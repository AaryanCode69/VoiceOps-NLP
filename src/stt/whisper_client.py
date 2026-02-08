"""
src/stt/whisper_client.py
==========================
OpenAI Whisper STT Client — VoiceOps Phase 2

Responsibility:
    - Transcribe audio using OpenAI Whisper API
    - Translate audio to English using OpenAI Whisper Translation API
    - Return time-aligned text segments
    - Used for non-Indian languages (per RULES.md §4 STT routing)

This module does NOT:
    - Perform speaker diarization (handled by diarizer.py)
    - Perform NLP, sentiment, intent, or risk analysis
    - Perform PII redaction
    - Store or embed data
"""

import io
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

from src.stt.language_detector import TranscriptSegment


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def transcribe(audio_bytes: bytes) -> list[TranscriptSegment]:
    """
    Transcribe audio using OpenAI Whisper API.

    Returns segment-level timestamped text. No speaker labels — diarization
    is handled separately by diarizer.py.

    Args:
        audio_bytes: Normalized audio (mono 16 kHz WAV bytes).

    Returns:
        List of TranscriptSegment with text and time boundaries.

    Raises:
        RuntimeError: If the Whisper API call fails.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    client = OpenAI(api_key=api_key)

    try:
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.wav"

        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    except Exception as exc:
        raise RuntimeError(f"Whisper transcription failed: {exc}") from exc

    segments: list[TranscriptSegment] = []
    raw_segments = getattr(response, "segments", None) or []

    for seg in raw_segments:
        # Handle both dict and object attribute access patterns
        if isinstance(seg, dict):
            text = seg.get("text", "").strip()
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", 0.0))
        else:
            text = getattr(seg, "text", "").strip()
            start = float(getattr(seg, "start", 0.0))
            end = float(getattr(seg, "end", 0.0))

        if text:
            segments.append(
                TranscriptSegment(text=text, start_time=start, end_time=end)
            )

    return segments


def translate(audio_bytes: bytes) -> list[TranscriptSegment]:
    """
    Translate audio to English using OpenAI Whisper Translation API.

    Whisper's /audio/translations endpoint translates any spoken language
    to English text while preserving segment-level timestamps.
    If the source is already English, it effectively acts as transcription.

    Args:
        audio_bytes: Normalized audio (mono 16 kHz WAV bytes).

    Returns:
        List of TranscriptSegment with English text and time boundaries.

    Raises:
        RuntimeError: If the Whisper API call fails.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    client = OpenAI(api_key=api_key)

    try:
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.wav"

        response = client.audio.translations.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
        )
    except Exception as exc:
        raise RuntimeError(f"Whisper translation failed: {exc}") from exc

    segments: list[TranscriptSegment] = []
    raw_segments = getattr(response, "segments", None) or []

    for seg in raw_segments:
        if isinstance(seg, dict):
            text = seg.get("text", "").strip()
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", 0.0))
        else:
            text = getattr(seg, "text", "").strip()
            start = float(getattr(seg, "start", 0.0))
            end = float(getattr(seg, "end", 0.0))

        if text:
            segments.append(
                TranscriptSegment(text=text, start_time=start, end_time=end)
            )

    return segments
