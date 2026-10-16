# CampusTwin AI — Three-Minute Demo and Recovery Runbook

## Before the demo

1. Check the actual event rubric, time limit, data/hardware rules, permitted APIs, and submission requirements. The official event identity/rubric has not been supplied in this repository and must not be invented.
2. Create/activate the project's virtual environment and install `backend/requirements.txt`. In a network-connected setup environment, install the exact frontend packages with `cd frontend && npm install` (then use the reviewed lockfile if one is available). This workspace's current frontend lock/build is not complete; see `artifacts/quality/VALIDATION_REPORT.md`.
3. Run `python -m pytest -q` and `python scripts/evaluate_scenarios.py --output-dir artifacts/quality`. Treat the reports as synthetic engineering evidence only.
4. Start the integrated app, not `main_account3.py`:

   ```bash
   python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
   ```

   In another terminal, after installing frontend dependencies: `cd frontend && npm run dev -- --host 127.0.0.1`. Open `http://127.0.0.1:5173`; API docs are at `http://127.0.0.1:8000/docs`.
5. Verify `/api/v1/health`, `/api/v1/preflight`, and `/api/vision/health`. If local model weights are absent, explicitly say that real camera inference is currently unavailable. Do not use manual simulated occupancy as a real camera result.
6. Rehearse the complete demo twice on the machine to be used. A frontend/browser walkthrough has not been recorded as passed by the current build environment.

## Three-minute narrative

### 0:00–0:20 — Problem and scope

“CampusTwin connects sustainability signals, evidence-backed alerts, human-approved action, independent verification, and transparent impact accounting. This local demonstration labels scenario inputs as SIMULATED rather than live campus measurements.”

Open the integrated overview and point out source/provenance and health labels.

### 0:20–0:55 — Evidence before conclusion

Run **Empty room + high power**. Open the event to show the triggering rule, linked reading snapshots, threshold and `SIMULATED` provenance. Explain that a power reading alone does not prove an empty room. Briefly trigger missing/stale sensor evidence to demonstrate `UNKNOWN`/`UNAVAILABLE` handling.

### 0:55–1:35 — Approve and independently verify

Approve the proposed simulated action. Show the append-only state sequence and baseline/post-action comparison. Say that command acknowledgement is not proof of success. The ledger should change only after the configured verification rule returns `VERIFIED_SUCCESS`.

### 1:35–2:00 — Deliberate failure

Select a dropped-command or acknowledged-but-ignored scenario. Show `ACK_TIMEOUT` or `VERIFICATION_FAILED` and the unchanged ledger. This is the trust moment: failure must not be presented as saved resources.

### 2:00–2:30 — Impact and Copilot

Show the deterministic energy formula, provenance, observation period, and configured assumptions. Cost or CO₂ results should be `UNAVAILABLE` if factors are missing. Ask the Copilot to explain the event; point out whether the response mode is `LLM`, `CACHED`, or `TEMPLATE`.

### 2:30–3:00 — Video path and honest next step

Open **Camera & video**. When detector weights and runtime are configured, demonstrate live USB/webcam or upload a short sample recording. The upload path samples frames locally in the browser; it does not upload/store the original video. If weights are absent, show the accurate unavailable status. Explain what needs a model/license review and real campus integration before deployment.

## Recovery / fallback

- **Frontend build/install unavailable:** use the backend's `/docs` and latest `artifacts/quality/scenario-evaluation.md`; do not pretend the app has passed a browser test.
- **Copilot provider unavailable:** continue in `TEMPLATE` mode; do not block the core workflow on the LLM.
- **Camera/model unavailable:** explicitly state `UNAVAILABLE`; continue with the labelled simulator and never claim it came from the camera.
- **Verification failure:** preserve the failure state and unchanged ledger. Do not reset or alter records just to produce a green result.

## Reset safely

The reset endpoint is a non-destructive logical reset. It closes active simulated events and rejects pending demo actions while preserving the action audit and impact ledger. Point it only at a dedicated local demo database:

```bash
python scripts/reset_demo.py --base-url http://127.0.0.1:8000 --confirm --reason "Before judge demo"
```

Never run reset commands against a production or shared real-user database.

## Dependency-free local rehearsal when npm is unavailable

If `frontend/node_modules/vite` is absent, `start.bat` / `start.sh` now opens the backend-served fallback at `http://127.0.0.1:8000/demo`. It is a separate plain HTML/CSS/JavaScript local UI and does not require CDN assets or npm packages. It is **not** the React/Vite production build.

Suggested core rehearsal:

1. Click **Run** for “Energy waste · successful response”. The request creates a labelled synthetic scenario and persisted evidence; inspect the selected event in **Events & evidence**.
2. Open **Actions & audit** and approve the pending action. Check that it reaches `VERIFIED_SUCCESS` and that a single simulated ledger entry appears on Overview.
3. Run “Energy waste · dropped command”, approve the new action and confirm it reaches `ACK_TIMEOUT` while the ledger count does not increase.
4. Refresh the page or restart the backend and confirm that the scenario/action/ledger records persist.
5. In **Camera & video**, test camera permissions and local recorded-video preview. If the health panel reports `DETECTOR UNAVAILABLE`, inference intentionally remains unavailable; do not demonstrate a person count until a reviewed, compatible local model is configured.
6. Export the JSON/CSV evidence packet in **Reports & system**.

Automated release checks: `python -m pytest -q`, `python scripts/evaluate_scenarios.py --output-dir artifacts/quality`, and `python scripts/verify_persistence_restart.py`. A real-browser walkthrough is still required before declaring all UI workflows verified.
