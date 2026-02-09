"""
src/stt/diarizer.py
====================
Speaker Diarization — VoiceOps Phase 2

Responsibility:
    - Identify distinct speakers in the audio
    - Map speakers to AGENT / CUSTOMER labels (per RULES.md §4)
    - Merge diarization output with STT transcript segments
    - Produce the final raw diarized transcript

Speaker labelling heuristic:
    In call-center audio the first speaker is typically the AGENT
    (initiating the call). The second unique speaker is the CUSTOMER.

This module does NOT:
    - Perform NLP, sentiment, intent, or risk analysis
    - Perform PII redaction
    - Filter or remove any speaker's text (both AGENT and CUSTOMER preserved)
    - Store or embed data
"""

import io
import logging
import os
import time
import wave
from dataclasses import dataclass

import numpy as np
from dotenv import load_dotenv

from src.stt.language_detector import TranscriptSegment

load_dotenv()

logger = logging.getLogger("voiceops.stt.diarizer")


# ---------------------------------------------------------------------------
# Module-level pipeline cache (singleton — avoids reloading on every request)
# ---------------------------------------------------------------------------

_cached_pipeline = None
_cached_device = None


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpeakerTurn:
    """A single speaker turn from diarization."""

    speaker: str        # Raw label from diarizer (e.g. "SPEAKER_00")
    start_time: float
    end_time: float


