#!/bin/bash
# Move to the directory containing this script
cd "/Users/litarcopperkaikem/Documents/Repositiry/chrome-automation-web-template"

echo "=================================================="
echo " Starting Chrome Automation Web Cockpit..."
echo "=================================================="

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run Uvicorn server on port 6969
uvicorn app.main:app --port 6969 --reload
