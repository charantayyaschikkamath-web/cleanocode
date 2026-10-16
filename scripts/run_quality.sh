#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p artifacts/quality
status=0

python -m compileall -q backend scripts tests || status=1
python scripts/evaluate_scenarios.py --output-dir artifacts/quality || status=1
python -m pytest -q backend/tests tests || status=1

if [ -x frontend/node_modules/.bin/tsc ]; then
  (cd frontend && npm run typecheck && npm run build) || status=1
else
  echo "[BLOCKED] Frontend dependencies are not installed; commit frontend/package-lock.json and run npm ci before typecheck/build."
  status=1
fi

python scripts/preflight.py --json-out artifacts/quality/preflight.json || status=1
python scripts/check_offline.py --json-out artifacts/quality/offline-readiness.json || status=1

if [ "$status" -eq 0 ]; then
  echo "Quality gate PASS: all invoked checks passed."
else
  echo "Quality gate FAIL: at least one required check is blocked or failing. Inspect artifacts/quality/*.json and fix the reported blockers."
fi
exit "$status"
