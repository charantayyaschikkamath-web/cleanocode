#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
if [ ! -x .venv/bin/python ]; then
  echo "[ERROR] Python virtual environment missing. Run: python3 -m venv .venv && . .venv/bin/activate && python -m pip install -r backend/requirements.txt" >&2
  exit 1
fi
[ -f .env ] || cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
cleanup() { kill "$BACKEND_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
sleep 2
if [ -x frontend/node_modules/.bin/vite ]; then
  cd frontend
  npm run dev -- --host 127.0.0.1
else
  echo "[INFO] React/Vite dependencies are not installed. Use the dependency-free demo at http://127.0.0.1:8000/demo."
  echo "[INFO] The React production build remains a separate release gate. Press Ctrl+C to stop the backend."
  if command -v xdg-open >/dev/null 2>&1; then xdg-open http://127.0.0.1:8000/demo >/dev/null 2>&1 || true; fi
  wait "$BACKEND_PID"
fi
