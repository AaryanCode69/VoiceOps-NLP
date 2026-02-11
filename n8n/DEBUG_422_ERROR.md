# Debugging HTTP 422 Error

## What HTTP 422 Means
"Unprocessable Entity" - The server understands the request but can't process it because:
- Missing required fields
- Wrong field names
- Invalid data format
- Validation errors

## Common Causes for VoiceOps Node

### 1. Field Name Mismatch
**Your API expects:** `audio_file`
**Node is sending:** `audio`

### 2. Missing Required Fields
Your API might require additional fields that aren't being sent.

### 3. Wrong Content-Type for Audio
The node sends `audio/*` but your API might expect specific types like `audio/mpeg`, `audio/mp4`, etc.

## How to Debug

### Step 1: Check Your VoiceOps API Expectations

What does your FastAPI endpoint expect? Check your backend code:

```python
# Example FastAPI endpoint
@app.post("/api/v1/analyze-call")
async def analyze_call(
    audio_file: UploadFile = File(...),  # ← Field name matters!
    call_id: str = Form(...),
    language: Optional[str] = Form(None)
):
    # ...
```

**Key Question:** What is the exact field name for the audio file in your API?
- Is it `audio`?
- Is it `audio_file`?
- Is it `file`?

### Step 2: Test Your API Directly

Use curl to test what your API accepts:

```bash
curl -X POST "http://localhost:8000/api/v1/analyze-call" \
  -F "audio_file=@Sample1.m4a" \
  -F "call_id=test-123"
```

If this works, then the field name is `audio_file`.

### Step 3: Check API Response

Your API should return details about what's wrong. Can you check the full error response?

In n8n, click on the error and look for more details, or check your VoiceOps API logs.

## Quick Fixes to Try

### Fix 1: Update Field Name in Node Code

If your API expects `audio_file` instead of `audio`, we need to update the node code.

**Current code (line ~350):**
```typescript
const formData: { [key: string]: any } = {
    audio: {  // ← This is the field name
        value: audioBuffer,
        options: {
            filename,
            contentType: 'audio/*',
        },
    },
    call_id: callId,
};
```

**Should be:**
```typescript
const formData: { [key: string]: any } = {
    audio_file: {  // ← Changed to match your API
        value: audioBuffer,
        options: {
            filename,
            contentType: 'audio/*',
        },
    },
    call_id: callId,
};
```

### Fix 2: Check if call_id Format is Correct

Your API might expect `call_id` in a different format or as a query parameter instead of form data.

### Fix 3: Verify Content-Type

The node sends `audio/*` but your API might need a specific type:
- `audio/mpeg` for MP3
- `audio/mp4` for M4A
- `audio/wav` for WAV

## Next Steps

1. **Check your VoiceOps API code** - What field name does it expect for the audio file?
2. **Check API logs** - What validation error is it returning?
3. **Test with curl** - Verify what format works directly with your API
4. **Share the API endpoint code** - I can help match the node to your API's expectations

## Most Likely Solution

Based on your Postman screenshot showing `audio_file`, the fix is probably:

**Change line ~350 in VoiceOpsAnalyzeCall.node.ts:**
```typescript
// FROM:
audio: {

// TO:
audio_file: {
```

Would you like me to make this change?
