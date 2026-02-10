# VoiceOps AI — Intelligent Call Analytics Platform

## Pitch Deck for Faculty Review

---

## 🎯 Problem Statement

Contact centers handle thousands of calls daily, but **manual quality auditing** covers only 2–5% of calls. This leads to:

- Missed compliance violations
- Undetected customer dissatisfaction
- Inconsistent agent performance evaluation
- No structured data extraction from conversations

**VoiceOps AI** automates the entire call audit pipeline — from raw audio to structured risk reports — using a multi-phase NLP and audio intelligence pipeline.

---

## 🏗️ System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT / WEBHOOK                             │
│          POST /api/v1/analyze-call  (audio file upload)             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     PHASE 1: AUDIO INGESTION                        │
│  • Validate file format (WAV, MP3, FLAC, OGG, WEBM, M4A)          │
│  • FFmpeg probe for duration, sample rate, channels                 │
│  • Convert to 16kHz mono WAV via FFmpeg                             │
│  • Chunking support for files > 10 minutes                          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  PHASE 2: LANGUAGE DETECTION                        │
│  • Extract first 30 seconds of audio via FFmpeg                     │
│  • Send sample to Whisper for language identification               │
│  • Determine primary language (Hindi, English, etc.)                │
│  • Route to appropriate STT engine                                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 3: SPEECH-TO-TEXT TRANSCRIPTION                   │
│  • Deepgram Nova-2 for English calls                                │
│  • Sarvam AI (saarika:v2) for Hindi/Indic calls                    │
│  • Word-level timestamps and confidence scores                      │
│  • Automatic punctuation and smart formatting                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 4: SPEAKER DIARIZATION                           │
│  • Pyannote.audio 3.1 neural speaker segmentation                   │
│  • Identify distinct speakers and their time boundaries             │
│  • Map each transcript word to a speaker via timestamp overlap      │
│  • Agent vs Customer role assignment (first-speaker heuristic)      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 5: TRANSCRIPT STRUCTURING                        │
│  • Merge word-level tokens into speaker turns                       │
│  • Collapse consecutive same-speaker segments                       │
│  • Produce final dialogue: Speaker, Text, Start, End                │
│  • Calculate per-speaker talk-time ratios                           │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 6: ENTITY EXTRACTION (NLP)                       │
│  • Names — regex patterns + spaCy NER (PERSON entities)             │
│  • Phone numbers — Indian 10-digit pattern matching                 │
│  • Email addresses — RFC-style regex extraction                     │
│  • Dates — dateutil + multi-format regex parsing                    │
│  • Monetary amounts — ₹/Rs/INR pattern + word-to-number            │
│  • Addresses — Indian PIN code anchored extraction                  │
│  • Policy/Reference numbers — alphanumeric pattern detection        │
│  • Products/Services — keyword dictionary lookup                    │
│  • Organization names — spaCy ORG entity recognition                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 7: SENTIMENT & EMOTION ANALYSIS                  │
│  • Per-utterance sentiment via transformer model                    │
│  • Emotion detection (anger, frustration, satisfaction, neutral)    │
│  • Sentiment arc tracking across the call                           │
│  • Escalation moment detection (sentiment polarity shifts)          │
│  • Overall call sentiment aggregation                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 8: COMPLIANCE & RISK SCORING                     │
│  • Rule-based checklist validation (greeting, disclosure, closing)  │
│  • Prohibited phrase detection (abusive/misleading language)        │
│  • Required phrase verification (regulatory disclosures)            │
│  • Risk score computation (weighted violations)                     │
│  • Flag generation with severity levels                             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 9: CALL SUMMARIZATION                            │
│  • Abstractive summary generation                                   │
│  • Key topics and action items extraction                           │
│  • Resolution status detection                                      │
│  • Callback/follow-up identification                                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 10: FINAL REPORT ASSEMBLY                        │
│  • Merge all phase outputs into unified JSON report                 │
│  • POST report to configured webhook URL                            │
│  • Return structured response to client                             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 🔬 Deep Dive: Each Phase

---

### Phase 1: Audio Ingestion & Preprocessing

**File:** `src/audio/preprocessing.py`

**What happens:**

1. **Format Validation**: The system accepts WAV, MP3, FLAC, OGG, WEBM, and M4A files. The MIME type and extension are validated before processing.

