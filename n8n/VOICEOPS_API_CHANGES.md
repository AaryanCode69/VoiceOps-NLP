# VoiceOps API Integration Changes

## What Changed

Updated the VoiceOps Analyze Call node to match your actual API requirements.

## Your API Expectations

Based on your Postman screenshot, your VoiceOps API expects:

### Endpoint
```
POST http://127.0.0.1:8000/api/v1/analyze-call
```

### Request Format
- **Content-Type:** `multipart/form-data`
- **Fields:**
  - `audio_file`: The audio file (File type)
  - **No other fields** (no call_id, no language in the request)

### Response Format
Your API should return:
```json
{
  "call_id": "some-generated-id",
  "status": "accepted"
}
```

## Changes Made to the Node

### 1. Removed `call_id` from Request
**Before:** Node generated UUID and sent it in form data
```typescript
formData = {
  audio: { ... },
  call_id: "generated-uuid",
  language: "en"
}
```

**After:** Node only sends audio_file
```typescript
formData = {
  audio_file: { ... }
}
```

### 2. Changed Field Name
**Before:** `audio`
**After:** `audio_file` (matches your API)

### 3. Get call_id from API Response
**Before:** Node generated call_id before submission
**After:** Node extracts call_id from API response after submission

```typescript
const response = await submitAudio();
const callId = response.call_id; // From your API
```

### 4. Removed Language Parameter
Your API doesn't accept language in the form data, so it was removed.

## How It Works Now

```
1. User uploads audio file to n8n webhook
   ↓
2. VoiceOps node receives audio as binary (audio_file0)
   ↓
3. Node validates file size (<100MB)
   ↓
4. Node sends POST to your API:
   - Only field: audio_file
   ↓
5. Your API responds with:
   {
     "call_id": "xyz123",
     "status": "accepted"
   }
   ↓
6. Node extracts call_id from response
   ↓
7. Node polls GET /api/v1/result/{call_id}
   ↓
8. When complete, routes based on risk_score
```

## Configuration in n8n

### Credentials (voiceOpsApi)
```
Base URL: http://127.0.0.1:8000
API Key: (optional)
```

### VoiceOps Node Settings
```
Audio Source: Binary Data
Binary Property Name: audio_file0
Risk Threshold: 65
```

## Testing

### 1. Restart n8n
```cmd
# Stop n8n (Ctrl+C), then:
n8n start
```

### 2. Send Test Request
```bash
curl -X POST "http://localhost:5678/webhook/your-path" \
  -F "audio_file=@Sample1.m4a"
```

### 3. Expected Flow
- ✅ Webhook receives file as `audio_file0`
- ✅ VoiceOps node reads from `audio_file0`
- ✅ Node sends to your API with only `audio_file` field
- ✅ Your API returns `call_id`
- ✅ Node polls with that `call_id`
- ✅ Results routed based on risk score

## API Response Requirements

Your VoiceOps API must return a response with `call_id`:

```json
{
  "call_id": "unique-identifier",
  "status": "accepted"
}
```

If your API returns a different format, let me know and I'll adjust the node!

## Troubleshooting

### Still Getting 422?
Check your API logs to see what validation error it's returning.

### API Not Returning call_id?
The node expects `call_id` in the response. If your API returns it with a different name (like `id` or `request_id`), let me know.

### Need to Pass Language?
If your API needs language, we can add it as a query parameter:
```
POST /api/v1/analyze-call?language=en
```

Let me know if you need this!
