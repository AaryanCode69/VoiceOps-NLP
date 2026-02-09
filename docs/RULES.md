# VoiceOps — System Rules & Architectural Invariants

## 1. Purpose of This File

This document defines the **non-negotiable architectural rules** for the VoiceOps system.

All implementations (human or AI-assisted) **must strictly comply** with this file.
If any code violates these rules, it is **architecturally incorrect**, even if it “works”.

This file is the **single source of truth** for:

* Phase boundaries
* Tool responsibilities
* LLM usage
* Output contracts
* Compliance guarantees

---

## 2. Core Design Principles

1. **Each phase has exactly one responsibility**
2. **Acoustic problems are solved acoustically**
3. **Semantic problems are solved semantically**
4. **LLMs interpret; rules decide**
5. **Risk decisions are deterministic**
6. **No phase may leak responsibility**
7. **All outputs must be auditable and explainable**
8. **Speed and correctness are both first-class goals**

---

## 3. High-Level Pipeline

```
Audio Upload
  ↓
Phase 1: Audio Normalization
  ↓
Phase 2: Speech-to-Text (STT ONLY)
  ↓
Phase 3: Semantic Structuring (Translation + Role Attribution)
  ↓
Phase 4: Text Normalization & PII Redaction
  ↓
Phase 5: Sentiment Analysis
  ↓
Phase 6: Intent, Obligation & Contradiction Detection
  ↓
Phase 7: Risk & Fraud Signal Engine (Deterministic)
  ↓
Phase 8: Summary Generation (RAG Anchor)
  ↓
Final Structured JSON Output
```

---

## 4. Phase Responsibilities (STRICT)

---

### Phase 1 — Audio Upload & Normalization

**Responsibility**

* Accept audio input
* Normalize format (mono, sample rate)
* Detect basic call quality signals

**Allowed**

* Audio format conversion
* Noise estimation
* Call stability heuristics

**Forbidden**

* STT
* Translation
* NLP
* IDs
* Storage

---

### Phase 2 — Speech-to-Text (STT ONLY)

**Responsibility**
Convert audio → text **without interpretation**.

#### STT Routing Rules

* If language is **Indian native or Hinglish** → **Sarvam AI**
* Else → **Deepgram Nova-3**
* Whisper is allowed **ONLY as a fallback**

#### Hard Rules

* ❌ NO diarization
* ❌ NO speaker labels
* ❌ NO translation
* ❌ NO semantic inference

#### Output Contract

```json
[
  {
    "start_time": 0.0,
    "end_time": 4.2,
    "text": "raw transcribed text"
  }
]
```

---

### Phase 3 — Semantic Structuring (CRITICAL PHASE)

**Responsibility**
Convert raw transcript → structured conversation using **semantic reasoning**.

This phase **replaces all acoustic diarization**.

#### Responsibilities

1. Translate text to English **if required**
2. Split conversation into **AGENT vs CUSTOMER**
3. Attach confidence per utterance
4. Output structured JSON

#### Tooling

* OpenAI APIs are used here
* Multiple models may be evaluated
* Translation + role attribution occur in **one controlled step**

#### Rules

* ❌ No audio processing
* ❌ No diarization models
* ❌ No forced speaker assignment
* `"speaker": "unknown"` is allowed if confidence is low

#### Output

```json
[
  {
    "speaker": "CUSTOMER",
    "text": "My salary was delayed",
    "confidence": 0.82
  }
]
```

---

### Phase 4 — Text Normalization & PII Redaction

**Responsibility**
Make text compliance-safe.

#### Mandatory Redactions

* Credit cards
* Bank accounts
* OTPs
* Phone numbers
* Emails
* Government IDs

#### Rules

* Replace with tokens (`<OTP>`, `<CREDIT_CARD>`, etc.)
* Never store raw PII
* Never embed raw PII

---

### Phase 5 — Sentiment Analysis (CUSTOMER ONLY)

**Responsibility**
Detect emotional state in **financial context**.

#### Rules

* OpenAI only
* CUSTOMER utterances only
* No intent or risk inference

#### Allowed Labels

* calm
* neutral
* stressed
* anxious
* frustrated
* evasive

---

### Phase 6 — Intent, Obligation & Contradiction Detection

**Responsibility**
Understand **what the customer is doing**, not how risky it is.

