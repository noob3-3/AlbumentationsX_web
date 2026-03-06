#!/bin/bash
# ─────────────────────────────────────────────
# Start script for AlbumentationsX backend
# Supports both uvicorn and gunicorn
# ─────────────────────────────────────────────

set -e

# Default values
SERVER_TYPE="${SERVER_TYPE:-uvicorn}"
WORKERS="${WORKERS:-4}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "================================================"
echo "AlbumentationsX Training Platform - Backend"
echo "================================================"
echo "Server: $SERVER_TYPE"
echo "Workers: $WORKERS"
echo "Host: $HOST"
echo "Port: $PORT"
echo "================================================"

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

# Start server based on SERVER_TYPE
if [ "$SERVER_TYPE" = "gunicorn" ]; then
    echo "Starting with Gunicorn (production)..."
    exec gunicorn -c gunicorn.conf.py app.main:app
else
    echo "Starting with Uvicorn..."
    exec python run.py
fi

