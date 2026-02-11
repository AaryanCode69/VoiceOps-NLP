# Debugging Multipart Form Data Issue

## The Problem

FastAPI is returning 422 with this error:
```json
{
  "detail": [
    {
      "loc": ["body", "audio_file"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

This means FastAPI isn't seeing the `audio_file` field in the multipart request.

## What Your API Expects

```python
@app.post("/api/v1/analyze-call")
async def analyze_call(audio_file: UploadFile = File(...)):
```

FastAPI expects:
- Content-Type: `multipart/form-data`
- Field name: `audio_file`
- Field type: File

## What Works (curl)

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/analyze-call" \
  -F "audio_file=@Sample1.m4a"
```

This works because curl properly formats the multipart data.

## The Issue with n8n's httpRequest

n8n's `this.helpers.httpRequest()` might not be formatting the multipart data correctly for FastAPI.

## Solutions to Try

### Solution 1: Test with HTTP Request Node (Manual Test)

Instead of using the custom node, try using n8n's built-in HTTP Request node:

1. Add an **HTTP Request** node after your Webhook
2. Configure it:
   ```
   Method: POST
   URL: http://127.0.0.1:8000/api/v1/analyze-call
   
   Send Binary Data: Yes
   Binary Property: audio_file0
   Parameter Name for Binary Data: audio_file
   
   Options:
     - Response Format: JSON
   ```

If this works, then we know the issue is with how our custom node is using `httpRequest`.

### Solution 2: Use form-data Library Directly

We might need to use the `form-data` npm package directly instead of relying on n8n's helper:

```typescript
import FormData from 'form-data';

const form = new FormData();
form.append('audio_file', audioBuffer, {
    filename: filename,
    contentType: 'audio/*'
});

const response = await context.helpers.httpRequest({
    method: 'POST',
    url: endpoint,
    body: form,
    headers: {
        ...headers,
        ...form.getHeaders()
    }
});
```

### Solution 3: Check n8n's Request Format

Add logging to see what n8n is actually sending:

```typescript
console.log('Sending request to:', endpoint);
console.log('Headers:', headers);
console.log('Body keys:', Object.keys(requestOptions.body));
console.log('Filename:', filename);
console.log('Buffer size:', audioBuffer.length);
```

## Next Steps

1. **Restart n8n** and try the workflow again
2. **Check your FastAPI logs** - they should show the incoming request details
3. **Try Solution 1** - Use n8n's HTTP Request node to confirm your API works
4. **If HTTP Request node works**, we'll update the custom node to match its approach

## FastAPI Debugging

Add this to your FastAPI endpoint to see what's being received:

```python
@app.post("/api/v1/analyze-call")
async def analyze_call(request: Request, audio_file: UploadFile = File(...)):
    # Log the request
    print(f"Content-Type: {request.headers.get('content-type')}")
    print(f"Headers: {dict(request.headers)}")
    
    # Log the form data
    form = await request.form()
    print(f"Form keys: {list(form.keys())}")
    
    # Continue with your logic...
```

This will show you exactly what FastAPI is receiving.
