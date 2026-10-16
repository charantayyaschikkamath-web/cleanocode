# CampusTwin AI — Integrated Local Demo

## Current release status — 16 October 2026

**Backend core verified; React/Vite release still blocked.** A dependency-free fallback UI is now served by the backend at `http://127.0.0.1:8000/demo`; it supports the core scenario/evidence/action/ledger flow without npm. This fallback is not represented as a React/Vite production build. The current local run passed `python -m compileall -q backend scripts tests`, **90 backend/integration tests**, **10/10 synthetic scenario checks**, and a real two-process SQLite persistence/restart check. The source-only frontend scan passed for 33 TypeScript/TSX files and 62 relative imports.

The React/Vite production build is **not verified**: `npm install` failed because this environment could not resolve `registry.npmjs.org` (`EAI_AGAIN`). Frontend dependencies and a package lockfile are therefore absent, and neither browser E2E nor webcam/video analysis has been tested in a browser. A syntax scan is not a substitute for TypeScript type-checking or a production build. Person detection also remains unavailable unless a reviewed compatible local ONNX model is configured.

See [`artifacts/quality/RELEASE_VERIFICATION.md`](artifacts/quality/RELEASE_VERIFICATION.md) for command-by-command results. The restart check can be repeated with `python scripts/verify_persistence_restart.py`; it creates and removes its own temporary database.

---

CampusTwin AI is an evidence-first campus sustainability operations prototype. Its core workflow is **observe → detect → explain → decide → act → independently verify → quantify impact**. This ZIP integrates the workstreams for persisted backend data, deterministic scenario detection, auditable actions, local camera/recorded-video evidence, the digital twin, grounded Copilot, what-if projections, reports, and quality checks.

**Scope truth:** this is a local prototype and controlled simulated demo, not a deployed campus system. Scenario sensor values are labeled `SIMULATED`. Impact results are `PROJECTED` unless the action workflow records `VERIFIED_SUCCESS`; verified simulated outcomes still are not measured real-world savings. The project does not claim a winning probability, field accuracy, deployment, or campus savings.

## Quick start (Windows)

1. Install Python 3.11+ and Node.js 20+ (npm included).
2. Extract this folder to a writable local directory.
3. Copy `.env.example` to `.env`; keep provider credentials server-side. The default config does not require an LLM API key.
4. Open a terminal in the project directory and run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
cd frontend
npm install
cd ..
```

5. Start both processes by double-clicking `start.bat`, or use two terminals:

```powershell
# Terminal 1, from project root, with .venv activated
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

# Terminal 2, from project root
cd frontend
npm run dev
```

6. Open the frontend at `http://127.0.0.1:5173`. The API docs are at `http://127.0.0.1:8000/docs`; health is `http://127.0.0.1:8000/api/v1/health` and API preflight is `http://127.0.0.1:8000/api/v1/preflight`.

## macOS / Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
./start.sh
```

The backend stores its default SQLite database in `data/campustwin.db`. Use a dedicated local demo DB. Never run destructive/reset workflows against production or shared real-user data. `POST /api/v1/ui/demo/reset` closes active simulated incidents and preserves action/audit/ledger history.

## No-build local demo fallback

If npm cannot reach its registry or `frontend/node_modules/vite` is absent, `start.bat` / `start.sh` now starts the backend and opens the built-in fallback at `http://127.0.0.1:8000/demo`. The fallback uses plain local HTML/CSS/JavaScript with no CDN or JavaScript package dependency. It provides dashboard counts, the energy-waste success and dropped-command scenarios, event evidence, action approval/audit history, the verified impact ledger, a simple building/room view, JSON/CSV exports, backend preflight, webcam preview and recorded-video preview/frame sampling when a local detector is configured.

This fallback is a practical way to rehearse the core workflow while the npm registry is blocked. The full React/Vite application remains under `frontend/`; its production build is still a separate release gate and must be built/tested after dependency installation is available.

