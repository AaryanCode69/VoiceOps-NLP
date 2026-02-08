# VoiceOps — Call-Centric Risk & Fraud Intelligence

> VoiceOps analyzes financial calls in real time to detect unreliable commitments and fraud-like patterns, grounding explainable risk signals against known knowledge using RAG.

## Architecture Reference

All implementation is governed by [docs/RULES.md](docs/RULES.md). That file is a **hard constraint** — any code that violates it is incorrect by design.

## Project Structure

```
docs/
  RULES.md              # Non-negotiable system rules (locked)
src/
  api/                  # API layer — POST /analyze-call endpoint
  audio/                # Audio normalization and format validation
  stt/                  # Speech-to-text with provider selection (Sarvam AI / Whisper)
  nlp/                  # NLP extraction: intent, sentiment, obligations, contradictions, PII redaction
  risk/                 # Risk & fraud signal engine (multi-signal scoring)
  rag/                  # RAG grounding layer (knowledge-based explanations)
  schemas/              # Locked JSON output schema definitions
```

## Current Phase

**Phase 0** — Project skeleton only. No business logic has been implemented. All source files contain placeholder comments describing their future responsibilities.

## Pipeline Order (per RULES.md §6)

1. Audio normalization
2. STT + speaker diarization
3. Text cleanup & normalization
4. PII redaction (mandatory)
5. Financial NLP extraction
6. Risk & fraud signal computation
7. Summary generation
8. Structured JSON output to RAG
