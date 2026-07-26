#!/bin/bash
# Move to the directory containing this script
cd "/Users/litarcopperkaikem/Documents/Repositiry/chrome-automation-web-template"

echo "=================================================="
echo " Starting Chrome Automation Web Cockpit..."
echo "=================================================="

# Kill any old processes holding port 6969 or 9225
echo "Checking for old processes on port 6969..."
PID_6969=$(lsof -t -i tcp:6969)
if [ ! -z "$PID_6969" ]; then
    echo "Killing old server process (PID: $PID_6969) on port 6969..."
    kill -9 $PID_6969 2>/dev/null
fi

echo "Checking for old processes on port 9225..."
PID_9225=$(lsof -t -i tcp:9225)
if [ ! -z "$PID_9225" ]; then
    echo "Killing old agent process (PID: $PID_9225) on port 9225..."
    kill -9 $PID_9225 2>/dev/null
fi

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run Uvicorn server on port 6969
uvicorn app.main:app --port 6969 --reload