#### Rules

* OpenAI for intent + contradiction detection
* Deterministic logic for obligation strength
* No risk scoring

#### Intent Labels

* repayment_promise
* repayment_delay
* refusal
* deflection
* information_seeking
* dispute
* unknown

---

### Phase 7 — Risk & Fraud Signal Engine (NO LLMs)

**Responsibility**
Convert structured signals → risk.

#### Rules

* 100% deterministic
* No LLMs
* No raw text
* Transparent weighting

#### Output

```json
{
  "risk_score": 78,
  "fraud_likelihood": "high",
  "confidence": 0.81
}
```

---

### Phase 8 — Summary Generation (RAG Anchor)

**Responsibility**
Generate a **single-sentence**, neutral summary for embedding.

#### Rules

* OpenAI allowed
* Structured inputs only
* No raw transcript
* No accusations
* Exactly one sentence

---

## 5. Identity & Persistence Rules

* `call_id` is generated **only by backend persistence**
* NLP services are **stateless**
* Metadata may be optional at ingestion
* No phase assumes identity existence

---

## 6. LLM Usage Rules (GLOBAL)

LLMs MAY:

* Translate
* Attribute roles
* Detect sentiment
* Detect intent
* Detect contradictions
* Generate summaries

LLMs MUST NOT:

* Assign risk or fraud
* Make legal assertions
* Invent facts
* Store data
* Bypass deterministic logic

---

## 7. RAG Rules

* Only Phase 8 summaries may be embedded
* Full JSON is stored in structured storage
* Vector DB must NEVER contain:

  * Raw transcript
  * PII
  * Risk scores
  * Agent statements

---

## 8. Performance Rules

* Long audio MUST be chunked
* STT MUST be parallelized
* No phase blocks the entire pipeline
* Partial failure is allowed with confidence degradation

---

## 9. Copilot / AI Assistant Rules

* Always generate an execution plan first
* Never expand phase scope
* Never merge phase responsibilities
* If unsure → STOP and refer to this file

---

## 10. Final Output Contract (MANDATORY)

### Purpose

Defines the **only valid final JSON output** of VoiceOps.

No phase may:

* Rename fields
* Remove sections
* Add speculative fields
* Change nesting

---

### Final JSON Output Schema (LOCKED)

```json
{
  "call_context": {
    "call_language": "hinglish",
    "call_quality": {
      "noise_level": "medium",
      "call_stability": "low",
      "speech_naturalness": "suspicious"
    }
  },

  "speaker_analysis": {
    "customer_only_analysis": true,
    "agent_influence_detected": false
  },

  "nlp_insights": {
    "intent": {
      "label": "repayment_promise",
      "confidence": 0.6,
      "conditionality": "high"
    },

    "sentiment": {
      "label": "stressed",
      "confidence": 0.82
    },

    "obligation_strength": "weak",

    "entities": {
      "payment_commitment": "next_week",
      "amount_mentioned": null
    },

    "contradictions_detected": true
  },

  "risk_signals": {
    "audio_trust_flags": [
      "low_call_stability",
      "unnatural_speech_pattern"
    ],

    "behavioral_flags": [
      "conditional_commitment",
      "evasive_responses",
      "statement_contradiction"
    ]
  },

  "risk_assessment": {
    "risk_score": 78,
    "fraud_likelihood": "high",
    "confidence": 0.81
  },

  "summary_for_rag": "Customer made a conditional repayment promise, showed stress, and contradicted earlier statements, which aligns with known high-risk call patterns."
}
```

---

## 11. Section Ownership by Phase

| Section                              | Phase     |
| ------------------------------------ | --------- |
| call_context                         | Phase 1–2 |
| speaker_analysis                     | Phase 3   |
| nlp_insights.sentiment               | Phase 5   |
| nlp_insights.intent                  | Phase 6   |
| nlp_insights.entities                | Phase 6   |
| nlp_insights.contradictions_detected | Phase 6   |
| risk_signals                         | Phase 7   |
| risk_assessment                      | Phase 7   |
| summary_for_rag                      | Phase 8   |

---

## 12. Final Architectural Assertion

> **VoiceOps treats voice as probabilistic signal,
> language as contextual evidence,
> and risk as a deterministic outcome.**

Any implementation violating this document is incorrect.


