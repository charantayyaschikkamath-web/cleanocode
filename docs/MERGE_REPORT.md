# CampusTwin AI — Eight-Account Merge Report

**Merge workspace:** `CampusTwin_AI_Merged`  
**Date:** 16 October 2026  
**Purpose:** one integrated repository for the eight uploaded Account 1–8 ZIP packages, with a local uploaded-video analysis option for the camera page.

## Integration summary

| Account/workstream | Integrated result |
|---|---|
| 1 — Product architecture/contracts | Project brief, contracts, architecture/decision docs, feature map, ownership notes, `.env.example`, `config.yaml`, and JSON contract examples retained. No official event rules were invented. |
| 2 — Backend core/persistence/impact | Canonical `backend/app/main.py`, SQLite/SQLAlchemy persistence, typed API errors, health/preflight, source/provenance, deterministic impact logic and core resource routers retained. |
| 3 — Detection/action lifecycle | Rule engine, scenario runner, human-approved actions, append-only transition log, baseline/post-action verification and savings ledger connected to canonical app. Shared event evaluation/evidence endpoints are already in `backend/app/routers/events.py`; the separate Account 3 `event_workflow.py` router was not double-registered because it would duplicate these endpoints. |
| 4 — Camera/local vision | Vision service/router mounted at `/api/vision`; live browser webcam/USB path retained. Added local video-file selection, in-browser frame sampling and progress/cancel UI. No original recording is uploaded or persisted; sampled frames are sent only to the configured local inference endpoint. |
| 5 — Frontend product | React/Vite main shell and navigation wired to the `/api/v1/ui` compatibility routes. Empty initial state offers a labelled demo scenario, instead of pretending seed metrics are live. Camera & video is in navigation. |
| 6 — Digital twin/charts | Clickable 2D twin, room/building views, resource charts and verification/scenario visualization retained in `frontend/src/features/twin` and `frontend/src/features/charts`. |
| 7 — Copilot/what-if/reports | Added sanitized database-to-facts adapter; canonical app mounts Copilot, reports and What-If routers. Numeric facts remain backend-owned; template fallback is available without a key. |
| 8 — Quality/release engineering | Preflight, synthetic scenario evaluator, offline audit, reset helper, documentation, quality tests and combined run script retained and refreshed. |

## Verification actually run

- `python -m compileall -q backend scripts tests` — PASS.
- `python -m pytest -q` — **90 passed** in the current environment.
- `python scripts/evaluate_scenarios.py --output-dir artifacts/quality` — **10/10 synthetic scenarios passed**. Dropped/ignored commands left the ledger unchanged; the verified response created one simulated ledger entry.
- TestClient integration tests exercised health, dashboard, scenario→evidence→Copilot template, human approval, idempotent replay, successful and failed ledger paths, what-if projection, report export and camera-unavailable/simulated fallback.
- TypeScript/TSX source scan — **32 files parsed, 0 syntax errors; 59 relative imports checked with 0 missing local targets**. This remains a syntax/path scan, not a dependency-backed project typecheck.
- `python scripts/preflight.py` — **FAIL** because frontend build output is missing; core files/dependencies/canonical router registration pass. Missing optional LLM key/model are warnings and fall back safely.
- `python scripts/check_offline.py` — **FAIL** because no frontend lockfile/build or prepared offline dependency cache exists; a local model is also not included.
- `npm run build` — explicitly attempted and **BLOCKED** at `tsc -b`: `react`, `react-dom/client`, `lucide-react`, and `react/jsx-runtime` could not be resolved because dependencies were absent. `npm install --no-audit --no-fund` timed out, and `curl` could not resolve `registry.npmjs.org`; therefore chained `vite build` did not run. Details: `artifacts/quality/FRONTEND_PRODUCTION_BUILD_ATTEMPT.md`. No lockfile or build output was fabricated.

All evaluator scenarios are synthetic. No hardware camera, configured ONNX model or real campus feed was available in this environment. The video upload UI and browser-side sampling code are implemented but have not been exercised in a real browser session here.

## Important release status

This is an integrated working **backend plus frontend source project**, but **not a fully release-verified browser build yet**. The remaining release blocker is the frontend dependency/build gate and a real browser walkthrough. On a network-connected machine, run `cd frontend && npm install`, generate and review `package-lock.json`, run `npm run typecheck && npm run build`, then repeat the checks in `README.md`. Do not describe the result as fully offline-ready until an actual Wi-Fi-disabled test passes.

To enable actual vision inference, choose an appropriate compatible local person-detection ONNX model, verify license and preprocessing/output expectations, document attribution and SHA-256, set `VISION_MODEL_PATH`, `VISION_MODEL_LICENSE_REVIEWED=true` and `VISION_MODEL_SHA256`, and confirm the health endpoint reports it is available. A USB/webcam alone does not install or supply a detection model.

## Merge-specific safeguards

- One canonical FastAPI app registers each feature router once.
- The account-specific native schemas remain available; the frontend adapter translates them without replacing persisted records with mock values.
- Only `VERIFIED_SUCCESS` credits the ledger. Rejected, dropped, ignored or failed commands do not.
- Missing inputs/factors remain `UNKNOWN`/`UNAVAILABLE`; UI values are not invented just to make the dashboard look complete.
- No secrets, raw video, camera frames, `node_modules`, Python virtual environments, or generated local database are intended for the delivery archive.
