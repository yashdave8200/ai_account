#!/bin/bash
# Start the Bank Statement Extractor (backend + frontend)

cd "$(dirname "$0")"

# Activate venv if it exists
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

# Open frontend in browser after a short delay (waits for server to be ready)
(sleep 2 && xdg-open frontend/index.html) &

# Start FastAPI backend
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