@dataclass(frozen=True)
class DiarizedUtterance:
    """A transcript segment enriched with speaker label and timestamps."""

    speaker: str        # "AGENT" or "CUSTOMER"
    text: str
    start_time: float
    end_time: float

    def to_dict(self) -> dict:
        """Serialize to the Phase 2 output format."""
        return {
            "speaker": self.speaker,
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


# ---------------------------------------------------------------------------
# Speaker label constants
# ---------------------------------------------------------------------------

SPEAKER_AGENT = "AGENT"
SPEAKER_CUSTOMER = "CUSTOMER"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def diarize_and_merge(
    audio_bytes: bytes,
    transcript_segments: list[TranscriptSegment],
) -> list[DiarizedUtterance]:
    """
    Run speaker diarization on the audio and merge with transcript segments.

    Steps:
        1. Run pyannote.audio diarization pipeline on the audio
        2. Map raw speaker labels to AGENT / CUSTOMER
        3. Assign a speaker to each transcript segment via time overlap
        4. Return merged diarized utterances

    Args:
        audio_bytes:         Normalized audio (mono 16 kHz WAV bytes).
        transcript_segments: Time-aligned text segments from the STT provider.

    Returns:
        List of DiarizedUtterance ordered by start_time.

    Raises:
        RuntimeError: If diarization fails.
    """
    t0 = time.perf_counter()
    speaker_turns = _run_diarization(audio_bytes)
    t1 = time.perf_counter()
    logger.info("\u23f1\ufe0f  Diarization inference took %.2fs", t1 - t0)

    if not speaker_turns:
        # Fallback: if diarization produces no speaker turns (single party),
        # assume the sole speaker is the CUSTOMER.
        return [
            DiarizedUtterance(
                speaker=SPEAKER_CUSTOMER,
                text=seg.text,
                start_time=seg.start_time,
                end_time=seg.end_time,
            )
            for seg in transcript_segments
            if seg.text.strip()
        ]

    # Build speaker label map: first unique speaker → AGENT, rest → CUSTOMER
    label_map = _build_speaker_label_map(speaker_turns)

    # Merge transcript segments with speaker labels
    utterances = _merge_segments_with_speakers(
        transcript_segments, speaker_turns, label_map
    )

    return utterances


# ---------------------------------------------------------------------------
# Diarization pipeline
# ---------------------------------------------------------------------------


def _load_wav_bytes_to_tensor(audio_bytes: bytes):
    """
    Load normalized WAV bytes into a torch tensor using the wave module.

    Avoids torchaudio.load() which depends on torchcodec/FFmpeg DLLs
    and is extremely slow on Windows. Since Phase 1 already normalizes
    audio to mono 16kHz WAV, we can read it directly.

    Returns:
        Tuple of (waveform: torch.Tensor [1, N], sample_rate: int)
    """
    import torch

    buf = io.BytesIO(audio_bytes)
    with wave.open(buf, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    # Map sample width to numpy dtype
    dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
    dtype = dtype_map.get(sampwidth, np.int16)
    audio_np = np.frombuffer(raw, dtype=dtype).astype(np.float32)

    # Normalize to [-1.0, 1.0]
    norm_map = {1: 128.0, 2: 32768.0, 4: 2147483648.0}
    audio_np /= norm_map.get(sampwidth, 32768.0)

    # Mix to mono if needed (shouldn't be after Phase 1, but safety)
    if n_channels > 1:
        audio_np = audio_np.reshape(-1, n_channels).mean(axis=1)

    waveform = torch.from_numpy(audio_np).unsqueeze(0)  # shape: [1, N]
    return waveform, sample_rate


def _run_diarization(audio_bytes: bytes) -> list[SpeakerTurn]:
    """
    Run pyannote.audio speaker-diarization pipeline on in-memory audio.

    Uses GPU (CUDA) if available, falls back to CPU otherwise.
    The pipeline is cached at module level to avoid reloading on every request.

    Requires:
        - torch and pyannote.audio installed
        - HF_AUTH_TOKEN environment variable set (HuggingFace model access)

    Returns:
        List of SpeakerTurn ordered by start_time.
    """
    global _cached_pipeline, _cached_device

    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise RuntimeError(
            "Speaker diarization requires 'torch' and "
            "'pyannote.audio'. Install them with: "
            "pip install torch pyannote.audio"
        ) from exc

    # ------------------------------------------------------------------
    # Load and cache the pipeline (first request only)
    # ------------------------------------------------------------------
    if _cached_pipeline is None:
        hf_token = os.environ.get("HF_AUTH_TOKEN")
        if not hf_token:
            raise RuntimeError("HF_AUTH_TOKEN environment variable is not set.")

        # Select device: GPU if available, CPU as fallback
        if torch.cuda.is_available():
            _cached_device = torch.device("cuda")
            gpu_name = torch.cuda.get_device_name(0)
            cuda_ver = torch.version.cuda or "unknown"
            vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
            logger.info(
                "\U0001f7e2 Diarization device: GPU (%s) | CUDA %s | VRAM: %.0f MB",
                gpu_name, cuda_ver, vram_mb,
            )
        else:
            _cached_device = torch.device("cpu")
            logger.warning(
                "\U0001f7e1 Diarization device: CPU (no CUDA GPU detected \u2014 this will be slow)"
            )

        t_load = time.perf_counter()
        logger.info("Loading diarization pipeline (first request, will be cached)...")
        try:
            _cached_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                token=hf_token,
            )
            _cached_pipeline.to(_cached_device)
        except Exception as exc:
            _cached_pipeline = None
            _cached_device = None
            raise RuntimeError(f"Failed to load diarization model: {exc}") from exc

        t_load_end = time.perf_counter()
        logger.info(
            "\u2705 Diarization pipeline loaded and cached on %s (took %.2fs).",
            _cached_device, t_load_end - t_load,
        )
    else:
        device_label = (
            f"GPU ({torch.cuda.get_device_name(0)})"
            if _cached_device.type == "cuda"
            else "CPU"
        )
        logger.info("Using cached diarization pipeline on %s.", device_label)

    # ------------------------------------------------------------------
    # Load audio from WAV bytes using wave module (fast, no torchcodec)
    # ------------------------------------------------------------------
    t_audio = time.perf_counter()
    try:
        waveform, sample_rate = _load_wav_bytes_to_tensor(audio_bytes)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to decode audio for diarization: {exc}"
        ) from exc
    t_audio_end = time.perf_counter()
    duration_sec = waveform.shape[1] / sample_rate
    logger.info(
        "\u23f1\ufe0f  Audio loaded: %.1fs duration, %d Hz \u2014 decoded in %.3fs",
        duration_sec, sample_rate, t_audio_end - t_audio,
    )

    # Run the diarization pipeline
    try:
        result = _cached_pipeline({"waveform": waveform, "sample_rate": sample_rate})
    except Exception as exc:
        raise RuntimeError(f"Diarization pipeline failed: {exc}") from exc

    # New pyannote versions return a DiarizeOutput object;
    # the Annotation with itertracks() lives on .speaker_diarization.
    # Legacy versions return the Annotation directly.
    if hasattr(result, "speaker_diarization"):
        diarization = result.speaker_diarization
    else:
        diarization = result

    # Collect speaker turns
    turns: list[SpeakerTurn] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        turns.append(
            SpeakerTurn(
                speaker=speaker,
                start_time=round(turn.start, 2),
                end_time=round(turn.end, 2),
            )
        )

    turns.sort(key=lambda t: t.start_time)
    logger.info("Pyannote returned %d speaker turns.", len(turns))
    return turns


