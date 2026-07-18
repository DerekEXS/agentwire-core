#!/bin/bash
# OpenClaw A2A Gateway - startup script
# Runs server.py in background, writes PID, logs to a2a-gateway.log

set -e

DIR="/home/AIKali/.openclaw/a2a-gateway"
PIDFILE="$DIR/a2a-gateway.pid"
LOGFILE="$DIR/a2a-gateway.log"
PYTHON="${PYTHON:-python3}"

cd "$DIR"

# Stop existing
if [ -f "$PIDFILE" ]; then
  OLD_PID=$(cat "$PIDFILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Stopping previous instance (PID $OLD_PID)..."
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

# Start fresh
echo "Starting OpenClaw A2A Gateway..."
nohup "$PYTHON" "$DIR/server.py" >> "$LOGFILE" 2>&1 &
NEW_PID=$!
echo $NEW_PID > "$PIDFILE"

sleep 1
if kill -0 "$NEW_PID" 2>/dev/null; then
  echo "Started OK (PID $NEW_PID)"
  echo "  endpoints:"
  echo "    GET  http://127.0.0.1:18802/health"
  echo "    GET  http://127.0.0.1:18802/.well-known/agent-card.json"
  echo "    POST http://127.0.0.1:18802/a2a/jsonrpc"
  echo "    POST http://127.0.0.1:18802/rpc/agent"
else
  echo "FAILED to start. Check $LOGFILE"
  rm -f "$PIDFILE"
  exit 1
fi
