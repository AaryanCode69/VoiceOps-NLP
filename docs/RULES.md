# 📘 RULES.md — VoiceOps (Call-Centric Risk & Fraud Intelligence)

## Purpose of This File

This document defines **non-negotiable rules** for implementing VoiceOps under the **call-level risk & fraud detection architecture**.
All generated code **must comply** with these rules.

---

## 1. SYSTEM GOAL (LOCKED)

VoiceOps analyzes a **single financial call** in isolation to detect:

* Customer intent
* Emotional state
* Strength of commitments
* Risk and fraud-like behavioral patterns

The system **does not** track customers over time and **does not** rely on historical identity.

---

## 2. CORE DESIGN PRINCIPLES

* Call-centric, not customer-centric
* Stateless NLP
* Speaker-aware analysis
* Explainable risk signals
* Compliance-safe (PII redaction mandatory)
* RAG used for **knowledge grounding**, not memory

---

## 3. INPUT CONTRACT

### API Input

```http
POST /analyze-call
Content-Type: multipart/form-data

audio_file = <wav | mp3>
```

### Input Rules

* Audio file is mandatory
* No customer_id, loan_id, or call_id is accepted
* No metadata is required
* Audio may be multilingual or code-switched

---

## 4. SPEECH-TO-TEXT (STT) RULES

### STT Provider Selection Logic (MANDATORY)

```text
If detected language ∈ {Hindi, Hinglish, Indian regional languages}
    → Use Sarvam AI STT
Else
    → Use OpenAI Whisper
```

### STT Requirements

* Language detection must occur before final STT selection
* Output must include:

  * Speaker diarization
  * Time-aligned utterances
* Speakers must be labeled as:

  * AGENT
  * CUSTOMER

---

## 5. SPEAKER RULES (CRITICAL)

* **ALL NLP, intent, sentiment, risk, and fraud signals MUST be derived ONLY from CUSTOMER speech**
* AGENT speech is contextual only
* Agent statements must never be treated as customer admissions

---

## 6. TEXT PROCESSING PIPELINE (MANDATORY ORDER)

1. Audio normalization
2. STT + speaker diarization
3. Text cleanup & normalization
4. **PII redaction (MANDATORY)**
5. Financial NLP extraction
6. Risk & fraud signal computation
7. Summary generation
8. Structured JSON output to RAG

Skipping or reordering steps is not allowed.

---

## 7. PII REDACTION RULES (NON-NEGOTIABLE)

Before **any storage, embedding, or RAG use**, redact:

* Credit / debit card numbers
* Bank account numbers
* Aadhaar / SSN
* OTPs
* Phone numbers
* Email addresses

### Example

```
"4500 1234 5678 9012" → "<CREDIT_CARD>"
```

No raw PII may appear in:

* Transcripts
* Summaries
* Embeddings
* RAG inputs

---

## 8. NLP EXTRACTION RULES

### 8.1 Intent Detection

* Enum-based
* Must include:

  * Confidence (0–1)
  * Conditionality (low | medium | high)

### 8.2 Sentiment Detection

* Financial-context sentiment only
* Must include confidence

### 8.3 Obligation Strength

* Classify commitment as:

  * strong
  * weak
  * conditional
  * none

### 8.4 Contradiction Detection

* Detect inconsistencies within the same call
* Binary output (true / false)

---

## 9. RISK & FRAUD SIGNAL ENGINE

Risk must be computed using **multiple signals**, not a single factor.

### Inputs

* Intent + confidence + conditionality
* Sentiment stability
* Obligation strength
* Contradictions
* Audio trust signals
* Behavioral patterns (evasion, urgency, deflection)

### Outputs

* Numerical risk score (0–100)
* Fraud likelihood (low | medium | high)
* Key contributing risk factors

---

## 10. RAG ROLE (STRICT)

RAG is used ONLY for:

* Grounding risk signals against known fraud patterns
* Aligning outputs with compliance & policy language
* Generating explanations and recommendations

RAG must NOT:

* Re-extract intent
* Re-score risk
* Analyze raw transcript
* Make accusations
* Track users

---

## 11. FINAL JSON FORMAT SENT TO RAG (LOCKED)

```json
{
  "call_context": {
    "call_language": "string",
    "call_quality": {
      "noise_level": "low | medium | high",
      "call_stability": "low | medium | high",
      "speech_naturalness": "normal | suspicious"
    }
  },

  "speaker_analysis": {
    "customer_only_analysis": true,
    "agent_influence_detected": false
  },

  "nlp_insights": {
    "intent": {
      "label": "enum",
      "confidence": 0.0,
      "conditionality": "low | medium | high"
    },

    "sentiment": {
      "label": "enum",
      "confidence": 0.0
    },

    "obligation_strength": "strong | weak | conditional | none",

    "entities": {
      "payment_commitment": "enum | null",
      "amount_mentioned": "number | null"
    },

    "contradictions_detected": true
  },

  "risk_signals": {
    "audio_trust_flags": ["enum"],
    "behavioral_flags": ["enum"]
  },

  "risk_assessment": {
    "risk_score": 0,
    "fraud_likelihood": "low | medium | high",
    "confidence": 0.0
  },

  "summary_for_rag": "string"
}
```

### JSON Rules

* All keys must always exist
* Optional values must be `null`, never omitted
* No extra fields allowed
* No PII allowed

---

## 12. OUTPUT GUARANTEES

* Deterministic structure
* Explainable signals
* No identity dependency
* No compliance violations
* Workflow-ready output

---

## 13. WHAT THIS SYSTEM MUST NEVER DO

❌ Track customer history
❌ Store raw transcripts with PII
❌ Accuse users of fraud
❌ Use agent speech as evidence
❌ Allow RAG to invent facts
❌ Depend on identity availability

---

## 14. ONE-LINE SYSTEM DEFINITION

> VoiceOps analyzes financial calls in real time to detect unreliable commitments and fraud-like patterns, grounding explainable risk signals against known knowledge using RAG.

---

## FINAL NOTE FOR GITHUB COPILOT

This file is a **hard constraint**.
If generated code violates this document, it is **incorrect by design**.
