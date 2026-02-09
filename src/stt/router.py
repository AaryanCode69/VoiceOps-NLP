"""
src/stt/router.py
==================
STT Router — VoiceOps Phase 2

Responsibility:
    Orchestrate the full Phase 2 pipeline:
        1. Detect spoken language (via OpenAI Whisper)
        2. Route to correct STT provider
               Indian languages → Sarvam AI STT
               All other languages → OpenAI Whisper STT
        3. Obtain raw timestamped transcript
        4. Run speaker diarization (pyannote.audio)
        5. Merge transcript with speaker labels
        6. Return the raw diarized transcript

    This is the single entry point for Phase 2.

Per RULES.md §4:
    - Language detection MUST occur before STT selection
    - Hindi / Hinglish / Indian regional → Sarvam AI STT
    - All other languages → OpenAI Whisper STT
    - Output includes speaker diarization (AGENT / CUSTOMER)
    - Output includes time-aligned utterances

This module does NOT:
    - Perform text cleanup or normalization
    - Perform PII redaction
    - Perform intent, sentiment, obligation, or risk analysis
    - Generate summaries or scores
    - Call RAG
    - Store data or generate identifiers
"""

import logging

from src.stt.language_detector import (
    detect_language_with_transcript,
    LanguageDetectionResult,
    TranscriptSegment,
)
from src.stt import sarvam_client
from src.stt import whisper_client
from src.stt.diarizer import diarize_and_merge, DiarizedUtterance

logger = logging.getLogger("voiceops.stt.router")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def transcribe_and_diarize(audio_bytes: bytes) -> list[dict]:
    """
    Full Phase 2 pipeline: language detection → STT → diarization.

    Steps:
        1. Detect language via Whisper API (also produces a transcript).
        2. If Indian language  → re-transcribe with Sarvam AI.
           If non-Indian lang → reuse Whisper transcript from step 1.
        3. Run speaker diarization on the audio.
        4. Merge transcript segments with speaker labels.
        5. Return raw diarized transcript as list of dicts.

    Args:
        audio_bytes: Normalized audio from Phase 1 (mono 16 kHz WAV bytes).

    Returns:
        List of dicts, each with keys:
            - "speaker":    "AGENT" or "CUSTOMER"
            - "text":       Transcribed text (always in English)
            - "start_time": float (seconds)
            - "end_time":   float (seconds)

    Raises:
        RuntimeError: If any pipeline step fails.
    """
    # ------------------------------------------------------------------
    # Step 1: Detect language (also yields Whisper transcript for reuse)
    # ------------------------------------------------------------------
    lang_result, whisper_segments = detect_language_with_transcript(audio_bytes)

    logger.info(
        "Language detected: %s (%s) | Indian: %s",
        lang_result.language_name,
        lang_result.language_code,
        lang_result.is_indian,
    )

    # ------------------------------------------------------------------
    # Step 2: Route to the correct STT provider (output always English)
    # ------------------------------------------------------------------
    if lang_result.is_indian:
        logger.info("STT provider selected: Sarvam AI (model: saaras:v2) + Sarvam Translate (mayura:v1)")
        transcript_segments = sarvam_client.transcribe_and_translate(
            audio_bytes, lang_result.language_code
        )
    elif lang_result.language_code == "en" and not lang_result.was_trimmed:
        logger.info("STT provider selected: OpenAI Whisper (model: whisper-1) — English detected, reusing detection transcript")
        transcript_segments = whisper_segments
    elif lang_result.language_code == "en" and lang_result.was_trimmed:
        logger.info("STT provider selected: OpenAI Whisper (model: whisper-1) — English detected, full transcription (detection used trimmed clip)")
        transcript_segments = whisper_client.transcribe(audio_bytes)
    else:
        logger.info("STT provider selected: OpenAI Whisper Translation (model: whisper-1) — translating %s to English", lang_result.language_name)
        transcript_segments = whisper_client.translate(audio_bytes)

    logger.info("Transcript segments received: %d", len(transcript_segments))

    if not transcript_segments:
        logger.warning("No transcript segments produced — returning empty result.")
        return []

    # ------------------------------------------------------------------
    # Step 3 & 4: Diarize and merge with transcript
    # ------------------------------------------------------------------
    logger.info("Starting speaker diarization...")
    utterances: list[DiarizedUtterance] = diarize_and_merge(
        audio_bytes, transcript_segments
    )
    logger.info("Diarization complete — %d utterances produced.", len(utterances))

    # ------------------------------------------------------------------
    # Step 5: Serialize to plain dicts for output
    # ------------------------------------------------------------------
    return [u.to_dict() for u in utterances]
