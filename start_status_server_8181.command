#!/bin/bash
cd "$(dirname "$0")"

if [ -f ".env" ]; then
    set -a
    source .env 2>/dev/null
    set +a
fi

echo "=================================================="
echo " Starting Lakorn Generation Status Monitor on 8181"
echo "=================================================="

# Kill old process on port 8181 if running
PID_8181=$(lsof -t -i tcp:8181)
if [ ! -z "$PID_8181" ]; then
    echo "Killing old process (PID: $PID_8181) on port 8181..."
    kill -9 $PID_8181 2>/dev/null
fi

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

exec python scripts/status_server_8181.py
