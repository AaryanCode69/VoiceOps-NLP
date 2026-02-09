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

**Phase 8** — RAG summary generation.

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

### What Phase 3 implements

| File | Purpose |
|---|---|
| `src/stt/diarizer_validator.py` | Validates raw diarized transcript: checks speaker labels, timestamps, and text; normalizes labels to AGENT / CUSTOMER |
| `src/stt/utterance_structurer.py` | Merges consecutive same-speaker fragments, drops artifacts, and produces clean ordered utterance list |

### Phase 3 — Diarization Guarantees

After Phase 3 processing, the utterance list satisfies the following invariants:

- **Every utterance has a valid speaker label** — only `"AGENT"` or `"CUSTOMER"` (per RULES.md §5)
- **Utterances are chronologically ordered** by `start_time`
- **No empty or null text** — all text fields are non-empty after whitespace stripping
- **No invalid timestamps** — `start_time >= 0` and `end_time > start_time` for every utterance
- **Diarization artifacts are cleaned** — consecutive same-speaker fragments separated by ≤ 0.3s are merged; extremely short fragments with no meaningful text are dropped
- **AGENT utterances are preserved** — no speaker's utterances are discarded
- **Text content is NOT modified semantically** — only whitespace-trimmed and concatenated during merges
- **No NLP, scoring, PII redaction, or identifiers** are present in the output

### What Phase 4 implements

| File | Purpose |
|---|---|
| `src/nlp/normalizer.py` | Removes filler words, normalizes spoken contractions to written form, collapses whitespace — without altering semantic meaning |
| `src/nlp/pii_redactor.py` | Detects and redacts credit/debit cards, bank accounts, Aadhaar/SSN, OTPs, phone numbers, and emails with safe tokens |
| `src/nlp/__init__.py` | Exposes `normalize_and_redact()` — the Phase 4 pipeline entry point (normalize → redact) |

### Phase 4 — PII Safety Guarantees

After Phase 4 processing, the utterance list satisfies the following invariants:

- **No raw PII in output** — all detected PII is replaced with redaction tokens before any downstream use
- **Redaction tokens used:** `<CREDIT_CARD>`, `<BANK_ACCOUNT>`, `<GOVT_ID>`, `<OTP>`, `<PHONE_NUMBER>`, `<EMAIL>`
- **Redaction is mandatory** — per RULES.md §7, no raw PII may appear in transcripts, summaries, embeddings, or RAG inputs
- **Text normalization preserves meaning** — only filler words (uh, um, hmm) are removed and spoken forms (gonna → going to) are expanded; no semantic distortion
- **Speaker labels and timestamps are unchanged** — only the `text` field is modified
- **No utterances are dropped or added** — every Phase 3 utterance passes through
- **Output is deterministic** — same input always produces same output
- **No external API calls** — all processing is local regex-based pattern matching
- **No downstream logic** — no intent, sentiment, risk, scores, or identifiers are introduced

### What Phase 5 implements

| File | Purpose |
|---|---|
| `src/nlp/sentiment.py` | Classifies financial-context sentiment from CUSTOMER utterances using OpenAI API; returns label + confidence |

### Phase 5 — Sentiment Scope & Limitations

- **CUSTOMER utterances only** — AGENT speech is never analyzed for sentiment (per RULES.md §5)
- **Input must be Phase 4 output** — utterances must be normalized and PII-redacted before sentiment analysis
- **Financial context** — sentiment is classified in the context of financial calls (debt, payments, obligations), not general conversation
- **Allowed labels:** `calm`, `neutral`, `stressed`, `anxious`, `frustrated`, `evasive` — no other labels are produced
- **Confidence score:** 0.0–1.0 float representing classifier certainty
- **OpenAI API required** — uses `gpt-4o-mini` with `temperature=0.0` for deterministic output
- **No fallback logic** — if OpenAI is unavailable, the call fails (no local heuristic)
- **Default behavior:** if no CUSTOMER utterances exist, returns `{"label": "neutral", "confidence": 0.0}`
- **No downstream logic** — no intent, risk, fraud scores, summaries, or identifiers are produced

### Phase 5 — Output Format

```json
{
  "label": "stressed",
  "confidence": 0.82
}
```

### What Phase 6 implements

| File | Purpose |
|---|---|
| `src/nlp/intent.py` | Classifies customer intent in a financial context using OpenAI API; returns label + confidence + conditionality |
| `src/nlp/obligation.py` | Derives obligation strength deterministically from intent label, conditionality, and linguistic markers — no LLM |
| `src/nlp/contradictions.py` | Detects within-call contradictions in CUSTOMER speech using OpenAI API; returns boolean |

### Phase 6 — Scope & Limitations

