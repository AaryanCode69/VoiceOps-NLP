# src/stt/__init__.py
# ====================
# Speech-to-Text Layer — VoiceOps (Phase 2)
#
# Pipeline (per RULES.md §4):
#   1. Detect spoken language (language_detector.py)
#   2. Route to Sarvam AI STT (Indian) or OpenAI Whisper (non-Indian)
#   3. Run speaker diarization (diarizer.py via pyannote.audio)
#   4. Merge transcript with speaker labels (AGENT / CUSTOMER)
#   5. Return raw diarized, time-aligned utterances
#
# Public API:
#   transcribe_and_diarize(audio_bytes) → list[dict]

from src.stt.router import transcribe_and_diarize  # noqa: F401
from src.stt.language_detector import (             # noqa: F401
    TranscriptSegment,
    LanguageDetectionResult,
)
from src.stt.diarizer import DiarizedUtterance      # noqa: F401

__all__ = [
    "transcribe_and_diarize",
    "TranscriptSegment",
    "LanguageDetectionResult",
    "DiarizedUtterance",
]
