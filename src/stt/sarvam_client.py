"""
src/stt/sarvam_client.py
=========================
Sarvam AI STT Client — VoiceOps Phase 2

Responsibility:
    - Transcribe audio using Sarvam AI API (saaras model)
    - Return time-aligned text segments
    - Used for Hindi, Hinglish, and Indian regional languages (per RULES.md §4)

This module does NOT:
    - Perform speaker diarization (handled by diarizer.py)
    - Perform NLP, sentiment, intent, or risk analysis
    - Perform PII redaction
    - Store or embed data
"""

import io
import os

import requests
from dotenv import load_dotenv

load_dotenv()

from src.stt.language_detector import TranscriptSegment


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SARVAM_API_BASE = "https://api.sarvam.ai"
SARVAM_STT_ENDPOINT = f"{SARVAM_API_BASE}/speech-to-text"
SARVAM_MODEL = "saaras:v2"

# Map ISO 639-1 to Sarvam BCP 47 language codes
_LANGUAGE_CODE_MAP: dict[str, str] = {
    "hi": "hi-IN",
    "mr": "mr-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "gu": "gu-IN",
    "pa": "pa-IN",
    "bn": "bn-IN",
    "or": "od-IN",  # Sarvam uses "od-IN" for Odia
    "as": "as-IN",
    "ur": "ur-IN",
    "ne": "ne-NP",
    "sa": "sa-IN",
    "sd": "sd-IN",
    "si": "si-LK",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def transcribe(
    audio_bytes: bytes,
    language_code: str,
) -> list[TranscriptSegment]:
    """
    Transcribe audio using the Sarvam AI STT API.

    Returns timestamped text segments. No speaker labels — diarization
    is handled separately by diarizer.py.

    Args:
        audio_bytes:   Normalized audio (mono 16 kHz WAV bytes).
        language_code: ISO 639-1 language code detected upstream (e.g. "hi", "ta").

    Returns:
        List of TranscriptSegment with text and time boundaries.

    Raises:
        RuntimeError: If the Sarvam API call fails.
    """
    api_key = os.environ.get("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY environment variable is not set.")

    sarvam_lang = _LANGUAGE_CODE_MAP.get(language_code, f"{language_code}-IN")

    headers = {
        "api-subscription-key": api_key,
    }

    files = {
        "file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav"),
    }

    data = {
        "language_code": sarvam_lang,
        "model": SARVAM_MODEL,
        "with_timestamps": "true",
    }

    try:
        resp = requests.post(
            SARVAM_STT_ENDPOINT,
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Sarvam API request failed: {exc}") from exc

    body = resp.json()
    return _parse_response(body)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_response(body: dict) -> list[TranscriptSegment]:
    """
    Parse Sarvam API response into TranscriptSegment list.

    Handles both word-level timestamps and plain transcript fallback.
    """
    segments: list[TranscriptSegment] = []

    # Try word-level timestamps first
    timestamps = body.get("timestamps") or {}
    words = timestamps.get("words") or []

    if words:
        segments = _group_words_into_segments(words)
    else:
        # Fallback: single segment from full transcript (no fine-grained timing)
        transcript = body.get("transcript", "").strip()
        if transcript:
            segments.append(
                TranscriptSegment(text=transcript, start_time=0.0, end_time=0.0)
            )

    return segments


def _group_words_into_segments(
    words: list[dict],
    pause_threshold: float = 1.0,
) -> list[TranscriptSegment]:
    """
    Group word-level timestamps into sentence-like segments.

    Words separated by more than ``pause_threshold`` seconds of silence
    are split into separate segments.

    Args:
        words:           List of {"word": str, "start": float, "end": float}.
        pause_threshold: Max silence gap (seconds) before splitting.

    Returns:
        List of TranscriptSegment.
    """
    if not words:
        return []

    segments: list[TranscriptSegment] = []
    current_words: list[str] = []
    seg_start: float = words[0].get("start", 0.0)
    prev_end: float = seg_start

    for w in words:
        w_start = float(w.get("start", prev_end))
        w_end = float(w.get("end", w_start))
        w_text = w.get("word", "").strip()

        if not w_text:
            continue

        # Start a new segment when the silence gap exceeds threshold
        if current_words and (w_start - prev_end) > pause_threshold:
            segments.append(
                TranscriptSegment(
                    text=" ".join(current_words),
                    start_time=seg_start,
                    end_time=prev_end,
                )
            )
            current_words = []
            seg_start = w_start

        current_words.append(w_text)
        prev_end = w_end

    # Flush remaining words
    if current_words:
        segments.append(
            TranscriptSegment(
                text=" ".join(current_words),
                start_time=seg_start,
                end_time=prev_end,
            )
        )

    return segments
