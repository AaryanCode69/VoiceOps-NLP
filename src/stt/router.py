"""
src/stt/router.py
==================
STT Router — VoiceOps Phase 2 (Sarvam + Deepgram, No Whisper)

Responsibility:
    Single entry point for Phase 2. Delegates to stt_pipeline which:
        1. Detects call language via Deepgram
        2. Chunks audio into 20–30 s segments with overlap
        3. Routes to the correct STT provider:
           - Indian / Hinglish → Sarvam AI
           - All other languages → Deepgram Nova-3
        4. Transcribes chunks in parallel (diarize=False)
        5. Returns diarization-agnostic transcript (text + timestamps only)

STT Routing Rules (LOCKED):
    - Indian native or Hinglish → Sarvam AI
    - Else → Deepgram Nova-3
    - Whisper MUST NOT be used

This module does NOT:
    - Perform speaker diarization or role classification
    - Translate text
    - Perform text cleanup or normalization
    - Perform PII redaction
    - Perform intent, sentiment, obligation, or risk analysis
    - Generate summaries or scores
    - Call RAG
    - Store data or generate identifiers
"""

import logging

from src.stt.stt_pipeline import transcribe as _run_pipeline

logger = logging.getLogger("voiceops.stt.router")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def transcribe(audio_bytes: bytes) -> list[dict]:
    """
    Full Phase 2 pipeline: detect language → chunk → route STT → flatten.

    Delegates to ``src.stt.stt_pipeline.transcribe`` which handles:
        1. Language detection (Deepgram)
        2. Audio chunking with overlap
        3. Routing to Sarvam AI (Indian) or Deepgram Nova-3 (other)
        4. Parallel transcription (diarize=False)
        5. Overlap deduplication and timestamp adjustment

    Args:
        audio_bytes: Normalized audio from Phase 1 (mono 16 kHz WAV bytes).

    Returns:
        List of dicts, each with keys:
            - "chunk_id":   int (sequential index)
            - "start_time": float (seconds, absolute)
            - "end_time":   float (seconds, absolute)
            - "text":       str (transcribed text)

    Raises:
        RuntimeError: If all chunks fail transcription.
    """
    logger.info("Phase 2 STT: language detection → Sarvam/Deepgram routing")
    return _run_pipeline(audio_bytes)
