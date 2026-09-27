#!/bin/bash
# Move to the directory containing this script
cd "/Users/litarcopperkaikem/Documents/Repositiry/chrome-automation-web-template"

echo "=================================================="
echo " Starting Chrome Automation Web Cockpit..."
echo "=================================================="

# Cleanup background processes on exit
trap 'kill $(jobs -p) 2>/dev/null' EXIT INT TERM

# Kill any old processes holding port 6969, 9225, or 8100
echo "Checking for old processes on port 6969..."
PID_6969=$(lsof -t -i tcp:6969)
if [ ! -z "$PID_6969" ]; then
    echo "Killing old server process (PID: $PID_6969) on port 6969..."
    kill -9 $PID_6969 2>/dev/null
fi

echo "Checking for old processes on port 9225..."
PID_9225=$(lsof -t -i tcp:9225)
if [ ! -z "$PID_9225" ]; then
    echo "Killing old agent WS process (PID: $PID_9225) on port 9225..."
    kill -9 $PID_9225 2>/dev/null
fi

echo "Checking for old processes on port 8100..."
PID_8100=$(lsof -t -i tcp:8100)
if [ ! -z "$PID_8100" ]; then
    echo "Killing old agent API process (PID: $PID_8100) on port 8100..."
    kill -9 $PID_8100 2>/dev/null
fi

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run Flow Kit Agent server on port 8100 in background
echo "Starting Flow Kit Agent server on port 8100..."
python -m agent.main &

# Run Uvicorn server on port 6969 with auto-reload on web and app changes
echo "Starting main Web Cockpit server on port 6969 (Auto-reload enabled)..."
uvicorn app.main:app --port 6969 --reload \
    --reload-dir app \
    --reload-dir web \
    --reload-dir agent \
    --reload-include "*.py" \
    --reload-include "*.html" \
    --reload-include "*.js" \
    --reload-include "*.css" \
    --reload-exclude "runtime/*" \
    --reload-exclude "*.bak"
