# Quick Start Guide

## Automated Setup (Windows)

Run the setup script:

```bash
setup.bat
```

This will automatically:
1. Install dependencies
2. Build the node
3. Link it globally
4. Link it to n8n

Then start n8n:

```bash
n8n start
```

---

## Manual Setup (Step by Step)

### 1. Check Prerequisites

```bash
node --version    # Should be 18.x or higher
npm --version     # Should be 8.x or higher
```

### 2. Install n8n (if not already installed)

```bash
npm install -g n8n
```

### 3. Install Dependencies

```bash
npm install
```

### 4. Build the Node

```bash
npm run build
```

### 5. Link the Package

```bash
npm link
```

### 6. Link to n8n

```bash
mkdir -p ~/.n8n/custom
cd ~/.n8n/custom
npm link n8n-nodes-voiceops
```

### 7. Start n8n

```bash
n8n start
```

### 8. Verify

1. Open http://localhost:5678
2. Create a new workflow
3. Click "+" to add a node
4. Search for "VoiceOps"
5. You should see "VoiceOps Analyze Call"

---

## Development Commands

```bash
# Build once
npm run build

# Watch mode (auto-rebuild on changes)
npm run dev

# Run tests
npm test

# Run tests in watch mode
npm test:watch

# Run tests with coverage
npm test:coverage

# Lint code
npm run lint

# Format code
npm run format
```

---

## Project Structure

```
n8n-nodes-voiceops/
├── src/
│   ├── credentials/
│   │   └── VoiceOpsApi.credentials.ts    # API credentials definition
│   └── nodes/
│       └── VoiceOpsAnalyzeCall/
│           ├── VoiceOpsAnalyzeCall.node.ts    # Main node implementation
│           ├── VoiceOpsAnalyzeCall.node.json  # Node metadata
│           └── voiceops.svg                   # Node icon
├── dist/                                  # Compiled output (generated)
├── package.json                          # Project configuration
├── tsconfig.json                         # TypeScript configuration
└── jest.config.js                        # Test configuration
```

---

## Next Steps

1. **Read the spec**: Check `.kiro/specs/voiceops-analyze-call/` for requirements and design
2. **Start implementing**: Follow tasks in `.kiro/specs/voiceops-analyze-call/tasks.md`
3. **Test as you go**: Run `npm test:watch` while developing

---

## Troubleshooting

### Node doesn't appear in n8n?

1. Check if build succeeded: `ls dist/`
2. Verify link: `ls -la ~/.n8n/custom/node_modules/`
3. Restart n8n
4. Check n8n logs for errors

### Build errors?

```bash
# Clean and rebuild
rm -rf dist/
npm run build
```

### Need to re-link?

```bash
# Unlink
npm unlink
cd ~/.n8n/custom
npm unlink n8n-nodes-voiceops

# Re-link
cd /path/to/n8n-nodes-voiceops
npm link
cd ~/.n8n/custom
npm link n8n-nodes-voiceops
```

---

## Getting Help

- Check `SETUP_GUIDE.md` for detailed setup instructions
- Check `README.md` for usage documentation
- Review the spec in `.kiro/specs/voiceops-analyze-call/`
