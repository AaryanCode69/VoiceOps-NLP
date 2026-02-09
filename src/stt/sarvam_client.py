"""
src/stt/sarvam_client.py
=========================
Sarvam AI STT Client — VoiceOps Phase 2

Responsibility:
    - Transcribe audio using Sarvam AI API (saaras model)
    - Return raw time-aligned text segments
    - Used for Hindi, Hinglish, and Indian regional languages (per RULES.md §4)

Per Phase 2 spec:
    - No translation (Phase 3 responsibility)
    - No diarization or speaker labels
    - No semantic inference
    - Output is raw text + timestamps only

This module does NOT:
    - Perform speaker diarization or role classification
    - Translate text
    - Perform NLP, sentiment, intent, or risk analysis
    - Perform PII redaction
    - Store or embed data
"""

import io
import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("voiceops.stt.sarvam_client")

from src.stt.language_detector import TranscriptSegment


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SARVAM_API_BASE = "https://api.sarvam.ai"
SARVAM_STT_ENDPOINT = f"{SARVAM_API_BASE}/speech-to-text"
SARVAM_MODEL = "saaras:v3"

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

    Returns timestamped text segments. No speaker labels, no translation.

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
    except requests.HTTPError as exc:
        # Capture response body for diagnostics (Sarvam 400s include details)
        detail = ""
        try:
            detail = f" — response: {resp.text[:500]}"
        except Exception:
            pass
        raise RuntimeError(
            f"Sarvam API request failed: {exc}{detail}"
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Sarvam API request failed: {exc}") from exc

    body = resp.json()
    logger.debug("Sarvam v3 raw response keys: %s", list(body.keys()))
    logger.debug("Sarvam v3 raw response body (truncated): %.1000s", body)
    return _parse_response(body)


def transcribe_chunk(
    audio_bytes: bytes,
    language_code: str,
) -> dict | None:
    """
    Transcribe a single audio chunk using Sarvam AI.

    Returns a dict matching the Phase 2 chunk output contract
    (text + start_time + end_time), compatible with Deepgram's output.

    Args:
        audio_bytes:   WAV audio bytes for a single chunk.
        language_code: ISO 639-1 language code (e.g. "hi", "ta").

    Returns:
        A dict containing:
            - text       (str):   Transcribed text for this chunk
            - start_time (float): Start of first segment (seconds, chunk-relative)
            - end_time   (float): End of last segment (seconds, chunk-relative)

        Returns None if Sarvam produces no transcript.

    Raises:
        RuntimeError: If the Sarvam API call fails.
    """
    segments = transcribe(audio_bytes, language_code)

    if not segments:
        return None

    texts = [seg.text.strip() for seg in segments if seg.text.strip()]
    if not texts:
        return None

    return {
        "text": " ".join(texts),
        "start_time": round(segments[0].start_time, 2),
        "end_time": round(segments[-1].end_time, 2),
    }


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_response(body: dict) -> list[TranscriptSegment]:
    """
    Parse Sarvam API response into TranscriptSegment list.

    Handles the Sarvam v3 parallel-array timestamp format:
        {
          "transcript": "...",
          "timestamps": {
            "words": ["word1", "word2", ...],
            "start_time_seconds": [0.0, 0.5, ...],
            "end_time_seconds": [0.4, 0.9, ...]
          }
        }

    Falls back to plain transcript if timestamps are absent.
    """
    segments: list[TranscriptSegment] = []

    # Try word-level timestamps first (v3 parallel-array format)
    timestamps = body.get("timestamps") or {}
    words = timestamps.get("words") or []
    start_times = timestamps.get("start_time_seconds") or []
    end_times = timestamps.get("end_time_seconds") or []

    if words and start_times and end_times:
        # Build unified word entries from parallel arrays
        word_entries = []
        for i, w_text in enumerate(words):
            word_entries.append({
                "word": w_text if isinstance(w_text, str) else str(w_text),
                "start": float(start_times[i]) if i < len(start_times) else 0.0,
                "end": float(end_times[i]) if i < len(end_times) else 0.0,
            })
        segments = _group_words_into_segments(word_entries)
    elif words and isinstance(words[0], dict):
        # Legacy v2 dict format fallback (just in case)
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