Manual fallback start after backend dependencies are installed:

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
# Then open http://127.0.0.1:8000/demo
```

## Camera and uploaded-video workflow

The **Camera & video** navigation entry supports two input paths:

- **Live webcam/USB camera:** choose a browser-visible camera and explicitly press Start. Use `localhost` or HTTPS for browser camera permissions. Audio is not requested.
- **Upload a saved video:** select a video file (MP4/WebM recommended; maximum 250 MB and 30 minutes), choose a sampling interval, and start analysis. The browser decodes the recording locally and sends downsized sampled JPEG frames to the local vision endpoint. It does **not** upload or persist the original video. Sampling is limited to 300 frames. Retrospective video evidence is intentionally not allowed to start a live empty-room timer.

**Person detection is not enabled just by connecting a camera.** The project does not bundle third-party model weights and never downloads them on startup. To enable detection, obtain an appropriate local ONNX person-detection model, review its license and source, verify compatible input/preprocessing and output classes, record attribution and SHA-256 in the camera model notes, then set these server-side variables in `.env`:

```dotenv
VISION_MODEL_PATH=vision/models/your-reviewed-model.onnx
VISION_MODEL_LICENSE_REVIEWED=true
VISION_MODEL_SHA256=your-verified-sha256
```

Restart the backend after configuration. The current vision adapter may still reject a model that does not match its expected ONNX output format; use `/api/vision/health` to confirm actual availability. Do not use face recognition, identity matching or biometric inference. If the detector, camera, frame freshness, or coverage is unavailable/uncertain, occupancy remains `UNKNOWN`/`UNAVAILABLE`; a no-person result is not proof that a room is empty. Manual occupancy input is visibly `SIMULATED` and never eligible for an empty-room timer.

## Optional AI Copilot

The Copilot remains usable in `TEMPLATE` mode without a provider key or internet access. To configure an OpenAI-compatible provider, set `COPILOT_API_BASE_URL`, `COPILOT_API_KEY`, and `COPILOT_MODEL` in the backend `.env` file. Do not prefix these values with `VITE_`, expose them to the browser, send video frames, or treat generated prose as a source of numeric truth. Backend formulas remain authoritative. Verify the provider's current availability/pricing before relying on it; no provider is promised to be permanently free.

## Run tests and preflight

Run from project root with `.venv` activated:

```bash
python -m compileall -q backend scripts tests
python -m pytest -q
python scripts/evaluate_scenarios.py --output-dir artifacts/quality
python scripts/preflight.py --json-out artifacts/quality/preflight.json
python scripts/check_offline.py --json-out artifacts/quality/offline-readiness.json
```

The evaluator reports **synthetic test-scenario results**, not real-world detection accuracy. Preflight/offline audits may warn or fail when the frontend has not been built or local detector weights are absent. Those warnings should not be suppressed. When frontend dependencies are prepared, run:

```bash
cd frontend
npm ci
npm run typecheck
npm run build
```

Before a competition demo, prepare dependency caches and the frontend build while connected to a trusted network, then test the app with Wi-Fi disabled on the exact demo machine. The current ZIP intentionally does not include `node_modules`, a production build, raw camera/video samples, secrets, or third-party detector weights.

## Main screens

- **Overview:** persisted KPIs, event feed, priority actions, health/provenance labels.
- **Campus Twin:** clickable 2D building/room view and evidence drill-down.
- **Live Events:** search/filter, evidence, thresholds, provenance, and false-alarm feedback.
- **Actions/Audit:** human approval, state transitions, baseline, post-action verification, and ledger eligibility.
- **Copilot:** grounded explanation with `LLM`, `CACHED`, or `TEMPLATE` mode.
- **What-If Lab:** deterministic projections from a compatible baseline and explicit assumptions.
- **Sustainability Reports:** JSON/CSV evidence packet.
- **Settings/Assumptions:** configurable demo thresholds and optional impact factors.
- **Camera & video:** live webcam/USB input and retrospective local video sampling.

## Trust, privacy and limitations

Camera frames are processed transiently; they must never be written to a database, logs, reports, or copilot requests. No face recognition/identity tracking is implemented. UI controls operate on backend records; an acknowledged command is not success. Only independent `VERIFIED_SUCCESS` creates a verified simulated savings ledger entry. Failed, rejected, dropped, or ignored commands do not increase the ledger. Missing tariff/emissions factors remain unavailable. The local demo is not validated for real campus facilities or safety-critical actuation.

See `docs/MERGE_REPORT.md` for the integration/test record, and `docs/CONTRACTS.md`, `docs/ALGORITHMS.md`, `docs/KNOWN_LIMITATIONS.md`, `docs/THIRD_PARTY_NOTICES.md`, `docs/DEMO_RUNBOOK.md`, and `docs/RELEASE_CHECKLIST.md` before using or pitching the system.
