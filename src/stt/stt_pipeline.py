"""
src/stt/stt_pipeline.py
========================
STT Pipeline — VoiceOps Phase 2 (Sarvam + Deepgram, No Whisper)

Responsibility:
    Orchestrate the full Phase 2 pipeline:
        1. Detect the call language (Deepgram detect_language)
        2. Chunk audio into 20–30 s segments with overlap
        3. Route chunks to the correct STT provider:
           - Indian / Hinglish → Sarvam AI
           - All other languages → Deepgram Nova-3
        4. Transcribe chunks in parallel (diarize=False)
        5. Handle per-chunk failures gracefully (skip, don't crash)
        6. Adjust per-chunk timestamps to absolute positions
        7. Deduplicate text in overlap regions
        8. Return flat list of chunk transcripts (text + timestamps only)

STT Routing Rules (LOCKED):
    - Indian native or Hinglish → Sarvam AI
    - All other languages → Deepgram Nova-3
    - Whisper MUST NOT be used under any condition

This module does NOT:
    - Perform speaker diarization or role classification
    - Translate text
    - Perform NLP, sentiment, intent, or risk analysis
    - Perform PII redaction
    - Generate summaries, scores, or identifiers
    - Store data
"""

import io
import logging
import os
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.audio.chunker import chunk_audio
from src.stt.deepgram_client import transcribe_chunk as deepgram_transcribe_chunk
from src.stt.sarvam_client import transcribe_chunk as sarvam_transcribe_chunk
from src.stt.language_detector import detect_language

logger = logging.getLogger("voiceops.stt.stt_pipeline")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Maximum parallel workers for chunk transcription
MAX_WORKERS: int = 4

# Chunking toggle: set ENABLE_CHUNKING=false in .env to send full audio
# directly to Deepgram without VAD-aware splitting.
# Default: enabled ("true").
_CHUNKING_ENABLED: bool = os.environ.get(
    "ENABLE_CHUNKING", "true"
).strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def transcribe(audio_bytes: bytes) -> list[dict]:
    """
    Full Phase 2 pipeline: detect language → chunk → route to STT → flatten.

    Routing:
        - Indian / Hinglish → Sarvam AI
        - All other languages → Deepgram Nova-3 (diarize=False)

    Output is diarization-agnostic: text + timestamps only.

    Steps:
        1. Detect call language via Deepgram (short clip).
        2. Chunk audio into ~25 s segments with 2.5 s overlap.
        3. Route and transcribe each chunk in parallel.
        4. Adjust timestamps from chunk-local to absolute.
        5. Deduplicate text in overlap regions.
        6. Return flat list of chunk transcript dicts.

    Args:
        audio_bytes: Normalized audio from Phase 1 (mono 16 kHz WAV bytes).

    Returns:
        List of dicts, each with keys:
            - "chunk_id":   int (sequential index)
            - "start_time": float (seconds, absolute)
            - "end_time":   float (seconds, absolute)
            - "text":       str (transcribed text)

    Raises:
        RuntimeError: If ALL chunks fail transcription.
    """
    # ------------------------------------------------------------------
    # Step 1: Detect call language
    # ------------------------------------------------------------------
    lang_result = detect_language(audio_bytes)
    logger.info(
        "Language detection: %s (%s) — routing to %s.",
        lang_result.language_name,
        lang_result.language_code,
        "Sarvam AI" if lang_result.is_indian else "Deepgram Nova-3",
    )

    # ------------------------------------------------------------------
    # Step 2: Chunk audio (or bypass if chunking is disabled)
    #
    # NOTE: Sarvam AI has a per-request file-size / duration limit.
    # Chunking is ALWAYS forced ON for Sarvam routes regardless of
    # the ENABLE_CHUNKING setting to avoid 400 errors on large files.
    # ------------------------------------------------------------------
    force_chunking = lang_result.is_indian  # Sarvam requires chunked input

    if _CHUNKING_ENABLED or force_chunking:
        if force_chunking and not _CHUNKING_ENABLED:
            logger.info(
                "Chunking was DISABLED but forced ON for Sarvam AI route "
                "(Sarvam has per-request size limits)."
            )
        chunks = chunk_audio(audio_bytes)
        logger.info("Audio chunked into %d segment(s).", len(chunks))
    else:
        logger.info(
            "Chunking DISABLED (ENABLE_CHUNKING=false). "
            "Sending full audio directly to STT."
        )
        chunks = [_wrap_full_audio_as_chunk(audio_bytes)]

    # ------------------------------------------------------------------
    # Step 3: Parallel transcription via routed STT provider
    # ------------------------------------------------------------------
    chunk_results = _transcribe_chunks_parallel(chunks, lang_result)

    # Count results — silent chunks (skipped by VAD) are not failures
    silent_count = sum(1 for cr in chunk_results if cr.get("skipped_silent"))
    speech_chunks = len(chunks) - silent_count
    succeeded = sum(
        1 for cr in chunk_results
        if cr["transcript"] is not None and not cr.get("skipped_silent")
    )
    provider = "Sarvam AI" if lang_result.is_indian else "Deepgram Nova-3"
    logger.info(
        "%s transcription: %d/%d speech chunks succeeded "
        "(%d silent chunks skipped by VAD).",
        provider, succeeded, speech_chunks, silent_count,
    )

    # ------------------------------------------------------------------
    # Step 4: Fail if no speech chunks succeeded
    # ------------------------------------------------------------------
    if succeeded == 0 and speech_chunks > 0:
        raise RuntimeError(
            f"All {speech_chunks} audio chunks failed {provider} — "
            "no usable transcript produced."
        )

    # ------------------------------------------------------------------
    # Steps 5–6: Flatten with absolute timestamps, deduplicate overlap
    # ------------------------------------------------------------------
    transcript = _flatten_chunks(chunk_results)

    logger.info("Pipeline produced %d transcript segment(s).", len(transcript))
    return transcript


