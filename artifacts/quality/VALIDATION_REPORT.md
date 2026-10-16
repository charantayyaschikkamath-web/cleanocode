# CampusTwin AI — Integrated Validation Report

**Run date:** 16 October 2026. **Workspace:** merged Accounts 1–8. **Environment:** Python 3.13.5, Node.js 22.16.0, npm 10.9.2. Generated test and preflight outputs sit alongside this report.

## Results

| Check | Actual result | Meaning |
|---|---|---|
| Python compile | **PASS** — `python -m compileall -q backend scripts tests` | Python backend/scripts/tests compile successfully. |
| Automated tests | **PASS** — **91 passed in 4.18s** | API/unit/integration suite passes using an in-memory database override for the test run. This is not a browser E2E or real-campus validation. |
| Scenario evaluation | **PASS** — **10/10 synthetic scenarios** | Resource detection, normal/unknown handling, command drop/ignore, verification and ledger invariants matched expected outcomes. See `scenario-evaluation.json` and `.md`. |
| Canonical backend smoke | **PASS** — health HTTP 200 and OpenAPI HTTP 200; dashboard, vision health, Copilot and preflight routes were present | See `backend-startup-smoke.json`. A separate real process restart test is now also available in `persistence-restart-current.json`. |
| Frontend source scan | **PASS** — 33 TypeScript/TSX files parsed, zero syntax diagnostics; 62 relative imports inspected, zero missing local targets | This is a syntax/path scan only, not dependency-backed type checking or browser execution. See `frontend-syntax-scan.json`. |
| Release preflight | **FAIL** — 29 PASS / 5 WARN / 1 FAIL | The only FAIL is missing built frontend assets. Warnings cover an uncreated local DB (normal before first launch), optional LLM key, optional model weights, missing frontend lockfile and offline dependency preparation. See `preflight.json`. |
| Offline readiness | **FAIL** — 1 PASS / 4 WARN / 2 FAIL | The two blockers are missing `frontend/package-lock.json` and `frontend/dist/index.html`. No Python wheelhouse or local vision weights are prepared. See `offline-readiness.json`. |
| Frontend production build | **BLOCKED — explicitly attempted** | `npm run build` stopped at `tsc -b` because React/Lucide dependencies and their types were not installed. `npm install` timed out; `registry.npmjs.org` could not be resolved. The chained `vite build` did not run. See `FRONTEND_PRODUCTION_BUILD_ATTEMPT.md`. |
| Browser camera/video test | **NOT RUN** | Upload UI and local frame-sampling code were added and syntax-scanned, but a real browser session was not available here. No camera hardware or reviewed local ONNX model was provided for real inference. |

The no-build fallback UI at `/demo` is covered by the current test suite and its inline JavaScript passes `node --check`; no real-browser interactions are claimed.

## Fresh release-gate follow-up

`RELEASE_VERIFICATION.md` is the current command-by-command source of truth. The newly added `scripts/verify_persistence_restart.py` passed against a temporary SQLite database: two events and two action states survived a complete backend process restart; verified success added one ledger entry; a dropped command added none. The current npm install attempt specifically failed with `EAI_AGAIN` resolving `registry.npmjs.org`.

## Scenario evidence summary

- Empty room/high power, night water flow, bin overflow and inefficient-use scenarios emitted expected event types.
- Normal operation emitted no event; missing and stale sensor scenarios returned evidence-insufficient/unavailable results rather than a confident empty-room claim.
- Dropped command ended at `ACK_TIMEOUT`; acknowledged-but-ignored ended at `VERIFICATION_FAILED`; neither changed the ledger.
- Verified response reached `VERIFIED_SUCCESS` and created exactly one simulated ledger entry; repeating approval with the idempotency key did not create a duplicate.

All ten results are **synthetic test-scenario results**. They are not real-world accuracy, measured environmental impact, or actual campus savings.

## What is and is not verified

The integrated backend route graph and tests are green, and the source contains an uploaded-video flow. An explicit `npm run build` attempt is recorded, but could not get past TypeScript startup because the registry was unreachable and frontend packages were absent. The full web app is **not release-verified yet** because the frontend dependency install/build gate and browser walkthrough remain incomplete. The uploaded-video path decodes the selected video in the browser and sends sampled/downscaled frames to the configured backend endpoint; it does not upload or persist the original video file. Retrospective samples are intentionally not eligible for real-time empty-room timers. Actual detections require a compatible, locally configured, license-reviewed ONNX model; no model weights or credentials are bundled.

## Release steps still required

1. On a network-connected machine, run `cd frontend`, `npm install`, inspect and commit the generated `package-lock.json`, then run `npm run typecheck` and `npm run build`. In this attempt, syntax/path scanning passed but dependency-backed typechecking and bundling remain unverified.
2. Fix any real type/build errors discovered by those commands, rerun backend tests and both audits, then exercise the UI in a browser against the integrated backend.
3. Test webcam selection and uploaded-video sampling in a real browser; verify permissions/error states and confirm frames/raw files are not saved.
4. If actual inference is needed, select a compatible model, review its license and preprocessing/output contract, record provenance/hash, configure `VISION_MODEL_PATH`, and confirm `/api/vision/health` honestly reports availability.
5. Only describe the system as offline-ready after preparing dependency caches/build artifacts and proving the app launches with Wi-Fi disabled.

No `package-lock.json`, frontend build output, local database, camera frames, raw video, secrets, model weights, or `node_modules` were fabricated or included to make the release gates appear green.
