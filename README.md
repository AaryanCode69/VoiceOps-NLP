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

**Phase 2** — Speech-to-Text with language-based provider routing and speaker diarization.

### What Phase 1 implements

| File | Purpose |
|---|---|
| `src/api/upload.py` | `POST /analyze-call` — accepts `.wav` / `.mp3` via multipart upload |
| `src/audio/normalizer.py` | Validates format, duration, emptiness; converts to mono 16 kHz WAV |

### What Phase 2 implements

| File | Purpose |
|---|---|
| `src/stt/language_detector.py` | Detects spoken language via OpenAI Whisper API; classifies Indian vs non-Indian |
| `src/stt/router.py` | Orchestrates the Phase 2 pipeline: detect → route → transcribe → diarize |
| `src/stt/whisper_client.py` | OpenAI Whisper API client for non-Indian language transcription |
| `src/stt/sarvam_client.py` | Sarvam AI API client for Hindi / Hinglish / Indian regional language transcription |
| `src/stt/diarizer.py` | Speaker diarization via pyannote.audio; merges transcript with AGENT / CUSTOMER labels |

### STT Routing Logic (per RULES.md §4)

```
Audio (normalized, mono 16 kHz WAV)
  │
  ▼
Language Detection (OpenAI Whisper API)
  │
  ├── Detected language ∈ {Hindi, Hinglish, Indian regional}
  │     → Sarvam AI STT (saaras:v2)
  │
  └── All other languages
        → OpenAI Whisper STT
  │
  ▼
Speaker Diarization (pyannote.audio)
  │
  ▼
Raw Diarized Transcript
  [{ speaker: AGENT|CUSTOMER, text, start_time, end_time }]
```

**Indian languages routed to Sarvam AI:** Hindi (hi), Marathi (mr), Tamil (ta), Telugu (te), Kannada (kn), Malayalam (ml), Gujarati (gu), Punjabi (pa), Bengali (bn), Odia (or), Assamese (as), Urdu (ur), Nepali (ne), Sanskrit (sa), Sindhi (sd), Sinhala (si).

### Environment Variables (Phase 2)

| Variable | Required for |
|---|---|
| `OPENAI_API_KEY` | Language detection + Whisper STT |
| `SARVAM_API_KEY` | Sarvam AI STT (Indian languages only) |
| `HF_AUTH_TOKEN` | pyannote.audio speaker diarization (HuggingFace) |

### API Endpoint

```
POST /analyze-call
Content-Type: multipart/form-data

audio_file = <.wav | .mp3>
```

**Response (Phase 2 — raw diarized transcript):**

```json
{
  "status": "transcription_complete",
  "transcript": [
    {
      "speaker": "AGENT",
      "text": "You have an outstanding payment",
      "start_time": 0.0,
      "end_time": 3.2
    },
    {
      "speaker": "CUSTOMER",
      "text": "Salary late aaya hai, next week pay kar dunga",
      "start_time": 3.3,
      "end_time": 8.1
    }
  ]
}
```

### Running the server

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

> **Note:** `pydub` requires FFmpeg installed on the system. `pyannote.audio` requires a HuggingFace auth token (`HF_AUTH_TOKEN`).

## Pipeline Order (per RULES.md §6)

1. **Audio normalization** ← Phase 1 (implemented)
2. **STT + speaker diarization** ← Phase 2 (implemented)
3. Text cleanup & normalization
4. PII redaction (mandatory)
5. Financial NLP extraction
6. Risk & fraud signal computation
7. Summary generation
8. Structured JSON output to RAG
