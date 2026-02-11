Perfect — below is the **exact content** you should put inside your **`kiro.prompt.md`** file.

This is the **WHAT to build** document. No rules, no guardrails — just the authoritative spec Kiro must implement.

---

## 📄 `kiro.prompt.md`

````md
# Engineering Prompt — VoiceOps Custom n8n Community Node

## Objective

Build a custom n8n community node named **“VoiceOps Analyze Call”** that:

1. Accepts an audio file as input (binary, file path, or URL)
2. Sends the audio to the VoiceOps FastAPI endpoint `POST /api/v1/analyze-call`
3. Waits for analysis completion via polling
4. Parses the returned analysis JSON
5. Routes execution through **two outputs** based on `risk_score`

---

## Core Routing Logic

- **High Risk output** → `risk_score >= riskThreshold`
- **Normal output** → `risk_score < riskThreshold`

Only ONE output may fire per item.

---

## Node Identity

| Property | Value |
|--------|------|
| displayName | VoiceOps Analyze Call |
| name | voiceOpsAnalyzeCall |
| group | ['transform'] |
| version | 1 |
| description | Analyzes financial call recordings for fraud risk using VoiceOps AI and routes calls by risk score |
| inputs | ['main'] |
| outputs | ['main', 'main'] |
| outputNames | ['High Risk', 'Normal'] |

---

## Credentials

Create credential type `voiceOpsApi` with:

| Field | Type | Required |
|-----|------|---------|
| baseUrl | string | Yes |
| apiKey | string (password) | No |
| webhookSecret | string (password) | No |

---

## Node Parameters

### Audio Source
Options:
- Binary Input (`binary`)
- File Path (`filePath`)
- URL (`url`)

Default: `binary`

---

### Binary Property Name
- Type: string  
- Default: `data`  
- Shown only when audio source = binary

---

### Audio File Path
- Type: string  
- Shown only when audio source = filePath

---

### Audio URL
- Type: string  
- Shown only when audio source = url

---

### Risk Threshold
- Type: number  
- Default: `65`  
- Min: `0`  
- Max: `100`

---

### Advanced Options
- Poll Timeout (seconds) — default `300`
- Poll Interval (seconds) — default `5`
- Force Language:
  - auto
  - en
  - hi
  - hi-en

---

## Execution Flow (High Level)

1. Read audio from selected source
2. Validate file size and format
3. Generate `call_id`
4. POST audio to `/api/v1/analyze-call`
5. Poll `/api/v1/result/{call_id}` until:
   - status = complete → continue
   - status = failed → error
   - timeout exceeded → error
6. Parse analysis response
7. Extract `risk_score`
8. Enrich response with `_voiceops_meta`
9. Route item to correct output

---

## Expected Analysis Response Shape

```json
{
  "call_id": "string",
  "call_timestamp": "ISO-8601 timestamp",
  "input_risk_assessment": {
    "risk_score": 0,
    "fraud_likelihood": "low | medium | high",
    "confidence": 0.0
  },
  "rag_output": {
    "explanation": "string",
    "recommended_action": "string",
    "matched_patterns": []
  },
  "backboard_thread_id": "uuid"
}
````

---

## Output Enrichment

Each output item must include:

```json
"_voiceops_meta": {
  "risk_threshold_used": number,
  "is_high_risk": boolean,
  "routed_to": "high_risk | normal",
  "processed_at": "ISO timestamp"
}
```

Also flatten these fields at top-level JSON:

* risk_score
* fraud_likelihood
* call_id
* explanation
* recommended_action
* matched_patterns

---

## Error Scenarios

* Audio > 100MB → error
* Invalid audio → error
* Network failure → error
* Poll timeout → error
* Missing `risk_score` → default to 0, route to Normal

---

## FastAPI Assumptions

VoiceOps backend provides:

* `POST /api/v1/analyze-call`
* `GET /api/v1/result/{call_id}`

Polling response statuses:

* `processing`
* `complete`
* `failed`

---

## File Structure Target

```text
n8n-nodes-voiceops/
├── src/
│   ├── credentials/
│   │   └── VoiceOpsApi.credentials.ts
│   └── nodes/
│       └── VoiceOpsAnalyzeCall/
│           ├── VoiceOpsAnalyzeCall.node.ts
│           ├── VoiceOpsAnalyzeCall.node.json
│           └── voiceops.svg
```

---

## Success Criteria

* Node appears in n8n UI
* Accepts all three audio input modes
* Routes exactly one output per item
* Works with Slack and Google Sheets downstream
* Honors configurable risk threshold

```

