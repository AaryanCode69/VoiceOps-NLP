# Kiro Rules — VoiceOps n8n Community Node

## Role & Scope
You are implementing a custom **n8n community node** in TypeScript.
You must follow n8n's node architecture, execution model, and error-handling conventions.

You are NOT designing APIs or changing requirements unless explicitly stated.
You are translating the provided engineering prompt into correct, production-grade code.

---

## Architectural Rules (NON-NEGOTIABLE)

1. Follow n8n's official community node structure:
   - Use `NodeOperationError` for all runtime failures
   - Use `this.helpers.httpRequest()` for all HTTP calls
   - Support `continueOnFail()` correctly

2. The node MUST:
   - Have **exactly one input**
   - Have **exactly two outputs**
     - Output 0 → High Risk
     - Output 1 → Normal

3. Output routing is STRICT:
   - `risk_score >= riskThreshold` → High Risk ONLY
   - `risk_score < riskThreshold` → Normal ONLY
   - Never send the same item to both outputs

---

## Execution Rules

4. Treat each input item independently.
   - Do not batch audio files
   - Do not share state between items

5. Audio handling rules:
   - Support binary input, file path, and URL
   - Reject files > 100MB BEFORE sending to VoiceOps
   - Preserve original filename where possible

6. Network rules:
   - POST audio using multipart/form-data
   - Poll using GET `/api/v1/result/{call_id}`
   - Respect configurable timeout and polling interval

7. Never block indefinitely.
   - If timeout is exceeded, throw a timeout error including `call_id`

---

## Data Integrity Rules

8. Assume webhook/poll responses may be incomplete.
   - If `risk_score` is missing:
     - Default to `0`
     - Route to Normal output
     - Add warning under `_voiceops_meta`

9. Do NOT mutate VoiceOps payload structure.
   - Only enrich data under `_voiceops_meta`
   - Flatten key fields at top level for Slack compatibility

---

## Error Handling Rules

10. Always prefer controlled failure:
    - Use `NodeOperationError`
    - Respect `continueOnFail()`

11. If `continueOnFail()` is enabled:
    - Push error objects ONLY to Normal output
    - Never throw

12. Errors must be explicit and actionable:
    - Include call_id where available
    - Include HTTP status codes for network failures

---

## Code Quality Rules

13. Use TypeScript strictly.
    - No `any` unless unavoidable
    - Type webhook and poll responses

14. No hardcoded URLs, secrets, or thresholds.
    - Everything configurable via credentials or node parameters

15. No console logs.
    - Use n8n error mechanisms only

---

## What You Must NOT Do

❌ Do not redesign the workflow  
❌ Do not simplify multi-output logic  
❌ Do not merge outputs  
❌ Do not assume synchronous processing  
❌ Do not invent new fields or API endpoints  

---

## Success Criteria

The implementation is correct ONLY if:
- The node installs via `npm link`
- Appears in n8n UI
- Routes items correctly based on `risk_score`
- Works with Slack and Google Sheets nodes downstream
