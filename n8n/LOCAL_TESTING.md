# Local Testing Guide for VoiceOps n8n Node

## Prerequisites
- Node.js installed (v16 or higher)
- n8n installed globally or locally

## Step 1: Install n8n (if not already installed)
```bash
npm install -g n8n
```

## Step 2: Link Your Custom Node

From this project directory:
```bash
# Build your node
npm run build

# Create a global npm link
npm link
```

## Step 3: Link to n8n

```bash
# Navigate to your n8n custom nodes directory
# On Windows: C:\Users\<YourUsername>\.n8n\custom
# On Mac/Linux: ~/.n8n/custom

# Create the custom directory if it doesn't exist
mkdir -p ~/.n8n/custom  # Mac/Linux
# or
mkdir %USERPROFILE%\.n8n\custom  # Windows

# Navigate to the custom directory
cd ~/.n8n/custom  # Mac/Linux
# or
cd %USERPROFILE%\.n8n\custom  # Windows

# Link your node package
npm link n8n-nodes-voiceops
```

## Step 4: Start n8n

```bash
n8n start
```

n8n will start on http://localhost:5678

## Step 5: Find Your Node

1. Open http://localhost:5678 in your browser
2. Create a new workflow
3. Click the "+" button to add a node
4. Search for "VoiceOps Analyze Call"
5. Your custom node should appear!

## Alternative: Run n8n with Custom Node Path

You can also run n8n directly pointing to your custom node:

```bash
# Set the custom nodes path
export N8N_CUSTOM_EXTENSIONS_DIR=/path/to/n8n-nodes-voiceops  # Mac/Linux
# or
set N8N_CUSTOM_EXTENSIONS_DIR=D:\Projects\Voiceops\n8n  # Windows

# Start n8n
n8n start
```

## Troubleshooting

### Node Not Appearing
1. Check that `npm run build` completed successfully
2. Verify the dist folder contains compiled files
3. Restart n8n completely
4. Check n8n logs for any errors

### Build Errors
```bash
# Clean and rebuild
rm -rf dist node_modules
npm install
npm run build
```

### Watch Mode for Development
```bash
# In one terminal, watch for changes
npm run dev

# In another terminal, run n8n
n8n start
```

After making changes, you'll need to restart n8n to see updates.

## Testing the Node

1. Add the VoiceOps Analyze Call node to your workflow
2. Configure credentials:
   - Base URL: Your VoiceOps API endpoint
   - API Key: Your API key (optional)
3. Provide audio input (binary, file path, or URL)
4. Set risk threshold (default: 65)
5. Execute the workflow
6. Check the two outputs:
   - Output 1 (High Risk): Calls with risk_score >= threshold
   - Output 2 (Normal): Calls with risk_score < threshold
