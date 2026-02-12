#!/usr/bin/env bash
# Media Manager health check — restarts any dead services.
# Intended to be called by cron every minute.

set -euo pipefail

PROJECT_DIR="/home/neehawranch/Projects/mediamanager"
LOG_FILE="$PROJECT_DIR/scripts/healthcheck.log"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
NGROK_BIN="$BACKEND_DIR/venv/bin/ngrok"
NGROK_DOMAIN="mediamanager.ngrok.app"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"; }

# --- Backend (uvicorn on port 8000) ---
if ! pgrep -f "uvicorn app.main:app.*--port 8000" > /dev/null 2>&1; then
    log "Backend down — starting"
    cd "$BACKEND_DIR"
    source venv/bin/activate
    nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 >> "$PROJECT_DIR/scripts/backend.log" 2>&1 &
    sleep 3
    log "Backend started (pid $!)"
else
    : # running
fi

# --- Frontend (vite on port 5173) ---
if ! pgrep -f "vite.*--host" > /dev/null 2>&1; then
    log "Frontend down — starting"
    cd "$FRONTEND_DIR"
    nohup npx vite --host 0.0.0.0 >> "$PROJECT_DIR/scripts/frontend.log" 2>&1 &
    sleep 3
    log "Frontend started (pid $!)"
else
    : # running
fi

# --- ngrok tunnel ---
if ! pgrep -f "ngrok" > /dev/null 2>&1; then
    log "ngrok down — starting"
    nohup "$NGROK_BIN" http 5173 --domain "$NGROK_DOMAIN" >> "$PROJECT_DIR/scripts/ngrok.log" 2>&1 &
    sleep 3
    log "ngrok started (pid $!)"
else
    : # running
fi
