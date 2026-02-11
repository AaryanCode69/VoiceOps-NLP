# n8n-nodes-voiceops

This is an n8n community node that integrates VoiceOps fraud detection capabilities into your n8n workflows.

## Features

- **Multi-format Audio Input**: Accept audio files as binary data, file paths, or URLs
- **Fraud Risk Analysis**: Analyze call recordings for fraud indicators using VoiceOps AI
- **Dual-Output Routing**: Automatically route calls to High Risk or Normal outputs based on configurable risk thresholds
- **Comprehensive Metadata**: Enriched output with flattened fields for easy integration with Slack, Google Sheets, and other nodes
- **Robust Error Handling**: Support for continueOnFail with detailed error messages

## Installation

### Prerequisites

- n8n installed (version 0.200.0 or higher)
- Node.js 18.x or higher
- npm or yarn

### Local Development Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/n8n-nodes-voiceops.git
   cd n8n-nodes-voiceops
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Build the node:
   ```bash
   npm run build
   ```

4. Link the node to n8n:
   ```bash
   npm link
   ```

5. In your n8n installation directory (or create custom nodes directory):
   ```bash
   cd ~/.n8n/custom
   npm link n8n-nodes-voiceops
   ```

6. Start n8n:
   ```bash
   n8n start
   ```

The VoiceOps Analyze Call node should now appear in your n8n instance under the Transform category.

## Configuration

### Credentials

1. In n8n, go to **Credentials** → **New**
2. Search for "VoiceOps API"
3. Configure:
   - **Base URL**: Your VoiceOps API endpoint (e.g., `https://api.voiceops.com`)
   - **API Key** (optional): Your VoiceOps API key
   - **Webhook Secret** (optional): Secret for webhook validation

### Node Parameters

- **Audio Source**: Choose how to provide audio (Binary, File Path, or URL)
- **Risk Threshold**: Set the risk score threshold (0-100) for routing (default: 65)
- **Advanced Options**:
  - Poll Timeout: Maximum wait time for analysis (default: 300 seconds)
  - Poll Interval: Time between polling attempts (default: 5 seconds)
  - Force Language: Specify analysis language (auto, en, hi, hi-en)

## Usage

### Basic Workflow

1. Add the **VoiceOps Analyze Call** node to your workflow
2. Connect an input node that provides audio data
3. Configure the audio source and risk threshold
4. Connect downstream nodes to the two outputs:
   - **Output 0 (High Risk)**: Receives calls with risk_score >= threshold
   - **Output 1 (Normal)**: Receives calls with risk_score < threshold

### Example: Slack Notification for High-Risk Calls

```
[Audio Input] → [VoiceOps Analyze Call]
                        ├─ High Risk → [Slack: Alert Security Team]
                        └─ Normal → [Google Sheets: Log Call]
```

### Output Structure

Each output item includes:

```json
{
  "call_id": "uuid",
  "risk_score": 85,
  "fraud_likelihood": "high",
  "explanation": "Multiple fraud indicators detected...",
  "recommended_action": "Escalate to fraud team",
  "matched_patterns": ["pattern1", "pattern2"],
  "_voiceops_meta": {
    "risk_threshold_used": 65,
    "is_high_risk": true,
    "routed_to": "high_risk",
    "processed_at": "2024-01-15T10:30:00Z"
  }
}
```

## Development

### Running Tests

```bash
npm test                    # Run all tests
npm test -- --coverage      # Run with coverage
npm test -- --watch         # Run in watch mode
```

### Building

```bash
npm run build              # Build once
npm run dev                # Build and watch for changes
```

### Linting

```bash
npm run lint               # Check for issues
npm run format             # Format code
```

## License

MIT

## Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/n8n-nodes-voiceops/issues
- VoiceOps Documentation: https://docs.voiceops.com
