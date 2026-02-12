Here is the comprehensive README for the entire VoiceOps ecosystem. It unifies the **NLP Signal Engine** (Audio Processing) and the **RAG Intelligence Engine** (Reasoning & Storage) into a single, cohesive documentation structure.

---

# VoiceOps — Call-Centric Risk & Fraud Intelligence

> VoiceOps analyzes financial calls in real time to detect unreliable commitments and fraud-like patterns, grounding explainable risk signals against known knowledge using RAG.

## Rag Pipeline [](https://github.com/raghavvag/VoiceOPs_Rag_Pipeline)

[https://github.com/raghavvag/VoiceOPs_Rag_Pipeline](https://github.com/raghavvag/VoiceOPs_Rag_Pipeline)

## Frontend [](https://github.com/kriti11m/VoiceOps_frontend.git)

[https://github.com/kriti11m/VoiceOps_frontend.git](https://github.com/kriti11m/VoiceOps_frontend.git)

---

<p align="center">
<img src="[https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)" />
<img src="[https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)" />
<img src="[https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=for-the-badge&logo=openai&logoColor=white](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=for-the-badge&logo=openai&logoColor=white)" />
<img src="[https://img.shields.io/badge/Supabase-pgvector-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white](https://img.shields.io/badge/Supabase-pgvector-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white)" />
<img src="[https://img.shields.io/badge/Sarvam_AI-Indian_Lang-FF6B6B?style=for-the-badge](https://www.google.com/search?q=https://img.shields.io/badge/Sarvam_AI-Indian_Lang-FF6B6B%3Fstyle%3Dfor-the-badge)" />
</p>

<h1 align="center">🎙️ VoiceOps System Architecture</h1>

VoiceOps is a dual-engine platform designed for financial compliance and risk detection. It consists of two major subsystems:

1. **NLP Signal Engine:** Processes raw audio, handles diarization, redacts PII, and extracts deterministic risk signals.
2. **RAG Intelligence Engine:** Ingests signals, retrieves fraud patterns/compliance rules, and generates grounded, auditor-friendly reasoning.

---

## 🏗️ High-Level System Architecture

```mermaid
graph TD
    User[Agent/System] -->|Upload Audio .wav/.mp3| API[NLP Engine API]
    
    subgraph "NLP Signal Engine (Phases 1-8)"
        API --> Norm[Audio Normalizer]
        Norm --> Route{Language Router}
        Route -->|Indian Langs| Sarvam[Sarvam AI STT]
        Route -->|Global| Whisper[OpenAI Whisper]
        Sarvam & Whisper --> Diar[Speaker Diarization]
        Diar --> PII[PII Redaction]
        PII --> NLP[NLP Extraction]
        NLP --> Risk[Deterministic Risk Scorer]
        Risk --> Sum[Summary Generator]
    end
    
    subgraph "RAG Intelligence Engine"
        Sum --> Vector[Vector Embedding]
        Vector --> Search{pgvector Search}
        Search -->|Retrieve| KB[Knowledge Base]
        KB --> Context[Context Builder]
        Context --> LLM[GPT-4o Reasoning]
        LLM --> Audit[Backboard AI Audit Trail]
        LLM --> DB[(Supabase Storage)]
    end
    
    DB --> Dashboard[Frontend Dashboard]
    DB --> Chat[RAG Chatbot]
    DB --> PDF[PDF Reports]

```

---

## 🛠 Tech Stack

### NLP & Audio Processing

* **Audio:** `ffmpeg`, `pydub`, `pyannote.audio` (Speaker Diarization)
* **STT:** OpenAI Whisper (Global), Sarvam AI `saaras:v2` (Indian Regional)
* **NLP:** `spacy`, OpenAI `gpt-4o-mini` (Extraction)
* **Safety:** Local Regex PII Redaction (Zero-trust)

### RAG & Infrastructure

* **Framework:** FastAPI 0.115.6
* **Database:** Supabase (PostgreSQL + pgvector)
* **LLM:** OpenAI GPT-4o / GPT-4o-mini
* **Embeddings:** `text-embedding-3-small` (1536-dim)
* **Memory/Audit:** Backboard AI
* **Reporting:** `fpdf2` for PDF generation

---

## 🧩 Part 1: The NLP Signal Engine

**Goal:** Convert raw audio into structured, safe, and scored JSON data.

### Pipeline Phases

| Phase | Component | Functionality |
| --- | --- | --- |
| **1** | **Upload & Norm** | Validates `.wav`/`.mp3`, converts to mono 16kHz. |
| **2** | **STT Routing** | Detects language. Routes **Hindi/Regional** to Sarvam AI, others to Whisper. |
| **3** | **Diarization** | Separates `AGENT` vs `CUSTOMER`. Merges fragments. **Guarantee:** Timestamps are chronological. |
| **4** | **PII Redaction** | **Mandatory Safety Layer.** Redacts Credit Cards, Aadhaar, OTPs, Phones locally. |
| **5** | **Sentiment** | Classifies customer emotion (stressed, evasive) in financial context. |
| **6** | **Intent/Logic** | Extracts `repayment_promise`, `refusal`, and detects contradictions. |
| **7** | **Risk Scoring** | **Deterministic Scorer.** Calculates 0-100 risk score based on weighted signals. |
| **8** | **Summarization** | Generates a safe, single-sentence summary for RAG embedding. |

### Key Guarantees

1. **Zero Raw PII:** No PII ever leaves Phase 4.
2. **Deterministic Scoring:** Risk scores are math-based, not LLM-hallucinated.
3. **Indian Language Support:** First-class support for Hinglish, Tamil, Telugu via Sarvam.

### API Output (The Input for RAG)

```json
{
  "risk_score": 78,
  "fraud_likelihood": "high",
  "key_risk_factors": ["conditional_commitment", "contradictory_statements"],
  "summary_for_rag": "Customer expressed a request to delay repayment with conditional commitment...",
  "transcript": [...]
}

```

---

## 🧠 Part 2: The RAG Intelligence Engine

**Goal:** Ground the NLP signals against legal/fraud knowledge and generate explainable audits.

### Core RAG Workflow (10 Steps)

The pipeline executes these steps for every analyzed call:

1. **Validate Payload:** Accepts output from NLP Engine.
2. **Store Record:** Creates entry in `call_analyses` (Supabase).
3. **Embed Summary:** Converts Phase 8 summary to 1536-dim vector.
4. **Retrieve Knowledge:** Searches 3 distinct knowledge categories:
* *Fraud Patterns* (Top 3)
* *Compliance Rules* (Top 2)
* *Risk Heuristics* (Top 2)


5. **Build Context:** Combines Call Signals + Matched Knowledge.
* *Audit:* Logs context to **Backboard AI** for traceability.


6. **Grounded Reasoning:** GPT-4o generates assessment.
* *Constraint:* Must cite specific knowledge patterns (e.g., `[fp_001]`).


7. **Store Output:** Updates database with reasoning.
8. **Status Assignment:** Sets `escalated` or `resolved` based on score.
9. **Document Extraction:** Extracts structured entities (Commitments, EMI dates) for the PDF report.
10. **Final Response:** Returns complete analysis package.

### Knowledge Base Architecture

The system uses `pgvector` for similarity search.

| Category | Description | Example |
| --- | --- | --- |
| **Fraud Pattern** | Known deceptive behaviors | `[fp_001]` Conditional Promise with Contradiction |
| **Compliance** | Regulatory guidelines | `[cr_005]` RBI Fair Practices Code |
| **Heuristics** | Statistical risk indicators | `[rh_002]` High stress + Evasive intent correlation |

### Chatbot System

A RAG-powered chatbot allows auditors to query the call data.

* **Temporal Queries:** "Show me calls from last week."
* **Pattern Queries:** "Which calls matched the 'Third-Party Impersonation' pattern?"

---

## 📂 Project Structure

```
.
├── nlp_engine/               # The Signal Processing Pipeline
│   ├── src/
│   │   ├── audio/            # Normalization
│   │   ├── stt/              # Whisper & Sarvam Clients
│   │   ├── nlp/              # PII, Sentiment, Intent
│   │   └── risk/             # Deterministic Scorer
│   └── docs/RULES.md         # Non-negotiable system rules
│
├── rag_pipeline/             # The Intelligence Pipeline
│   ├── app/
│   │   ├── services/         # Embedding, Retrieval, Backboard AI
│   │   └── db/               # Supabase & pgvector queries
│   ├── knowledge/            # JSON definitions of Fraud Patterns
│   └── sql/                  # Database migration scripts
│
└── frontend/                 # Next.js Dashboard

```

---

## 🚀 Setup & Installation

### Prerequisites

* Python 3.11+
* FFmpeg (for audio processing)
* Supabase Account (with `pgvector` enabled)
* OpenAI API Key & Sarvam AI API Key

### 1. Environment Configuration

Create a `.env` file covering both engines:

```env
# --- NLP Engine ---
OPENAI_API_KEY=sk-...
SARVAM_API_KEY=...
HF_AUTH_TOKEN=...       # For pyannote.audio

# --- RAG Engine ---
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
EMBEDDING_MODEL=text-embedding-3-small
BACKBOARD_API_KEY=...

```

### 2. Database Initialization (RAG)

Run the SQL scripts in `rag_pipeline/sql/` in your Supabase SQL Editor:

1. `init.sql`: Creates tables and RPC functions.
2. `migrate_chatbot.sql`: Enables chat vector search.

### 3. Knowledge Seeding

Populate the vector database with the definitions:

```bash
curl -X POST http://localhost:8000/api/v1/knowledge/seed

```

### 4. Running the Services

**Start the NLP Engine:**

```bash
cd nlp_engine
pip install -r requirements.txt
uvicorn main:app --port 8001

```

**Start the RAG Engine:**

```bash
cd rag_pipeline
pip install -r requirements.txt
uvicorn main:app --port 8000

```

---

## 📊 Example Workflow

1. **Input:** An audio file of a debt collection call in Hindi mixed with English.
2. **NLP Processing:**
* Detects "Hinglish".
* Transcribes: *"Haan main pay kar dunga but salary late hai"* (Customer).
* Scores Risk: **72/100** (High Conditionality).


3. **RAG Processing:**
* Embeds summary.
* Retrieves pattern `[fp_001] Conditional Promise`.
* LLM concludes: *"High risk. Customer language matches pattern fp_001. Contradiction detected between promise and ability."*


4. **Output:** A PDF report is generated with the transcript, risk score, and specific regulatory flags.

---

<p align="center">
Built for <strong>DevSoc'26</strong>
</p>