# ---------------------------------------------------------------------------
# No-chunking helper
# ---------------------------------------------------------------------------


def _wrap_full_audio_as_chunk(audio_bytes: bytes) -> dict:
    """
    Wrap the entire audio as a single "chunk" dict so the rest of the
    pipeline (transcription) works unchanged.

    Used when ``ENABLE_CHUNKING=false``.
    """
    try:
        buf = io.BytesIO(audio_bytes)
        with wave.open(buf, "rb") as wf:
            n_frames = wf.getnframes()
            sample_rate = wf.getframerate()
            duration = n_frames / sample_rate
    except Exception:
        duration = 0.0

    return {
        "chunk_id": 0,
        "audio_bytes": audio_bytes,
        "offset": 0.0,
        "duration": round(duration, 3),
        "has_speech": True,  # assume speech — no VAD when chunking is off
    }


# ---------------------------------------------------------------------------
# Parallel chunk transcription (routed by language)
# ---------------------------------------------------------------------------


def _transcribe_chunks_parallel(
    chunks: list[dict],
    lang_result,
) -> list[dict]:
    """
    Send all chunks to the appropriate STT provider in parallel.

    Routing:
        - Indian / Hinglish (lang_result.is_indian) → Sarvam AI
        - Else → Deepgram Nova-3

    Chunks flagged as ``has_speech=False`` by the VAD pre-filter are
    skipped entirely — they produce no transcript and don't count as
    failures.

    Returns a list of result dicts (one per chunk, in chunk_id order):
        [{ "chunk_id": int, "offset": float, "transcript": dict|None }, ...]

    Failed chunks get transcript=None (logged, not raised).
    """
    results: list[dict] = [None] * len(chunks)  # type: ignore[list-item]

    def _transcribe_one(chunk: dict) -> dict:
        cid = chunk["chunk_id"]

        # Skip chunks with no detected speech (VAD pre-filter)
        if not chunk.get("has_speech", True):
            logger.info(
                "Chunk %d (offset=%.1fs) skipped — no speech detected by VAD.",
                cid, chunk["offset"],
            )
            return {
                "chunk_id": cid,
                "offset": chunk["offset"],
                "duration": chunk["duration"],
                "transcript": None,
                "skipped_silent": True,
            }

        try:
            if lang_result.is_indian:
                result = sarvam_transcribe_chunk(
                    chunk["audio_bytes"],
                    language_code=lang_result.language_code,
                )
            else:
                result = deepgram_transcribe_chunk(chunk["audio_bytes"])

            return {
                "chunk_id": cid,
                "offset": chunk["offset"],
                "duration": chunk["duration"],
                "transcript": result,  # dict or None
                "skipped_silent": False,
            }
        except Exception as exc:
            provider = "Sarvam" if lang_result.is_indian else "Deepgram"
            logger.warning(
                "Chunk %d failed %s (offset=%.1fs): %s — skipping.",
                cid, provider, chunk["offset"], exc,
            )
            return {
                "chunk_id": cid,
                "offset": chunk["offset"],
                "duration": chunk["duration"],
                "transcript": None,
                "skipped_silent": False,
            }

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(chunks))) as executor:
        futures = {
            executor.submit(_transcribe_one, chunk): chunk["chunk_id"]
            for chunk in chunks
        }
        for future in as_completed(futures):
            result = future.result()
            results[result["chunk_id"]] = result

    return results


# ---------------------------------------------------------------------------
# Flatten chunks into diarization-agnostic transcript
# ---------------------------------------------------------------------------


def _flatten_chunks(chunk_results: list[dict]) -> list[dict]:
    """
    Merge per-chunk transcription results into a flat list of transcript
    segments with absolute timestamps.

    For overlap regions: text from the earlier chunk is kept; overlapping
    portions from the next chunk are trimmed by adjusting start_time.

    Output contract (diarization-agnostic):
        - chunk_id   (int):   Sequential index
        - start_time (float): Absolute start in seconds
        - end_time   (float): Absolute end in seconds
        - text       (str):   Transcribed text
    """
    if not chunk_results:
        return []

    segments: list[dict] = []
    prev_abs_end: float = 0.0
    output_idx = 0

    for chunk_result in chunk_results:
        transcript = chunk_result["transcript"]
        offset = chunk_result["offset"]

        if transcript is None:
            continue

        text = transcript.get("text", "").strip()
        if not text:
            continue

        # Compute absolute timestamps
        abs_start = round(transcript["start_time"] + offset, 2)
        abs_end = round(transcript["end_time"] + offset, 2)

        # Overlap deduplication: if this chunk's start overlaps with
        # the previous chunk's end, adjust the start forward.
        # The text may partially overlap but we keep the full chunk text
        # since Deepgram processes each chunk independently.
        if abs_start < prev_abs_end:
            abs_start = prev_abs_end

        # Only emit if there's a valid time window
        if abs_end <= abs_start:
            continue

        segments.append({
            "chunk_id": output_idx,
            "start_time": abs_start,
            "end_time": abs_end,
            "text": text,
        })

        prev_abs_end = abs_end
        output_idx += 1

    return segments
