# Setup Checklist

Use this checklist to verify your setup is complete.

## Prerequisites
- [ ] Node.js 18.x or higher installed (`node --version`)
- [ ] npm 8.x or higher installed (`npm --version`)
- [ ] n8n installed globally (`n8n --version`)

## Installation Steps
- [ ] Dependencies installed (`npm install`)
- [ ] Project builds successfully (`npm run build`)
- [ ] `dist/` folder created with compiled files
- [ ] Package linked globally (`npm link`)
- [ ] `~/.n8n/custom` directory exists
- [ ] Package linked to n8n (`cd ~/.n8n/custom && npm link n8n-nodes-voiceops`)

## Verification
- [ ] n8n starts without errors (`n8n start`)
- [ ] Can access n8n UI at http://localhost:5678
- [ ] "VoiceOps Analyze Call" node appears in node list
- [ ] Node is in "Transform" category
- [ ] "VoiceOps API" credential type is available

## Development Setup
- [ ] Tests run successfully (`npm test`)
- [ ] Watch mode works (`npm run dev`)
- [ ] Can create test workflow in n8n UI
- [ ] Can add VoiceOps node to workflow

## Ready to Develop!

Once all items are checked, you're ready to start implementing the tasks from:
`.kiro/specs/voiceops-analyze-call/tasks.md`

## Quick Commands Reference

```bash
# Development
npm run dev          # Watch mode
npm test:watch       # Test watch mode

# Testing
npm test            # Run all tests
npm test:coverage   # With coverage

# Building
npm run build       # Build once

# After changes
npm run build       # Rebuild
# Then restart n8n
```