# ---------------------------------------------------------------------------
# Speaker label mapping
# ---------------------------------------------------------------------------


def _build_speaker_label_map(turns: list[SpeakerTurn]) -> dict[str, str]:
    """
    Map raw speaker labels to AGENT / CUSTOMER.

    Heuristic:
        - If only ONE unique speaker is detected, assume CUSTOMER
          (single-party recording).
        - If two or more speakers: the first speaker is the AGENT
          (initiating the call), all others are CUSTOMER.

    Args:
        turns: Ordered list of SpeakerTurn.

    Returns:
        Dict mapping a raw label (e.g. "SPEAKER_00") to "AGENT" or "CUSTOMER".
    """
    seen_order: list[str] = []
    for t in turns:
        if t.speaker not in seen_order:
            seen_order.append(t.speaker)

    label_map: dict[str, str] = {}

    if len(seen_order) == 1:
        # Single speaker detected → assume CUSTOMER
        label_map[seen_order[0]] = SPEAKER_CUSTOMER
    else:
        # Multiple speakers: first = AGENT, rest = CUSTOMER
        for i, raw_label in enumerate(seen_order):
            if i == 0:
                label_map[raw_label] = SPEAKER_AGENT
            else:
                label_map[raw_label] = SPEAKER_CUSTOMER

    return label_map


# ---------------------------------------------------------------------------
# Merging logic
# ---------------------------------------------------------------------------


def _merge_segments_with_speakers(
    transcript_segments: list[TranscriptSegment],
    speaker_turns: list[SpeakerTurn],
    label_map: dict[str, str],
) -> list[DiarizedUtterance]:
    """
    Assign a speaker label to each transcript segment by time overlap.

    For each transcript segment, the speaker turn with the greatest
    temporal overlap determines the speaker label.

    Args:
        transcript_segments: Timestamped text from the STT provider.
        speaker_turns:       Speaker turns from diarization.
        label_map:           Raw label → AGENT/CUSTOMER mapping.

    Returns:
        List of DiarizedUtterance ordered by start_time.
    """
    utterances: list[DiarizedUtterance] = []

    for seg in transcript_segments:
        if not seg.text.strip():
            continue

        best_speaker = _find_best_speaker(seg, speaker_turns, label_map)
        utterances.append(
            DiarizedUtterance(
                speaker=best_speaker,
                text=seg.text,
                start_time=seg.start_time,
                end_time=seg.end_time,
            )
        )

    utterances.sort(key=lambda u: u.start_time)
    return utterances


def _find_best_speaker(
    segment: TranscriptSegment,
    speaker_turns: list[SpeakerTurn],
    label_map: dict[str, str],
) -> str:
    """
    Find the speaker with the greatest time overlap for a transcript segment.

    Returns AGENT as the default if no overlap is found.
    """
    best_label = SPEAKER_AGENT
    best_overlap = 0.0

    for turn in speaker_turns:
        overlap_start = max(segment.start_time, turn.start_time)
        overlap_end = min(segment.end_time, turn.end_time)
        overlap = max(0.0, overlap_end - overlap_start)

        if overlap > best_overlap:
            best_overlap = overlap
            best_label = label_map.get(turn.speaker, SPEAKER_CUSTOMER)

    return best_label
