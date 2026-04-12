#!/bin/bash
export AUTH_ENABLED="${AUTH_ENABLED:-false}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export PYTHONPATH="."
export ENABLE_SCRAPING="${ENABLE_SCRAPING:-true}"
export ENABLE_ODDS="${ENABLE_ODDS:-true}"

# Ports (override via env vars)
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5000}"

# Use DATABASE_URL from secrets if set, otherwise fall back to SQLite for local dev
if [ -z "$DATABASE_URL" ]; then
  export DATABASE_URL="sqlite+aiosqlite:///vit.db"
fi

echo "Starting FastAPI backend on port $BACKEND_PORT..."
python3 -m uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!

echo "Starting Vite frontend on port $FRONTEND_PORT..."
cd frontend && VITE_PORT="$FRONTEND_PORT" npm run dev
