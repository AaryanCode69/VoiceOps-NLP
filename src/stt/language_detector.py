"""
src/stt/language_detector.py
=============================
Language Detection — VoiceOps Phase 2

Responsibility:
    - Detect the dominant spoken language of normalized audio
    - Determine whether the language is Indian (Hindi, Hinglish, regional)
    - Provide the Whisper transcript from the detection call for reuse

Language detection MUST occur before STT provider selection (RULES.md §4).

This module does NOT:
    - Perform NLP, sentiment, intent, or risk analysis
    - Perform PII redaction
    - Store or embed data
"""

import io
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


# ---------------------------------------------------------------------------
# Indian language ISO 639-1 codes (RULES.md §4: Hindi, Hinglish, Indian
# regional languages route to Sarvam AI STT)
# ---------------------------------------------------------------------------

INDIAN_LANGUAGE_CODES: set[str] = {
    "hi",  # Hindi (includes Hinglish when detected as Hindi)
    "mr",  # Marathi
    "ta",  # Tamil
    "te",  # Telugu
    "kn",  # Kannada
    "ml",  # Malayalam
    "gu",  # Gujarati
    "pa",  # Punjabi
    "bn",  # Bengali
    "or",  # Odia
    "as",  # Assamese
    "ur",  # Urdu
    "ne",  # Nepali
    "sa",  # Sanskrit
    "sd",  # Sindhi
    "si",  # Sinhala
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TranscriptSegment:
    """A single time-aligned text segment from STT (no speaker info)."""

    text: str
    start_time: float
    end_time: float


@dataclass(frozen=True)
class LanguageDetectionResult:
    """Result of spoken language detection."""

    language_code: str  # ISO 639-1 (e.g. "hi", "en")
    language_name: str  # Human-readable (e.g. "Hindi", "English")
    is_indian: bool     # True → route to Sarvam; False → route to Whisper


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_language(audio_bytes: bytes) -> LanguageDetectionResult:
    """
    Detect the dominant spoken language in the audio.

    Uses OpenAI Whisper API to identify the language.
    This must run before STT provider selection (RULES.md §4).

    Args:
        audio_bytes: Normalized audio (mono 16 kHz WAV bytes).

    Returns:
        LanguageDetectionResult with language code, name, and indian flag.

    Raises:
        RuntimeError: If language detection fails.
    """
    result, _ = detect_language_with_transcript(audio_bytes)
    return result


def detect_language_with_transcript(
    audio_bytes: bytes,
) -> tuple[LanguageDetectionResult, list[TranscriptSegment]]:
    """
    Detect language AND produce timestamped transcript in one API call.

    The transcript is a by-product of language detection via Whisper.
    The router reuses it for non-Indian audio to avoid a redundant
    Whisper call.

    Args:
        audio_bytes: Normalized audio (mono 16 kHz WAV bytes).

    Returns:
        Tuple of (LanguageDetectionResult, list of TranscriptSegment).

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
        raise RuntimeError(f"Whisper language detection failed: {exc}") from exc

    # Extract language code from Whisper response (ISO 639-1)
    language_code: str = getattr(response, "language", "unknown") or "unknown"
    is_indian = language_code in INDIAN_LANGUAGE_CODES
    language_name = _LANGUAGE_NAMES.get(language_code, language_code.title())

    # Extract timestamped segments from the Whisper response
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

    lang_result = LanguageDetectionResult(
        language_code=language_code,
        language_name=language_name,
        is_indian=is_indian,
    )

    return lang_result, segments


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "bn": "Bengali",
    "or": "Odia",
    "as": "Assamese",
    "ur": "Urdu",
    "ne": "Nepali",
    "sa": "Sanskrit",
    "sd": "Sindhi",
    "si": "Sinhala",
    "ar": "Arabic",
    "zh": "Chinese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "ru": "Russian",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "th": "Thai",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "no": "Norwegian",
}
