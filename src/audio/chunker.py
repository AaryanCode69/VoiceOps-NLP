"""
src/audio/chunker.py
=====================
Audio Chunker — VoiceOps Phase 1 (VAD-Aware)

Responsibility:
    - Split normalized audio (mono 16 kHz WAV) into chunks for parallel STT
    - Use Voice Activity Detection (Silero VAD) to find silence boundaries
      so chunks are split at natural pauses, not mid-utterance
    - Mark chunks that contain no speech so the STT layer can skip them
    - Apply overlap between consecutive chunks for speaker continuity

Per RULES.md §3.1:
    - Audio MUST be chunked BEFORE STT
    - Chunk size: 20–30 seconds  (target 25 s, max 35 s hard limit)
    - Overlap:   2–3 seconds     (default 2.5 s)
    - Chunks MUST be processed in parallel (caller's responsibility)
    - Failure of a single chunk MUST NOT fail the full pipeline

This module does NOT:
    - Perform STT, diarization, or any NLP
    - Modify the audio content (no gain, no filtering)
    - Store data
"""

import io
import logging
import wave
from typing import List, Tuple

import numpy as np

from src.audio.vad import find_silence_gaps, chunk_has_speech

logger = logging.getLogger("voiceops.audio.chunker")

# ---------------------------------------------------------------------------
# Defaults (within RULES.md §3.1 bounds)
# ---------------------------------------------------------------------------

DEFAULT_CHUNK_DURATION_SEC: float = 25.0   # target chunk duration (seconds)
DEFAULT_OVERLAP_SEC: float = 2.5           # overlap between consecutive chunks

