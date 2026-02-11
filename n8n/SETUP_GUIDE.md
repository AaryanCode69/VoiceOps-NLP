# VoiceOps n8n Node - Local Development Setup Guide

This guide will walk you through setting up the VoiceOps n8n community node for local development using npm link.

## Prerequisites

Before you begin, ensure you have:

- **Node.js** 18.x or higher installed
- **npm** 8.x or higher installed
- **n8n** installed globally (or you'll install it in step 1)

Check your versions:
```bash
node --version
npm --version
```

## Step-by-Step Setup

### Step 1: Install n8n Globally

If you don't have n8n installed globally:

```bash
npm install -g n8n
```

Verify installation:
```bash
n8n --version
```

### Step 2: Install Project Dependencies

In your project directory (where package.json is):

```bash
npm install
```

This will install all required dependencies including:
- TypeScript
- n8n-workflow
- fast-check (for property-based testing)
- Jest (for unit testing)
- And other dev dependencies

### Step 3: Build the Node

Build the TypeScript code:

```bash
npm run build
```

This will:
- Compile TypeScript to JavaScript in the `dist/` folder
- Copy assets (JSON, SVG files) to `dist/`

### Step 4: Link the Node Package

Create a global symlink for your package:

```bash
npm link
```

This makes `n8n-nodes-voiceops` available globally on your system.

### Step 5: Link to n8n's Custom Nodes Directory

Create n8n's custom nodes directory if it doesn't exist:

```bash
mkdir -p ~/.n8n/custom
cd ~/.n8n/custom
```

Link the package to n8n:

```bash
npm link n8n-nodes-voiceops
```

### Step 6: Start n8n

Start n8n from any directory:

```bash
n8n start
```

Or with custom settings:

```bash
# Start on a different port
N8N_PORT=5679 n8n start

# Start with tunnel for webhooks
n8n start --tunnel
```

### Step 7: Verify the Node Appears

1. Open n8n in your browser (default: http://localhost:5678)
2. Create a new workflow
3. Click the "+" button to add a node
4. Search for "VoiceOps"
5. You should see **"VoiceOps Analyze Call"** in the Transform category

## Development Workflow

### Making Changes

When you make changes to the code:

1. **Rebuild the node**:
   ```bash
   npm run build
   ```

2. **Restart n8n**:
   - Stop n8n (Ctrl+C)
   - Start it again: `n8n start`

### Watch Mode (Recommended)

For faster development, use watch mode:

```bash
# Terminal 1: Watch and rebuild on changes
npm run dev

# Terminal 2: Run n8n
n8n start
```

Now when you save changes, TypeScript will automatically rebuild. You still need to restart n8n to see the changes.

### Running Tests

```bash
# Run all tests
npm test

# Run tests in watch mode
npm test:watch

# Run with coverage
npm test:coverage
```

## Troubleshooting

### Node Doesn't Appear in n8n

1. **Check the link**:
   ```bash
   ls -la ~/.n8n/custom/node_modules/
   ```
   You should see `n8n-nodes-voiceops` as a symlink.

2. **Verify the build**:
   ```bash
   ls -la dist/
   ```
   Ensure `dist/` contains compiled JavaScript files.

3. **Check n8n logs**:
   Look for errors when starting n8n. The node might have compilation errors.

4. **Re-link**:
   ```bash
   # In your project directory
   npm unlink
   npm link
   
   # In n8n custom directory
   cd ~/.n8n/custom
   npm unlink n8n-nodes-voiceops
   npm link n8n-nodes-voiceops
   ```

### Build Errors

If you get TypeScript errors:

1. **Clean and rebuild**:
   ```bash
   rm -rf dist/
   npm run build
   ```

2. **Check TypeScript version**:
   ```bash
   npx tsc --version
   ```

3. **Reinstall dependencies**:
   ```bash
   rm -rf node_modules package-lock.json
   npm install
   ```

### n8n Can't Find Credentials

If the VoiceOps API credential doesn't appear:

1. Check that `VoiceOpsApi.credentials.ts` is in `src/credentials/`
2. Verify it's listed in `package.json` under `n8n.credentials`
3. Rebuild: `npm run build`
4. Restart n8n

## Testing Your Node

### 1. Create Test Credentials

1. In n8n UI, go to **Credentials** → **New**
2. Search for "VoiceOps API"
3. Enter test values:
   - Base URL: `http://localhost:8000` (or your VoiceOps API URL)
   - API Key: (optional for testing)

### 2. Create a Test Workflow

1. Add a **Manual Trigger** node
2. Add your **VoiceOps Analyze Call** node
3. Configure it with test audio
4. Add **Set** nodes to both outputs to see the routing
5. Execute the workflow

## Next Steps

Now that your development environment is set up, you can:

1. Start implementing the tasks from `.kiro/specs/voiceops-analyze-call/tasks.md`
2. Run tests as you develop: `npm test:watch`
3. Test in n8n UI after each major feature

## Uninstalling

To remove the linked node:

```bash
# In n8n custom directory
cd ~/.n8n/custom
npm unlink n8n-nodes-voiceops

# In your project directory
npm unlink
```

## Additional Resources

- [n8n Community Nodes Documentation](https://docs.n8n.io/integrations/creating-nodes/)
- [n8n Node Development Guide](https://docs.n8n.io/integrations/creating-nodes/build/)
- [TypeScript Documentation](https://www.typescriptlang.org/docs/)
