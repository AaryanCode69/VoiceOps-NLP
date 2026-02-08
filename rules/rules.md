# 📘 VoiceOps – NLP & Primary Intelligence Rules

## Scope Owner

**Module:** Primary NLP Intelligence
**Owner:** NLP Engineer
**IDE:** Kiro
**Language:** Python
**Responsibility Boundary:** Ends at structured JSON + summary handoff

---

## 1. PURPOSE OF THIS MODULE

This module is responsible for converting a **financial call audio file** into **structured, explainable primary insights** and a **deterministic summary** that can be consumed by downstream systems.

This module **does not make final decisions** and **does not access historical data**.

---

## 2. INPUT CONTRACT

### Accepted Inputs

* Audio file (`.wav`, `.mp3`)
* Metadata:

  * `call_id`
  * `loan_id`
  * `customer_id`
  * `call_timestamp`

### Input Assumptions

* Audio may be multilingual or code-switched
* Audio may contain noise or filler words
* Metadata is trusted and provided externally

---

## 3. PROCESSING PIPELINE (MANDATORY ORDER)

### Step 1: Speech-to-Text

* Convert audio to text using a multilingual STT service
* Do not modify meaning
* Do not summarize at this stage

**Output:** Raw transcript

---

### Step 2: Text Cleanup & Normalization

* Remove filler words
* Normalize dates and numbers
* Standardize informal phrases
* Preserve semantic meaning

**Output:** Cleaned transcript (string)

---

### Step 3: Primary Insight Extraction (4 Contexts)

Each context is **independent** and must be executed separately.

#### Context 1: Intent Classification

* Choose exactly one intent from a fixed enum
* No free-text output allowed

#### Context 2: Sentiment Detection

* Detect emotion in a **financial context**
* Limited to predefined sentiment classes

#### Context 3: Entity Extraction

* Extract only explicitly mentioned entities
* Use `null` when entity is absent
* Never hallucinate values

#### Context 4: Risk Indicator Detection

* Detect signals of financial stress
* Indicators must map directly to transcript phrases

---

## 4. OUTPUT CONTRACT (STRICT)

### Final Output JSON (MANDATORY)

```json
{
  "call_id": "string",
  "loan_id": "string",
  "customer_id": "string",
  "call_timestamp": "ISO-8601 timestamp",

  "cleaned_transcript": "string",

  "primary_insights": {
    "intent": "enum",
    "sentiment": "enum",

    "entities": {
      "payment_commitment": "enum | null",
      "amount_mentioned": "number | null"
    },

    "risk_indicators": ["enum"]
  },

  "summary_for_embedding": "string"
}
```

---

## 5. SUMMARY GENERATION RULES (CRITICAL)

* Summary must be generated **inside this module**
* Summary must be:

  * Deterministic
  * Single sentence
  * Based only on extracted insights
* Summary is used **only for embedding and retrieval**
* Summary must NOT:

  * Introduce new facts
  * Contain speculation
  * Replace structured JSON

---

## 6. WHAT THIS MODULE MUST NOT DO

❌ Do not access SQL
❌ Do not access Vector DB
❌ Do not fetch historical data
❌ Do not assign final risk scores
❌ Do not make decisions
❌ Do not embed anything
❌ Do not trigger workflows
❌ Do not modify schemas downstream

This module **only produces signals**.

---

## 7. ERROR HANDLING RULES

* Module must never crash the pipeline
* On failure:

  * Return neutral defaults
  * Preserve schema shape

### Example Fallback

```json
{
  "sentiment": "neutral",
  "risk_indicators": []
}
```

---

## 8. CONNECTION TO THE REST OF THE SYSTEM

### Downstream Consumers

* Backend Service
* SQL Database (source of truth)
* Vector DB (summary embedding only)
* RAG Reasoning Layer
* n8n Workflow Engine

### How They Use This Output

* SQL stores the full JSON
* Vector DB embeds `summary_for_embedding`
* RAG reasons over structured JSON + retrieved summaries
* n8n triggers actions based on final decisions (not here)

---

## 9. DESIGN PRINCIPLES (NON-NEGOTIABLE)

* Determinism over creativity
* Structure over prose
* Explainability over prediction
* Separation of concerns
* Stability over optimization

---

## 10. ONE-SENTENCE MODULE DEFINITION

> “This module converts raw financial call audio into structured, explainable primary insights and a deterministic summary optimized for semantic retrieval.”

---

## 11. CHANGE POLICY

* Any schema change requires agreement with:

  * Backend owner
  * RAG owner
* No breaking changes without version bump

---

## ✅ FINAL NOTE FOR KIRO

This file should be used as:

* System context
* Guardrail
* Acceptance checklist

If output violates this document, it is **incorrect by design**.

---