- **CUSTOMER utterances only** — AGENT speech is never analyzed (per RULES.md §5)
- **Input must be Phase 4 output** — utterances must be normalized and PII-redacted
- **Intent labels (enum):** `repayment_promise`, `repayment_delay`, `refusal`, `deflection`, `information_seeking`, `dispute`, `unknown` — no other labels are produced
- **Conditionality levels:** `low`, `medium`, `high`
- **Confidence score:** 0.0–1.0 float
- **Obligation strength:** `strong`, `weak`, `conditional`, `none` — derived deterministically from intent + conditionality + linguistic markers
- **Contradiction detection:** binary true/false for within-call inconsistencies only; requires ≥2 CUSTOMER utterances
- **OpenAI API required** — intent and contradiction detection use `gpt-4o-mini` with `temperature=0.0`
- **No downstream logic** — no risk scores, fraud likelihood, summaries, explanations, or identifiers are produced
- **No sentiment** — sentiment is handled by Phase 5; Phase 6 does not re-analyze it

### Phase 6 — Output Format

```json
{
  "intent": {
    "label": "repayment_delay",
    "confidence": 0.85,
    "conditionality": "medium"
  },
  "obligation_strength": "conditional",
  "contradictions_detected": false
}
```

### What Phase 7 implements

| File | Purpose |
|---|---|
| `src/risk/signals.py` | Defines typed signal structures for all risk inputs; validates and bundles upstream outputs (sentiment, intent, obligation, contradictions, audio trust) |
| `src/risk/scorer.py` | Deterministic weighted risk scorer — computes risk score (0–100), fraud likelihood, confidence, and key contributing risk factors |

### Phase 7 — Risk Scoring Philosophy

- **Multi-signal aggregation** — Risk is computed from six independent signal dimensions: sentiment, intent, conditionality, obligation strength, contradictions, and audio trust. No single factor can dominate the risk score alone.
- **Deterministic** — No LLMs, no randomness, no probabilistic sampling. Same inputs always produce identical outputs.
- **Transparent weighting** — Each signal dimension has a configurable weight (default weights sum to 1.0). Sub-scores are computed independently in [0, 100] and combined via weighted sum.
- **Threshold-based fraud classification** — Fraud likelihood is derived from fixed score thresholds: `high` (≥65), `medium` (≥35), `low` (<35). Thresholds are configurable.
- **Traceable risk factors** — Each flagged risk factor maps directly to an input signal dimension that exceeded a sub-score threshold, ensuring every factor is explainable from the inputs.
- **No downstream logic** — Phase 7 does not generate explanations, summaries, or identifiers. It does not call RAG, store data, or make business decisions.

### Phase 7 — Signal Dimensions & Weights

| Dimension | Weight | What it measures |
|---|---|---|
| Sentiment | 0.20 | Emotional risk from customer sentiment (evasive/stressed = high) |
| Intent | 0.20 | Risk inherent in the classified intent (refusal/deflection = high) |
| Conditionality | 0.15 | How hedged or conditional the customer's statements are |
| Obligation | 0.15 | Strength of customer's commitment (none/conditional = high risk) |
| Contradictions | 0.15 | Whether within-call contradictions were detected |
| Audio trust | 0.15 | Audio quality signals (suspicious naturalness = high risk) |

### Phase 7 — Output Format

```json
{
  "risk_score": 78,
  "fraud_likelihood": "high",
  "confidence": 0.81,
  "key_risk_factors": [
    "conditional_commitment",
    "contradictory_statements",
    "high_emotional_stress"
  ]
}
```

### What Phase 8 implements

| File | Purpose |
|---|---|
| `src/rag/summary_generator.py` | Generates a single-sentence, embedding-safe summary from Phase 6 + Phase 7 structured outputs; OpenAI with deterministic template fallback |

### Phase 8 — Summary Generation for RAG

- **Input:** Structured outputs only — intent label, conditionality, obligation strength, contradictions (Phase 6) and risk score, fraud likelihood, key risk factors (Phase 7)
- **Output:** Exactly one sentence suitable for semantic embedding
- **No raw transcript:** Summary is derived exclusively from structured signals, never from raw text
- **OpenAI usage:** `gpt-4o-mini` with `temperature=0.0`, constrained prompt enforcing neutral language, one sentence, no new facts
- **Deterministic fallback:** If OpenAI is unavailable or returns invalid output, a template-based summary is generated deterministically
- **Summary constraints:** No PII, no identifiers, no numeric scores, no accusatory language, no recommendations
- **Banned words:** "fraudster", "lied", "scam", "criminal", "guilty", "dishonest", etc. are never used
- **Deterministic:** Same structured inputs always produce identical template-based output
- **No downstream logic:** Phase 8 does not store data, call RAG, embed, or generate identifiers

### Phase 8 — Output Format

A single string:

```
"Customer expressed a request to delay repayment with conditional commitment, showing moderate conditionality and conditional commitment patterns, indicating moderate risk and warranting closer attention."
```

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
3. **Diarization validation + utterance structuring** ← Phase 3 (implemented)
4. **Text cleanup & normalization** ← Phase 4 (implemented)
5. **PII redaction (mandatory)** ← Phase 4 (implemented)
6. **Financial NLP extraction (sentiment)** ← Phase 5 (implemented)
7. **Financial NLP extraction (intent, obligations, contradictions)** ← Phase 6 (implemented)
8. **Risk & fraud signal computation** ← Phase 7 (implemented)
9. **Summary generation** ← Phase 8 (implemented)
10. Structured JSON output to RAG
