# VoiceOps API Endpoints Used by the Node

## Overview
The VoiceOps Analyze Call node communicates with your VoiceOps FastAPI backend using two endpoints.

## Base URL Configuration
The base URL is configured in the node credentials:
- **Credential Field**: `baseUrl`
- **Example**: `https://api.voiceops.com` or `http://localhost:8000`

---

## Endpoint 1: Submit Audio for Analysis

### POST /api/v1/analyze-call

**Purpose**: Submit an audio file for fraud analysis

**Request Format**: `multipart/form-data`

**Headers**:
```
Authorization: Bearer <apiKey>  (if API key is configured)
Content-Type: multipart/form-data
```

**Request Body**:
```
audio: <binary audio file>
call_id: <UUID v4 string>
language: <optional: "en" | "hi" | "hi-en">  (only if not "auto")
```

**Example Request**:
```http
POST https://api.voiceops.com/api/v1/analyze-call
Authorization: Bearer your-api-key-here
Content-Type: multipart/form-data

--boundary
Content-Disposition: form-data; name="audio"; filename="call_recording.mp3"
Content-Type: audio/*

<binary audio data>
--boundary
Content-Disposition: form-data; name="call_id"

550e8400-e29b-41d4-a716-446655440000
--boundary
Content-Disposition: form-data; name="language"

en
--boundary--
```

**Expected Response**:
```json
{
  "status": "accepted",
  "call_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Code Location**: `submitAudioForAnalysis()` method in VoiceOpsAnalyzeCall.node.ts

---

## Endpoint 2: Poll for Analysis Results

### GET /api/v1/result/{call_id}

**Purpose**: Check the status and retrieve results of an audio analysis

**Headers**:
```
Authorization: Bearer <apiKey>  (if API key is configured)
```

**URL Parameters**:
- `call_id`: The UUID generated during submission

**Example Request**:
```http
GET https://api.voiceops.com/api/v1/result/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer your-api-key-here
```

**Response - Processing**:
```json
{
  "status": "processing"
}
```

**Response - Complete**:
```json
{
  "status": "complete",
  "result": {
    "call_id": "550e8400-e29b-41d4-a716-446655440000",
    "call_timestamp": "2024-01-15T10:30:00Z",
    "input_risk_assessment": {
      "risk_score": 85,
      "fraud_likelihood": "high",
      "confidence": 0.92
    },
    "rag_output": {
      "explanation": "Multiple fraud indicators detected including...",
      "recommended_action": "Flag for manual review",
      "matched_patterns": ["urgency_language", "account_verification_request"]
    },
    "backboard_thread_id": "thread_abc123"
  }
}
```

**Response - Failed**:
```json
{
  "status": "failed",
  "error": "Audio quality too poor for analysis"
}
```

**Polling Behavior**:
- **Default Poll Interval**: 5 seconds
- **Default Poll Timeout**: 300 seconds (5 minutes)
- The node will keep polling until:
  - Status is "complete" → Returns result
  - Status is "failed" → Throws error
  - Timeout exceeded → Throws error

**Code Location**: `pollForResults()` method in VoiceOpsAnalyzeCall.node.ts

---

## Complete Flow Example

```
1. User triggers n8n workflow with audio file
   ↓
2. Node generates UUID: "550e8400-e29b-41d4-a716-446655440000"
   ↓
3. POST https://api.voiceops.com/api/v1/analyze-call
   - Sends audio file + call_id
   ↓
4. API responds: { "status": "accepted" }
   ↓
5. Node starts polling every 5 seconds:
   GET https://api.voiceops.com/api/v1/result/550e8400-e29b-41d4-a716-446655440000
   ↓
6. First poll: { "status": "processing" } → Wait 5 seconds
   ↓
7. Second poll: { "status": "processing" } → Wait 5 seconds
   ↓
8. Third poll: { "status": "complete", "result": {...} }
   ↓
9. Node processes result:
   - Extracts risk_score: 85
   - Compares to threshold: 65
   - Routes to High Risk output (85 >= 65)
   ↓
10. Workflow continues with enriched data
```

---

## Testing Your Backend

To test if your VoiceOps API is working correctly:

### Test Submission Endpoint
```bash
curl -X POST "http://localhost:8000/api/v1/analyze-call" \
  -H "Authorization: Bearer your-api-key" \
  -F "audio=@/path/to/audio.mp3" \
  -F "call_id=test-123" \
  -F "language=en"
```

### Test Polling Endpoint
```bash
curl -X GET "http://localhost:8000/api/v1/result/test-123" \
  -H "Authorization: Bearer your-api-key"
```

---

## Configuration in n8n

When you add the VoiceOps Analyze Call node to your workflow, you'll configure:

1. **Credentials** (voiceOpsApi):
   - `baseUrl`: `http://localhost:8000` (or your production URL)
   - `apiKey`: Your API key (optional)
   - `webhookSecret`: For webhook validation (optional, not used in this node)

2. **Node Parameters**:
   - Audio source (binary/filePath/url)
   - Risk threshold (0-100)
   - Advanced options (poll timeout, poll interval, language)

The node will automatically construct the full URLs:
- `{baseUrl}/api/v1/analyze-call`
- `{baseUrl}/api/v1/result/{call_id}`
