@echo off
echo ========================================
echo VoiceOps n8n Node - Setup Script
echo ========================================
echo.

echo Step 1: Installing dependencies...
call npm install
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

echo Step 2: Building the node...
call npm run build
if %errorlevel% neq 0 (
    echo ERROR: Failed to build the node
    pause
    exit /b 1
)
echo.

echo Step 3: Linking the package globally...
call npm link
if %errorlevel% neq 0 (
    echo ERROR: Failed to link package
    pause
    exit /b 1
)
echo.

echo Step 4: Creating n8n custom directory...
if not exist "%USERPROFILE%\.n8n\custom" (
    mkdir "%USERPROFILE%\.n8n\custom"
)
echo.

echo Step 5: Linking to n8n...
cd "%USERPROFILE%\.n8n\custom"
call npm link n8n-nodes-voiceops
if %errorlevel% neq 0 (
    echo ERROR: Failed to link to n8n
    pause
    exit /b 1
)
echo.

echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Start n8n: n8n start
echo 2. Open http://localhost:5678
echo 3. Look for "VoiceOps Analyze Call" node
echo.
echo For development:
echo - Run "npm run dev" to watch for changes
echo - Run "npm test" to run tests
echo.
pause
