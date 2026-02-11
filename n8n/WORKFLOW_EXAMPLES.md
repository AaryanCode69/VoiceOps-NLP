# VoiceOps Node Workflow Examples

## Understanding the Two Outputs

Your VoiceOps Analyze Call node has **two outputs**:

### Output 1: High Risk (Red/Top Output)
- Receives calls where `risk_score >= risk_threshold`
- Default threshold: 65
- These are potentially fraudulent calls that need attention

### Output 2: Normal (Green/Bottom Output)
- Receives calls where `risk_score < risk_threshold`
- These are legitimate calls
- Also receives errors if "Continue on Fail" is enabled

---

## Example 1: Basic Fraud Alert System

```
┌──────────────┐
│   Webhook    │ ← Receives audio file upload
└──────┬───────┘
       │
       ↓
┌─────────────────────────┐
│ VoiceOps Analyze Call   │
│ Threshold: 65           │
└────┬──────────────┬─────┘
     │              │
     │ High Risk    │ Normal
     │ (≥65)        │ (<65)
     ↓              ↓
┌─────────────┐  ┌──────────────┐
│ Slack Node  │  │ Google Sheet │
│ #fraud-team │  │ Normal Calls │
└─────────────┘  └──────────────┘
```

### High Risk → Slack Configuration
```
Channel: #fraud-alerts
Message:
🚨 HIGH RISK CALL DETECTED

Risk Score: {{ $json.risk_score }}/100
Fraud Likelihood: {{ $json.fraud_likelihood }}
Call ID: {{ $json.call_id }}

📋 Analysis:
{{ $json.explanation }}

✅ Recommended Action:
{{ $json.recommended_action }}

🔍 Matched Patterns:
{{ $json.matched_patterns.join(', ') }}

Timestamp: {{ $json._voiceops_meta.processed_at }}
```

### Normal → Google Sheets Configuration
```
Spreadsheet: Call Logs
Sheet: Normal Calls
Columns:
- Call ID: {{ $json.call_id }}
- Risk Score: {{ $json.risk_score }}
- Fraud Likelihood: {{ $json.fraud_likelihood }}
- Timestamp: {{ $json.call_timestamp }}
- Processed At: {{ $json._voiceops_meta.processed_at }}
```

---

## Example 2: Multi-Channel Alert System

```
┌──────────────┐
│   Webhook    │
└──────┬───────┘
       │
       ↓
┌─────────────────────────┐
│ VoiceOps Analyze Call   │
│ Threshold: 70           │
└────┬──────────────┬─────┘
     │              │
     │ High Risk    │ Normal
     ↓              ↓
┌─────────────┐  ┌──────────────┐
│    IF       │  │ HTTP Request │
│ risk > 85?  │  │ Send to CRM  │
└──┬────┬─────┘  └──────────────┘
   │    │
   │Yes │No
   ↓    ↓
┌──────┐ ┌────────┐
│Email │ │ Slack  │
│+SMS  │ │ Alert  │
└──────┘ └────────┘
```

### High Risk → IF Node
```
Condition: {{ $json.risk_score }} > 85

If True (Critical):
  → Email to security@company.com
  → SMS to on-call manager
  → Create P1 incident ticket

If False (High but not critical):
  → Slack notification to #fraud-team
  → Log to database
```

---

## Example 3: Complete Fraud Management Pipeline

```
┌──────────────┐
│   Webhook    │
└──────┬───────┘
       │
       ↓
┌─────────────────────────┐
│ VoiceOps Analyze Call   │
│ Threshold: 65           │
└────┬──────────────┬─────┘
     │              │
     │ High Risk    │ Normal
     ↓              ↓
┌─────────────┐  ┌──────────────┐
│   Slack     │  │   Postgres   │
│   Alert     │  │   Insert     │
└──────┬──────┘  └──────────────┘
       │
       ↓
┌─────────────┐
│    Jira     │
│ Create Task │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  Postgres   │
│   Insert    │
│ high_risk   │
└─────────────┘
```

### High Risk Path:
1. **Slack Alert** - Immediate notification
2. **Jira Ticket** - Create investigation task
3. **Database** - Log to `high_risk_calls` table

