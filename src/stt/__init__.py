# src/stt/__init__.py
# ====================
# Speech-to-Text Layer — VoiceOps (Phase 2 + Phase 3)
#
# Pipeline (per RULES.md §4):
#   1. Detect spoken language (language_detector.py)
#   2. Route to Sarvam AI STT (Indian) or OpenAI Whisper (non-Indian)
#   3. Run speaker diarization (diarizer.py via pyannote.audio)
#   4. Merge transcript with speaker labels (AGENT / CUSTOMER)
#   5. Return raw diarized, time-aligned utterances
#
# Phase 3 (diarization validation & structuring):
#   6. Validate diarization output (diarizer_validator.py)
#   7. Clean artifacts and structure utterances (utterance_structurer.py)
#
# Public API:
#   transcribe_and_diarize(audio_bytes) → list[dict]
#   validate_diarized_transcript(raw_utterances) → list[dict]
#   structure_utterances(validated_utterances) → list[dict]

from src.stt.router import transcribe_and_diarize  # noqa: F401
from src.stt.language_detector import (             # noqa: F401
    TranscriptSegment,
    LanguageDetectionResult,
)
from src.stt.diarizer import DiarizedUtterance      # noqa: F401
from src.stt.diarizer_validator import (            # noqa: F401
    validate_diarized_transcript,
)
from src.stt.utterance_structurer import (          # noqa: F401
    structure_utterances,
)

__all__ = [
    "transcribe_and_diarize",
    "TranscriptSegment",
    "LanguageDetectionResult",
    "DiarizedUtterance",
    "validate_diarized_transcript",
    "structure_utterances",
]
