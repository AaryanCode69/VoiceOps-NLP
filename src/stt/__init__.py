# src/stt/__init__.py
# ====================
# Speech-to-Text Layer — VoiceOps
#
# Responsibility (future phases):
#   - Language detection before STT provider selection (per RULES.md §4)
#   - Route to Sarvam AI STT for Hindi/Hinglish/Indian regional languages
#   - Route to OpenAI Whisper for all other languages
#   - Output speaker-diarized, time-aligned utterances
#   - Label speakers as AGENT or CUSTOMER (per RULES.md §4)
#
# Phase 0: Placeholder only. No logic implemented.
# TODO: Implement STT provider selection and diarization in a future phase.
