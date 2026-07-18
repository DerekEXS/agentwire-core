#!/bin/bash
# Stop OpenClaw A2A Gateway
DIR="/home/AIKali/.openclaw/a2a-gateway"
PIDFILE="$DIR/a2a-gateway.pid"
if [ -f "$PIDFILE" ]; then
  PID=$(cat "$PIDFILE")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "Stopped (PID $PID)"
  fi
  rm -f "$PIDFILE"
else
  echo "No PID file; nothing to stop"
fi