2. **FFmpeg Probe**: We use `ffprobe` (FFmpeg's analysis tool) to extract audio metadata without decoding the entire file:
   - Duration in seconds
   - Sample rate (e.g., 44100 Hz, 16000 Hz)
   - Number of channels (mono/stereo)
   - Codec information

3. **Audio Normalization**: All audio is converted to a **standard format** using FFmpeg:
   ```
   ffmpeg -i input.mp3 -ar 16000 -ac 1 -f wav output.wav
   ```
   - **16kHz sample rate** — optimal for speech recognition models
   - **Mono channel** — diarization and STT work on single-channel audio
   - **WAV format** — uncompressed PCM for maximum STT accuracy

4. **Chunking** (if `ENABLE_CHUNKING=true`): For calls longer than 10 minutes, the audio is split into overlapping chunks to stay within STT API limits. Chunks are later stitched using timestamp alignment.

**Why FFmpeg?**
FFmpeg handles the widest range of audio codecs and container formats. It performs sample rate conversion using high-quality sinc interpolation, and channel downmixing preserves both sides of a stereo call recording.

---

### Phase 2: Language Detection

**File:** `src/stt/language_detect.py`

**What happens:**

1. **Sample Extraction**: FFmpeg extracts the **first 30 seconds** of the normalized audio:
   ```
   ffmpeg -i full_audio.wav -t 30 -f wav sample.wav
   ```
   30 seconds provides enough speech content for reliable detection while keeping the API call fast.

2. **Whisper-based Detection**: The 30-second sample is sent to Whisper's transcription endpoint with the purpose of language identification. Whisper's encoder produces language probability scores across 99 languages.

3. **Language Routing Decision**:
   - If detected language is **English** → route to Deepgram Nova-2
   - If detected language is **Hindi** or other Indic language → route to Sarvam AI
   - Confidence threshold check — if below threshold, default to English pipeline

**Why detect first?**
Different STT engines excel at different languages. Deepgram Nova-2 leads in English accuracy, while Sarvam AI is purpose-built for Indian languages with code-switching support (Hinglish).

---

### Phase 3: Speech-to-Text Transcription

**Files:** `src/stt/deepgram_stt.py`, `src/stt/sarvam_stt.py`

#### Deepgram Path (English):

1. Audio is sent to Deepgram's Nova-2 model via REST API
2. Configuration:
   - `model=nova-2` — latest general English model
   - `smart_format=true` — adds punctuation, capitalization, numerals
   - `utterances=true` — groups words into natural utterances
   - `diarize=false` — we handle diarization separately with Pyannote for better accuracy
3. Response contains **word-level timestamps**: each word has `start`, `end`, `confidence`, and `word` fields

#### Sarvam AI Path (Hindi/Indic):

1. Audio is sent to Sarvam AI's `saarika:v2` model
2. The API is called with `language_code` set based on Phase 2 detection
3. For large files, audio is chunked and transcribed in parts
4. Returns transcript with timestamps at the sentence/segment level

**Output Schema:**
```json
{
  "transcript": "Hello, thank you for calling...",
  "words": [
    {"word": "Hello", "start": 0.0, "end": 0.45, "confidence": 0.98},
    {"word": "thank", "start": 0.50, "end": 0.72, "confidence": 0.97}
  ],
  "language": "en"
}
```

---

### Phase 4: Speaker Diarization (Who Spoke When)

**File:** `src/audio/diarization.py`

**Technology:** Pyannote.audio 3.1 (`pyannote/speaker-diarization-3.1`)

**What happens:**

1. **Neural Speaker Segmentation**: Pyannote loads the pre-trained neural pipeline from HuggingFace. The model consists of:
   - **Segmentation model**: A PyanNet architecture (SincNet + LSTM) that processes the audio in sliding windows and outputs frame-level speaker activity probabilities
   - **Embedding model**: Extracts x-vector speaker embeddings for each detected speech segment
   - **Clustering**: Agglomerative clustering groups embeddings into distinct speaker identities

2. **Pipeline Execution**:
   ```python
   pipeline = Pipeline.from_pretrained(
       "pyannote/speaker-diarization-3.1",
       use_auth_token=HF_TOKEN
   )
   diarization = pipeline(audio_file)
   ```

3. **Output**: A list of time-stamped speaker segments:
   ```
   SPEAKER_00: [0.5s → 4.2s]
   SPEAKER_01: [4.5s → 8.1s]
   SPEAKER_00: [8.3s → 12.0s]
   ```

4. **Word-to-Speaker Mapping**: Each word from Phase 3 (with its timestamp) is assigned to a speaker by finding which diarization segment it falls within:
   ```
   For each word:
       word_midpoint = (word.start + word.end) / 2
       Find segment where segment.start <= word_midpoint <= segment.end
       Assign word.speaker = segment.speaker
   ```

5. **Agent vs Customer Assignment** (First-Speaker Heuristic):
   - In typical call center recordings, the **agent speaks first** (greeting)
   - `SPEAKER_00` (first speaker detected) → **Agent**
   - `SPEAKER_01` → **Customer**
   - This heuristic is configurable and can be overridden via API parameters

**Why Pyannote over Deepgram's built-in diarization?**
Pyannote's neural pipeline provides significantly better speaker separation accuracy, especially on:
- Overlapping speech segments
- Short utterances ("yes", "okay")
- Indian-accented English and Hindi audio

---

### Phase 5: Transcript Structuring

**File:** `src/nlp/structuring.py`

**What happens:**

1. **Turn Merging**: Consecutive words from the same speaker are merged into a single utterance:
   ```
   Before:
     Agent: "Hello"  Agent: "thank"  Agent: "you"  Agent: "for"  Agent: "calling"
   After:
     Agent: "Hello thank you for calling" [0.0s → 2.1s]
   ```

2. **Turn Collapse**: If the same speaker has multiple adjacent segments (due to diarization micro-segments), they are collapsed into one continuous turn.

3. **Dialogue Format**:
   ```json
   [
     {"speaker": "Agent", "text": "Hello, thank you for calling VoiceOps.", "start": 0.0, "end": 2.1},
     {"speaker": "Customer", "text": "Hi, I have an issue with my policy.", "start": 2.5, "end": 5.3},
     {"speaker": "Agent", "text": "Sure, can I have your policy number?", "start": 5.8, "end": 8.0}
   ]
   ```

4. **Talk-Time Metrics**:
   - Agent talk-time: sum of all Agent segment durations
   - Customer talk-time: sum of all Customer segment durations
   - Talk ratio: Agent% vs Customer%
   - Silence/dead-air detection: gaps between segments > 3 seconds

---

### Phase 6: Entity Extraction

**File:** `src/nlp/entity_extraction.py`

This is a **hybrid approach** combining regex pattern matching, spaCy NER, and domain-specific rules. No external LLM API is used here — everything runs locally.

#### Entity Types and Extraction Logic:

| Entity | Method | Details |
|--------|--------|---------|
| **Person Names** | spaCy NER (`en_core_web_sm`) | Extracts `PERSON` entities; filters out common false positives like "Sir", "Ma'am" |
| **Phone Numbers** | Regex | Pattern: `[6-9]\d{9}` for Indian mobiles; also catches `+91` prefixed numbers and landlines |
| **Email Addresses** | Regex | Standard RFC pattern: `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}` |
| **Dates** | Regex + dateutil | Multiple patterns: `DD/MM/YYYY`, `DD-MM-YYYY`, `Month DD YYYY`, relative dates ("yesterday", "last Monday") parsed via `dateutil.parser` |
| **Monetary Amounts** | Regex | Patterns for `₹`, `Rs.`, `Rs`, `INR`, followed by numeric values; handles lakhs/crores notation and word-form numbers |
| **Addresses** | PIN code anchor + context | Detects 6-digit Indian PIN codes, then extracts surrounding text (up to 150 chars) as address context |
| **Policy/Reference Numbers** | Regex | Alphanumeric patterns like `POL-\d+`, `REF\d+`, `#\d+`; length-filtered to avoid false matches |
| **Products/Services** | Keyword dictionary | Domain-specific keyword lists (insurance, banking, telecom) matched against transcript |
| **Organizations** | spaCy NER | Extracts `ORG` entities from the transcript |

#### Deduplication Logic:
Extracted entities are deduplicated by:
1. Normalizing whitespace and case
2. Removing exact duplicates
3. Keeping the first occurrence (with timestamp) for reference

**Output:**
```json
{
  "entities": {
    "names": ["Rahul Sharma"],
    "phone_numbers": ["9876543210"],
    "dates": ["2024-01-15"],
    "amounts": ["₹15,000"],
    "policy_numbers": ["POL-2024-78923"],
    "addresses": ["42 MG Road, Bangalore 560001"],
    "emails": [],
    "organizations": ["HDFC Life"]
  }
}
```

---

### Phase 7: Sentiment & Emotion Analysis

**File:** `src/nlp/sentiment.py`

**What happens:**

1. **Per-Utterance Sentiment**: Each dialogue turn from Phase 5 is analyzed individually:
   - A transformer-based sentiment model classifies each utterance as **Positive**, **Negative**, or **Neutral**
   - Confidence scores are attached to each classification

2. **Emotion Detection**: Beyond polarity, specific emotions are detected:
   - **Anger** — harsh language, raised-voice indicators (ALL CAPS in transcript, exclamation marks)
   - **Frustration** — repeated complaints, phrases like "again", "still not resolved", "how many times"
   - **Satisfaction** — "thank you", "that's great", "perfect"
   - **Neutral** — factual exchanges, information gathering

3. **Sentiment Arc**: The system tracks how sentiment evolves across the call:
   ```
   Start: Neutral → Mid: Negative (complaint) → End: Positive (resolution)
   ```
   This arc is critical for identifying calls that escalated and de-escalated.

4. **Escalation Detection**: A sentiment polarity shift from positive/neutral to strongly negative triggers an escalation flag, especially when combined with:
   - Customer requesting supervisor/manager
   - Repeated use of complaint keywords
   - Increasing negative sentiment scores in consecutive turns

5. **Overall Call Sentiment**: Aggregated by weighted average (later utterances weighted higher, as call resolution matters more than initial complaint).

---

### Phase 8: Compliance & Risk Scoring

**Files:** `src/risk/compliance.py`, `src/risk/risk_engine.py`

**Rule Configuration:** `rules/rules.md`

**What happens:**

1. **Checklist Validation**: The system checks whether mandatory call elements are present:

   | Check | How It Works | Weight |
   |-------|-------------|--------|
   | **Greeting** | First Agent turn checked for greeting phrases ("hello", "welcome", "thank you for calling") | Medium |
   | **Agent Introduction** | Agent name mention within first 3 turns | Medium |
   | **Identity Verification** | Agent asking for policy number/DOB/name before sharing account details | High |
   | **Disclosure Statements** | Required regulatory phrases present (e.g., "this call is being recorded") | High |
   | **Proper Closing** | Last Agent turn contains closing phrases ("anything else", "thank you", "have a good day") | Medium |

2. **Prohibited Phrase Detection**:
   - A dictionary of prohibited/abusive/misleading phrases is checked against the Agent's utterances
   - Includes: profanity, discriminatory language, false promises ("I guarantee"), unauthorized commitments
   - Fuzzy matching handles misspellings and speech-to-text artifacts

3. **Required Phrase Verification**:
   - Industry-specific mandatory disclosures (insurance: "terms and conditions apply", banking: "subject to RBI guidelines")
   - Checked with substring matching and semantic similarity for paraphrased versions

4. **Risk Score Computation**:
   ```
   risk_score = Σ (violation_weight × violation_count) / max_possible_score × 100
   ```
   - **0–30**: Low risk (green) ✅
   - **31–60**: Medium risk (yellow) ⚠️
   - **61–100**: High risk (red) 🔴

5. **Flag Generation**: Each violation produces a structured flag:
   ```json
   {
     "rule": "missing_greeting",
     "severity": "medium",
     "description": "Agent did not greet the customer in the opening",
     "timestamp": null,
     "speaker": "Agent"
   }
   ```

---

### Phase 9: Call Summarization

**File:** `src/nlp/summarization.py`

**What happens:**

1. **Abstractive Summary**: The structured transcript is condensed into a 3–5 sentence summary capturing:
   - Reason for the call
   - Key discussion points
   - Resolution or outcome
   - Any pending action items

2. **Topic Extraction**: Key topics discussed are identified and tagged (e.g., "policy renewal", "claim status", "premium payment").

3. **Action Items**: Explicit commitments from the agent are extracted:
   - "I will send you an email" → Action: Email follow-up
   - "Someone will call you back within 24 hours" → Action: Callback scheduled

4. **Resolution Status**: The system classifies the call outcome:
   - **Resolved** — customer's issue was addressed
   - **Unresolved** — issue pending, follow-up needed
   - **Escalated** — transferred to supervisor/higher authority

---

### Phase 10: Report Assembly & Delivery

**File:** `src/pipeline.py`

**What happens:**

1. All phase outputs are merged into a **single unified JSON report**:
   ```json
   {
     "call_id": "uuid",
     "metadata": { "duration": 342, "language": "en", ... },
     "transcript": [ ... ],
     "entities": { ... },
     "sentiment": { "overall": "Neutral", "arc": [...], ... },
     "compliance": { "score": 25, "flags": [...], "checklist": {...} },
     "summary": { "text": "...", "topics": [...], "action_items": [...] }
   }
   ```

2. **Webhook Delivery**: The report is POSTed to the configured `WEBHOOK_URL` for downstream consumption by dashboards/CRM systems.

3. **API Response**: The same report is returned as the HTTP response to the original API call.

---

## 🔧 Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Web Framework** | FastAPI | Async REST API with auto-generated docs |
| **Audio Processing** | FFmpeg | Format conversion, probing, chunking, sample extraction |
| **Language Detection** | Whisper | Identifies spoken language from audio sample |
| **STT (English)** | Deepgram Nova-2 | High-accuracy English transcription with word timestamps |
| **STT (Hindi/Indic)** | Sarvam AI saarika:v2 | Indic language transcription with code-switching support |
| **Diarization** | Pyannote.audio 3.1 | Neural speaker segmentation and clustering |
| **NLP - NER** | spaCy (en_core_web_sm) | Named entity recognition (persons, organizations) |
| **NLP - Dates** | python-dateutil | Robust date parsing from natural language |
| **NLP - Sentiment** | Transformer models | Utterance-level sentiment and emotion classification |
| **Orchestration** | Python asyncio | Async pipeline with phase-level error recovery |
| **Configuration** | python-dotenv | Environment-based configuration management |
| **Validation** | Pydantic v2 | Schema validation for all inter-phase data |

---

## 🔁 Pipeline Orchestration & Error Recovery

**File:** `src/pipeline.py`, `src/phase_validator.py`

- Each phase is **independently validated** — if Phase 7 (sentiment) fails, Phase 8 (compliance) still runs on available data
- **Retry logic** with exponential backoff for all external API calls (`src/openai_retry.py`)
- Phase outputs are validated against **Pydantic schemas** (`src/schemas/`) before being passed downstream
- Pipeline logs phase-level timing for performance monitoring

---

## 📊 Key Differentiators

1. **Multilingual by Design**: Automatic Hindi/English detection and routing — not an afterthought
2. **No Cloud LLM Dependency for NLP**: Entity extraction, sentiment analysis, and compliance checking run **locally** using spaCy, regex, and lightweight transformer models
3. **Pyannote Diarization**: Research-grade speaker separation; significantly outperforms API-bundled diarization on Indian audio
4. **Configurable Compliance Rules**: Rules defined in markdown (`rules/rules.md`), easily customizable per industry (insurance, banking, telecom)
5. **Full Traceability**: Every extracted insight links back to a **timestamp** in the original audio

---

## 🏃 How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# Fill in: OPENAI_API_KEY, SARVAM_API_KEY, HF_TOKEN, DEEPGRAM_API_KEY

# 3. Start the server
python main.py

# 4. Send a call for analysis
curl -X POST http://localhost:8000/api/v1/analyze-call \
  -F "audio=@call_recording.wav"
```

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/

# Phase-specific tests
pytest tests/test_phase6.py   # Entity extraction
pytest tests/test_phase7.py   # Sentiment analysis
pytest tests/test_phase8.py   # Compliance & risk
```

---

## 📈 Future Roadmap

- **Real-time streaming**: WebSocket-based live call monitoring
- **Agent coaching**: Real-time prompts to agents during calls
- **Custom model fine-tuning**: Domain-specific STT models for insurance/banking terminology
- **Multi-call analytics**: Trend analysis across thousands of calls
- **PII redaction**: Automatic masking of sensitive information in transcripts

---

*Built with ❤️ by the VoiceOps AI Team*