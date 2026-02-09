# src/stt/__init__.py
# ====================
# Speech-to-Text Layer — VoiceOps (Phase 2 ONLY)
#
# Phase 2 Pipeline (diarization-agnostic, no Whisper):
#   1. Detect call language via Deepgram
#   2. Chunk audio into 20–30 s segments with overlap
#   3. Route to Sarvam AI (Indian) or Deepgram Nova-3 (other)
#   4. Transcribe chunks in parallel (diarize=False)
#   5. Flatten, deduplicate overlap, adjust timestamps
#   6. Return timestamped transcript (text + times only)
#
# Phase 3 (semantic structuring) is handled entirely by src/nlp/:
#   - src/nlp/semantic_structurer.py (orchestrator)
#   - src/nlp/translator.py (translation)
#   - src/nlp/role_splitter.py (role attribution)
#
# Public API:
#   transcribe(audio_bytes) → list[dict]

from src.stt.router import transcribe  # noqa: F401
from src.stt.language_detector import (             # noqa: F401
    TranscriptSegment,
    LanguageDetectionResult,
)

__all__ = [
    "transcribe",
    "TranscriptSegment",
    "LanguageDetectionResult",
]