# VAD-aware chunking parameters
_MIN_CHUNK_DURATION_SEC: float = 15.0      # don't create chunks shorter than this
_MAX_CHUNK_DURATION_SEC: float = 35.0      # hard upper bound if no silence found
_SPLIT_SEARCH_WINDOW_SEC: float = 5.0      # search ±5 s around target for silence


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chunk_audio(
    audio_bytes: bytes,
    chunk_duration: float = DEFAULT_CHUNK_DURATION_SEC,
    overlap: float = DEFAULT_OVERLAP_SEC,
) -> list[dict]:
    """
    Split normalized WAV audio into overlapping, VAD-aware chunks.

    Chunks are preferentially split at silence boundaries (detected via
    Silero VAD) to avoid cutting mid-utterance — the primary cause of
    Deepgram returning empty results for a chunk.

    Each chunk is a self-contained WAV byte buffer that can be sent
    independently to an STT provider.

    Args:
        audio_bytes:    Normalized audio from Phase 1 (mono 16 kHz WAV bytes).
        chunk_duration: Target duration of each chunk in seconds (20–30).
        overlap:        Overlap between consecutive chunks in seconds (2–3).

    Returns:
        List of chunk dicts, each containing:
            - chunk_id    (int):   Sequential chunk index starting at 0
            - audio_bytes (bytes): Standalone WAV file bytes for the chunk
            - offset      (float): Start time of this chunk in the original
                                   audio (seconds)
            - duration    (float): Actual duration of this chunk (seconds)
            - has_speech  (bool):  Whether VAD detected meaningful speech
                                   in this chunk

    Raises:
        ValueError: If audio_bytes is empty or not valid WAV.
    """
    if not audio_bytes:
        raise ValueError("audio_bytes is empty — nothing to chunk.")

    # ------------------------------------------------------------------
    # Read WAV metadata and raw PCM frames
    # ------------------------------------------------------------------
    try:
        buf = io.BytesIO(audio_bytes)
        with wave.open(buf, "rb") as wf:
            sample_rate = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw_pcm = wf.readframes(n_frames)
    except Exception as exc:
        raise ValueError(f"Failed to read WAV audio for chunking: {exc}") from exc

    total_duration = n_frames / sample_rate
    frame_byte_size = n_channels * sampwidth  # bytes per frame

    logger.info(
        "Chunking audio: %.1fs total | %d Hz | %d ch | %d-bit | "
        "target=%.1fs overlap=%.1fs (VAD-aware)",
        total_duration, sample_rate, n_channels, sampwidth * 8,
        chunk_duration, overlap,
    )

    # ------------------------------------------------------------------
    # Convert raw PCM to float32 numpy array for VAD
    # ------------------------------------------------------------------
    dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
    np_dtype = dtype_map.get(sampwidth, np.int16)
    pcm_float = np.frombuffer(raw_pcm, dtype=np_dtype).astype(np.float32)

    norm_map = {1: 128.0, 2: 32768.0, 4: 2147483648.0}
    pcm_float = pcm_float / norm_map.get(sampwidth, 32768.0)

    # Mix to mono if needed (shouldn't happen after Phase 1, but safety)
    if n_channels > 1:
        pcm_float = pcm_float.reshape(-1, n_channels).mean(axis=1)

    # ------------------------------------------------------------------
    # Short audio — return as a single chunk (no splitting needed)
    # ------------------------------------------------------------------
    if total_duration <= _MAX_CHUNK_DURATION_SEC:
        logger.info(
            "Audio (%.1fs) fits in a single chunk — no splitting.", total_duration
        )
        speech = chunk_has_speech(pcm_float, sample_rate=sample_rate)
        return [
            {
                "chunk_id": 0,
                "audio_bytes": audio_bytes,
                "offset": 0.0,
                "duration": round(total_duration, 3),
                "has_speech": speech,
            }
        ]

    # ------------------------------------------------------------------
    # Detect silence gaps across the full audio for intelligent splitting
    # ------------------------------------------------------------------
    silence_gaps = find_silence_gaps(
        pcm_float, sample_rate=sample_rate, min_silence_duration_ms=300,
    )
    logger.info(
        "VAD found %d silence gaps in %.1fs of audio.", len(silence_gaps), total_duration,
    )

    # ------------------------------------------------------------------
    # Compute split points at silence boundaries
    # ------------------------------------------------------------------
    split_samples = _compute_split_points(
        total_samples=n_frames,
        sample_rate=sample_rate,
        silence_gaps=silence_gaps,
        target_chunk_sec=chunk_duration,
    )
    logger.info(
        "Computed %d split points → %d chunks.",
        len(split_samples), len(split_samples) + 1,
    )

    # ------------------------------------------------------------------
    # Build chunk boundaries with overlap
    # ------------------------------------------------------------------
    overlap_frames = int(overlap * sample_rate)
    boundaries: list[Tuple[int, int]] = []
    prev = 0
    for sp in split_samples:
        boundaries.append((prev, sp))
        # Next chunk starts overlap_frames before the split point
        prev = max(0, sp - overlap_frames)
    boundaries.append((prev, n_frames))  # final chunk

    # ------------------------------------------------------------------
    # Extract chunks & run per-chunk VAD
    # ------------------------------------------------------------------
    chunks: list[dict] = []
    for idx, (start_frame, end_frame) in enumerate(boundaries):
        chunk_raw = raw_pcm[start_frame * frame_byte_size : end_frame * frame_byte_size]
        chunk_wav = _frames_to_wav(chunk_raw, n_channels, sampwidth, sample_rate)

        offset_sec = round(start_frame / sample_rate, 3)
        dur_sec = round((end_frame - start_frame) / sample_rate, 3)

        # Per-chunk speech detection
        chunk_pcm = pcm_float[start_frame:end_frame]
        speech = chunk_has_speech(chunk_pcm, sample_rate=sample_rate)

        if not speech:
            logger.info(
                "Chunk %d (%.1fs–%.1fs) has no speech — will be skipped by STT.",
                idx, offset_sec, offset_sec + dur_sec,
            )

        chunks.append(
            {
                "chunk_id": idx,
                "audio_bytes": chunk_wav,
                "offset": offset_sec,
                "duration": dur_sec,
                "has_speech": speech,
            }
        )

    speech_count = sum(1 for c in chunks if c["has_speech"])
    logger.info(
        "Chunking complete: %d total chunks (%d with speech, %d silent).",
        len(chunks), speech_count, len(chunks) - speech_count,
    )

    return chunks


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_split_points(
    total_samples: int,
    sample_rate: int,
    silence_gaps: list[Tuple[int, int]],
    target_chunk_sec: float,
) -> list[int]:
    """
    Compute sample-level split points, preferring silence gap midpoints
    near the target chunk boundary.

    For each target split position, searches a ±_SPLIT_SEARCH_WINDOW_SEC
    window for the closest silence gap midpoint.  If no silence gap is
    found, falls back to a hard split at the max chunk boundary.
    """
    target_samples = int(target_chunk_sec * sample_rate)
    search_window = int(_SPLIT_SEARCH_WINDOW_SEC * sample_rate)
    min_chunk_samples = int(_MIN_CHUNK_DURATION_SEC * sample_rate)
    max_chunk_samples = int(_MAX_CHUNK_DURATION_SEC * sample_rate)

    splits: list[int] = []
    current = 0

    while current + min_chunk_samples < total_samples:
        target_split = current + target_samples

        # If we're near the end, no need to split
        if target_split >= total_samples:
            break

        # Remaining audio after this potential split
        remaining = total_samples - target_split
        if remaining < min_chunk_samples:
            # Don't split — last piece would be too short; let it merge
            break

        # Try to find a silence gap near the target
        best = _find_nearest_silence_midpoint(
            silence_gaps, target_split, search_window,
        )

        if best is not None:
            chunk_len = best - current
            if chunk_len < min_chunk_samples:
                # Gap too close to current position — search further out
                best = _find_nearest_silence_midpoint(
                    silence_gaps,
                    current + max_chunk_samples,
                    search_window,
                )
            if best is not None and (best - current) >= min_chunk_samples:
                splits.append(best)
                current = best
                continue

        # No suitable silence gap — hard split at max boundary
        hard_split = min(current + max_chunk_samples, total_samples)
        logger.warning(
            "No silence gap near %.1fs — hard split at %.1fs.",
            target_split / sample_rate,
            hard_split / sample_rate,
        )
        splits.append(hard_split)
        current = hard_split

    return splits


def _find_nearest_silence_midpoint(
    silence_gaps: list[Tuple[int, int]],
    target_sample: int,
    search_window: int,
) -> int | None:
    """
    Find the silence gap whose midpoint is closest to *target_sample*
    within ±*search_window*.

    Returns the midpoint sample index, or None if no gap qualifies.
    """
    window_lo = target_sample - search_window
    window_hi = target_sample + search_window

    best_point: int | None = None
    best_dist = float("inf")

    for gap_start, gap_end in silence_gaps:
        gap_mid = (gap_start + gap_end) // 2
        if window_lo <= gap_mid <= window_hi:
            dist = abs(gap_mid - target_sample)
            if dist < best_dist:
                best_dist = dist
                best_point = gap_mid

    return best_point


def _frames_to_wav(
    raw_pcm: bytes,
    n_channels: int,
    sampwidth: int,
    sample_rate: int,
) -> bytes:
    """Wrap raw PCM frames into a standalone WAV byte buffer."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_pcm)
    return buf.getvalue()
