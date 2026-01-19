#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="/app/src:${PYTHONPATH:-}"

echo "Starting FastAPI..."
uvicorn api.main:app --host 0.0.0.0 --port 8000 &
api_pid=$!

echo "Starting transcription pipeline..."
python -m pipeline.main &
pipeline_pid=$!

echo "Starting Next.js dev server..."
npm --prefix /app/web run dev -- --hostname 0.0.0.0 --port 3000 &
web_pid=$!

trap 'kill "$api_pid" "$pipeline_pid" "$web_pid" 2>/dev/null || true' SIGINT SIGTERM

wait -n "$api_pid" "$pipeline_pid" "$web_pid"
status=$?

kill "$api_pid" "$pipeline_pid" "$web_pid" 2>/dev/null || true
wait || true

exit "$status"
