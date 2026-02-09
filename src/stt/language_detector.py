"""
src/stt/language_detector.py
=============================
Language Detection — VoiceOps Phase 2

Responsibility:
    - Detect the dominant spoken language of normalized audio
    - Determine whether the language is Indian (Hindi, Hinglish, regional)
    - Route decision: Indian → Sarvam AI; non-Indian → Deepgram Nova-3

Language detection MUST occur before STT provider selection (RULES.md §4).

Detection uses OpenAI Whisper (whisper-1) ONLY to identify the spoken
language. The transcript returned by Whisper is discarded — actual STT
is performed by Sarvam AI or Deepgram Nova-3 only.

This module does NOT:
    - Perform STT transcription (language ID only)
    - Perform NLP, sentiment, intent, or risk analysis
    - Perform PII redaction
    - Perform translation
    - Store or embed data
"""

import io
import logging
import os
import wave
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger("voiceops.stt.language_detector")
logging.getLogger("openai._base_client").setLevel(logging.WARNING)

# If audio is >= this duration, only send the first DETECTION_CLIP_SECONDS
# to Whisper for language detection (saves time and cost).
DETECTION_THRESHOLD_SECONDS = 60
DETECTION_CLIP_SECONDS = 30


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
    is_indian: bool     # True → route to Sarvam; False → route to Deepgram
    was_trimmed: bool = False  # True if only a clip was used for detection


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_language(audio_bytes: bytes) -> LanguageDetectionResult:
    """
    Detect the dominant spoken language in the audio.

    Uses OpenAI Whisper API (whisper-1) ONLY for language identification.
    The transcript produced by Whisper is discarded — actual STT is
    performed by Sarvam AI or Deepgram Nova-3 downstream.

    This must run before STT provider selection (RULES.md §4).

    Args:
        audio_bytes: Normalized audio (mono 16 kHz WAV bytes).

    Returns:
        LanguageDetectionResult with language code, name, and indian flag.

    Raises:
        RuntimeError: If language detection fails.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    client = OpenAI(api_key=api_key)

    # ---- Trim long audio to first N seconds for faster detection ----
    detection_bytes, was_trimmed = _maybe_trim_for_detection(audio_bytes)

    try:
        audio_file = io.BytesIO(detection_bytes)
        audio_file.name = "audio.wav"

        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    except Exception as exc:
        raise RuntimeError(
            f"Whisper language detection failed: {exc}"
        ) from exc

    # ------------------------------------------------------------------
    # Extract language code from Whisper response (ISO 639-1).
    # The transcript text is intentionally discarded — Whisper is used
    # here ONLY for language identification, not for STT.
    #
    # NOTE: Whisper sometimes returns full language names (e.g. "tamil")
    # instead of ISO 639-1 codes (e.g. "ta"). We normalise to ISO codes
    # so that the INDIAN_LANGUAGE_CODES lookup works reliably.
    # ------------------------------------------------------------------
    raw_language: str = (getattr(response, "language", "unknown") or "unknown").strip().lower()
    language_code = _normalize_language_code(raw_language)
    is_indian = language_code in INDIAN_LANGUAGE_CODES
    language_name = _LANGUAGE_NAMES.get(language_code, language_code.title())

    lang_result = LanguageDetectionResult(
        language_code=language_code,
        language_name=language_name,
        is_indian=is_indian,
        was_trimmed=was_trimmed,
    )

    clip_info = f"{DETECTION_CLIP_SECONDS}s clip" if was_trimmed else "full audio"
    logger.info(
        "Language detected from %s: %s (%s) — route to %s",
        clip_info,
        language_name,
        language_code,
        "Sarvam AI" if is_indian else "Deepgram Nova-3",
    )

    return lang_result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _maybe_trim_for_detection(audio_bytes: bytes) -> tuple[bytes, bool]:
    """
    If the audio is >= DETECTION_THRESHOLD_SECONDS, return only the first
    DETECTION_CLIP_SECONDS as WAV bytes. Otherwise return the original bytes.

    Returns:
        Tuple of (possibly-trimmed WAV bytes, was_trimmed: bool).
    """
    buf = io.BytesIO(audio_bytes)
    try:
        with wave.open(buf, "rb") as wf:
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            duration = n_frames / sample_rate
    except Exception:
        # If we can't read the WAV header, just send the full bytes
        return audio_bytes, False

    if duration < DETECTION_THRESHOLD_SECONDS:
        return audio_bytes, False

    # Trim to first DETECTION_CLIP_SECONDS
    clip_frames = int(DETECTION_CLIP_SECONDS * sample_rate)
    buf.seek(0)
    with wave.open(buf, "rb") as wf:
        raw_frames = wf.readframes(clip_frames)

    # Write trimmed WAV
    out = io.BytesIO()
    with wave.open(out, "wb") as wf_out:
        wf_out.setnchannels(n_channels)
        wf_out.setsampwidth(sampwidth)
        wf_out.setframerate(sample_rate)
        wf_out.writeframes(raw_frames)

    logger.info(
        "Audio is %.0fs — trimmed to first %ds for language detection.",
        duration, DETECTION_CLIP_SECONDS,
    )
    return out.getvalue(), True


# ---------------------------------------------------------------------------
# Whisper language-code normalisation
# ---------------------------------------------------------------------------
# Whisper may return full language names (e.g. "tamil", "hindi",
# "english") instead of ISO 639-1 codes. This map lets us normalise
# both forms to the canonical two-letter code.

_LANGUAGE_NAME_TO_CODE: dict[str, str] = {
    "hindi": "hi",
    "marathi": "mr",
    "tamil": "ta",
    "telugu": "te",
    "kannada": "kn",
    "malayalam": "ml",
    "gujarati": "gu",
    "punjabi": "pa",
    "bengali": "bn",
    "odia": "or",
    "assamese": "as",
    "urdu": "ur",
    "nepali": "ne",
    "sanskrit": "sa",
    "sindhi": "sd",
    "sinhala": "si",
    "english": "en",
    "arabic": "ar",
    "chinese": "zh",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "japanese": "ja",
    "korean": "ko",
    "portuguese": "pt",
    "russian": "ru",
    "italian": "it",
    "dutch": "nl",
    "polish": "pl",
    "turkish": "tr",
    "vietnamese": "vi",
    "thai": "th",
    "swedish": "sv",
    "danish": "da",
    "finnish": "fi",
    "norwegian": "no",
}


def _normalize_language_code(raw: str) -> str:
    """
    Convert a Whisper language response to an ISO 639-1 code.

    Handles both cases:
        - Already an ISO code (e.g. "ta") → returned as-is if recognised.
        - Full name (e.g. "tamil") → mapped to "ta".

    Falls back to the raw string lowered if no mapping exists.
    """
    # If it's already a known ISO code, return directly
    if raw in _LANGUAGE_NAMES:
        return raw

    # Try full-name → ISO lookup
    code = _LANGUAGE_NAME_TO_CODE.get(raw)
    if code:
        return code

    # Last resort: return the raw value so callers can still operate
    logger.debug(
        "Unrecognised Whisper language token '%s' — using as-is.", raw,
    )
    return raw


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
