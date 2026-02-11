# n8n Webhook Configuration for File Uploads

## Problem
Your API sends audio files as `form-data` with field name `audio_file`, but n8n Webhook needs proper configuration to receive files.

## Solution: Configure Webhook Node

### Step 1: Add Webhook Node to Your Workflow

1. In n8n, add a **Webhook** node at the start of your workflow
2. Configure it as follows:

**Webhook Settings:**
```
HTTP Method: POST
Path: webhook/voiceops-upload (or any path you want)
Response Mode: When Last Node Finishes
Response Code: 200
```

**Important: Enable Binary Data**
- Scroll down to "Options"
- Click "Add Option"
- Select **"Binary Data"**
- Set to: **Yes** or **True**

### Step 2: Webhook Will Receive File as Binary

When configured correctly, the webhook will automatically:
- Accept `multipart/form-data` requests
- Convert uploaded files to binary data
- Store them in `$binary` with the field name as the key

**Your file will be available at:**
```
$binary.audio_file0
```

**Important:** n8n automatically appends `0` to the field name to support multiple file uploads.

### Step 3: Connect Webhook to VoiceOps Node

```
[Webhook Node] → [VoiceOps Analyze Call Node]
```

**In VoiceOps Node, configure:**
- Audio Source: **Binary Data**
- Binary Property Name: **audio_file0** (note the 0 suffix added by n8n!)

## Complete Workflow Example

```
┌─────────────────┐
│  Webhook Node   │
│  POST /webhook  │
│  Binary: Yes    │
└────────┬────────┘
         │ Receives: audio_file (form-data)
         │ Outputs: $binary.audio_file
         ↓
┌─────────────────────────┐
│ VoiceOps Analyze Call   │
│ Audio Source: binary    │
│ Property: audio_file    │
└────────┬────────────────┘
         │
         ↓
    [Results]
```

## Testing Your Webhook

### Get Your Webhook URL
After adding the Webhook node, n8n will show you the URL:
```
Production URL: http://localhost:5678/webhook/voiceops-upload
Test URL: http://localhost:5678/webhook-test/voiceops-upload
```

### Test with Postman (as shown in your screenshot)

**Request:**
```
POST http://localhost:5678/webhook/voiceops-upload
Content-Type: multipart/form-data

Body (form-data):
- Key: audio_file
- Type: File
- Value: Sample1.m4a
```

### Test with cURL

```bash
curl -X POST "http://localhost:5678/webhook/voiceops-upload" \
  -F "audio_file=@/path/to/Sample1.m4a"
```

## Important: Binary Property Name Must Match (with n8n suffix)

Your form field name is: **`audio_file`**
n8n stores it as: **`audio_file0`** (adds 0 suffix automatically)

So in VoiceOps node, set:
- Binary Property Name: **`audio_file0`** (not "audio_file" or "data")

## Troubleshooting

### Issue: "Binary property not found"
**Solution:** n8n adds a `0` suffix to binary field names. Use `audio_file0` instead of `audio_file`.

```
Form field name: audio_file
↓ (n8n adds suffix)
Stored as: audio_file0
↓
VoiceOps node setting: audio_file0
```

### Issue: Still getting "Binary property 'audio_file' not found"
**Solution:** Check the webhook output in the Binary tab to see the exact property name, then use that exact name (likely `audio_file0`).

### Issue: Webhook not receiving file
**Solution:** 
1. Ensure "Binary Data" option is enabled in Webhook node
2. Use `multipart/form-data` content type
3. Check webhook is in "listening" mode (execute workflow once)

### Issue: File too large
**Solution:** 
- n8n default max payload: 16MB
- Your node validates: 100MB max
- To increase n8n limit, set environment variable:
  ```bash
  export N8N_PAYLOAD_SIZE_MAX=100
  n8n start
  ```

## Alternative: Direct URL Upload

If you want to send a URL instead of uploading the file:

**Request:**
```json
POST http://localhost:5678/webhook/voiceops-upload
Content-Type: application/json

{
  "audio_url": "https://example.com/audio.mp3"
}
```

**VoiceOps Node Configuration:**
- Audio Source: **URL**
- Audio URL: `{{ $json.audio_url }}`

## Complete Example Workflow

```json
{
  "nodes": [
    {
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "parameters": {
        "httpMethod": "POST",
        "path": "voiceops-upload",
        "options": {
          "binaryData": true
        }
      }
    },
    {
      "name": "VoiceOps Analyze Call",
      "type": "n8n-nodes-voiceops.voiceOpsAnalyzeCall",
      "parameters": {
        "audioSource": "binary",
        "binaryPropertyName": "audio_file",
        "riskThreshold": 65
      }
    }
  ]
}
```

## Summary

✅ **Webhook Node:** Enable "Binary Data" option
✅ **Form Field Name:** `audio_file`
✅ **VoiceOps Node:** Set Binary Property Name to `audio_file`
✅ **Test:** Send POST with `multipart/form-data` containing `audio_file`

Your workflow will now accept file uploads exactly as shown in your Postman screenshot! 🎉