### Normal Path:
1. **Database** - Log to `processed_calls` table

---

## Example 4: Customer Service Routing

```
┌──────────────┐
│   Webhook    │
└──────┬───────┘
       │
       ↓
┌─────────────────────────┐
│ VoiceOps Analyze Call   │
│ Threshold: 60           │
└────┬──────────────┬─────┘
     │              │
     │ High Risk    │ Normal
     ↓              ↓
┌─────────────┐  ┌──────────────┐
│  Twilio     │  │   Twilio     │
│  Route to   │  │   Route to   │
│  Fraud Team │  │   Normal CS  │
└─────────────┘  └──────────────┘
```

### Use Case:
- High risk calls → Routed to specialized fraud investigation team
- Normal calls → Routed to standard customer service

---

## Example 5: Analytics & Reporting

```
┌──────────────┐
│   Webhook    │
└──────┬───────┘
       │
       ↓
┌─────────────────────────┐
│ VoiceOps Analyze Call   │
│ Threshold: 65           │
└────┬──────────────┬─────┘
     │              │
     │ High Risk    │ Normal
     ↓              ↓
┌─────────────┐  ┌──────────────┐
│   Airtable  │  │   Airtable   │
│ Fraud Cases │  │ Normal Calls │
└──────┬──────┘  └──────┬───────┘
       │                │
       └────────┬───────┘
                ↓
        ┌──────────────┐
        │  Merge Node  │
        └──────┬───────┘
               ↓
        ┌──────────────┐
        │   Webhook    │
        │ Send to BI   │
        └──────────────┘
```

---

## Available Data Fields

Both outputs provide enriched data:

### Flattened Fields (Easy Access)
```javascript
$json.risk_score          // 0-100
$json.fraud_likelihood    // "low", "medium", "high"
$json.call_id            // UUID
$json.explanation        // AI explanation
$json.recommended_action // What to do
$json.matched_patterns   // Array of fraud patterns
```

### Metadata
```javascript
$json._voiceops_meta.risk_threshold_used  // Threshold used
$json._voiceops_meta.is_high_risk        // true/false
$json._voiceops_meta.routed_to           // "high_risk" or "normal"
$json._voiceops_meta.processed_at        // ISO timestamp
$json._voiceops_meta.warning             // If risk_score was missing
```

### Original Nested Structure (Also Available)
```javascript
$json.input_risk_assessment.risk_score
$json.input_risk_assessment.fraud_likelihood
$json.input_risk_assessment.confidence
$json.rag_output.explanation
$json.rag_output.recommended_action
$json.rag_output.matched_patterns
```

---

## Common Node Connections

### For High Risk Output:
- ✅ Slack (alerts)
- ✅ Email (notifications)
- ✅ SMS/Twilio (urgent alerts)
- ✅ Jira/Linear (create tickets)
- ✅ PagerDuty (incidents)
- ✅ Webhook (trigger external systems)
- ✅ Database (log high risk calls)
- ✅ Google Sheets (fraud log)

### For Normal Output:
- ✅ Database (log all calls)
- ✅ Google Sheets (call records)
- ✅ Airtable (analytics)
- ✅ CRM systems (customer data)
- ✅ Webhook (send to other services)
- ✅ Archive/S3 (long-term storage)
- ✅ Stop/No-op (just log and end)

---

## Tips

1. **Always log both outputs** - Even normal calls should be recorded for analytics

2. **Use IF nodes for granular control** - Add conditions on the High Risk output:
   ```
   IF risk_score > 90 → Urgent alert
   IF risk_score 70-90 → Standard alert
   ```

3. **Include context in alerts** - Use all available fields:
   - Risk score
   - Explanation
   - Recommended action
   - Matched patterns
   - Call ID for tracking

4. **Set appropriate threshold** - Default is 65, but adjust based on your needs:
   - Stricter (50): More calls flagged as high risk
   - Looser (80): Only very suspicious calls flagged

5. **Handle errors** - Enable "Continue on Fail" to route errors to Normal output

6. **Test with different risk scores** - Use the threshold parameter to fine-tune routing
