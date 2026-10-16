# CampusTwin AI — Release Verification

**Run date:** 16 October 2026  
**Environment:** Linux container; Python 3.13.5, Node.js 22.16.0, npm 10.9.2  
**Release status:** Backend core checks pass, and a dependency-free fallback UI is served at `/demo`. The React/Vite production build and browser workflows remain blocked/unverified.

## Results from commands executed in this workspace

| Check | Actual result | Evidence / qualification |
|---|---|---|
| `python -m compileall -q backend scripts tests` | PASS | Exit code 0 after adding the restart verification script. |
| `python -m pytest -q` | PASS — 91 passed | Fresh run: 91 tests passed in 4.18 seconds. Includes merged API/action/ledger, copilot, what-if, camera fallback coverage, and a test that verifies the no-build demo page route. |
| `python scripts/evaluate_scenarios.py --output-dir artifacts/quality` | PASS — 10/10 | Fresh run. Synthetic scenarios only; not real-world detection accuracy or actual campus savings. Current outputs: `scenario-evaluation.json` and `scenario-evaluation.md`. |
| `python scripts/verify_persistence_restart.py` | PASS | Started the backend, ran successful and dropped-command actions, stopped the process, restarted against the same temporary SQLite database, and verified persistence. Report: `persistence-restart-current.json`. |
| TypeScript syntax and relative-import scan | PASS — 33 files, 62 relative imports | `frontend-source-scan-current.json`: zero syntax diagnostics and zero missing local relative imports. This is not a full type-check. |
| No-build fallback UI syntax/route | PASS | The backend test suite confirms `GET /demo` serves HTML containing the scenario and video controls. The inline JavaScript also passes `node --check`. This does not equal real-browser interaction testing. |
| `npm install --no-audit --no-fund --fetch-retries=0 --fetch-timeout=20000` | BLOCKED | npm failed with `EAI_AGAIN` while resolving `registry.npmjs.org`. No packages were installed and no lockfile was generated. |
| `tsc -b --pretty false` | BLOCKED | The global TypeScript compiler ran, but declared local packages `react`, `react-dom`, `lucide-react` and React type/runtime declarations are unavailable. The resulting JSX/type diagnostics are not sufficient to determine whether a clean dependency-installed type-check passes. |
| `npm run typecheck` | BLOCKED — exit 1 | Local React/Lucide packages and React JSX runtime/types are absent, cascading into TypeScript diagnostics. This environment cannot determine the clean install type-check result. |
| `npm run build` | BLOCKED — exit 1 before Vite | The `tsc -b` stage failed on absent React/Lucide packages; the chained `vite build` stage was not reached and no bundle was created. |
| Preflight | FAIL — 29 PASS, 5 WARN, 1 FAIL | The sole hard failure is missing `frontend/dist` assets. Warnings include missing lockfile/database before first startup, optional LLM key, and reviewed local vision model. Report: `preflight-current.json`. |
| Offline readiness | FAIL — 1 PASS, 4 WARN, 2 FAIL | Fails due to absent frontend lockfile/build and no prepared offline package cache. Report: `offline-readiness-current.json`. |
| Browser walkthrough / frontend-backend E2E | NOT TESTED | The `/demo` HTML route and JavaScript syntax were checked, but no real browser automation/run was available. |
| Live webcam and uploaded-video inference | NOT TESTED | Source inspection confirms selection/preview and sampled-frame workflow code, but the browser workflow could not be run. No reviewed ONNX detector weights are configured. |

## No-build fallback for local rehearsal

When `frontend/node_modules/vite` is missing, `start.bat` and `start.sh` now start the backend and direct the user to `http://127.0.0.1:8000/demo`. This dependency-free page provides the core dashboard, synthetic scenario triggers, event/evidence details, action approval/audit, verified ledger, basic building/room selection, CSV/JSON exports, preflight view, live camera preview and local video preview/sampled-frame analysis when a compatible local detector is actually available. It is a separate HTML/CSS/JavaScript fallback; it is **not** described as a React/Vite production build. Its route is covered by pytest and its inline JavaScript passes `node --check`, but the controls have not been tested in a real browser.

## Persistence/release workflow verified

The repeatable restart script proved the following against one temporary SQLite database:

1. Backend process #1 starts and the dashboard API returns HTTP 200.
2. An `empty_room_high_power` scenario creates a persisted event and action.
3. Approving the successful scenario reaches `VERIFIED_SUCCESS` and creates exactly one simulated ledger entry.
4. A second scenario configured as `COMMAND_DROPPED` reaches `ACK_TIMEOUT` and does not increase the ledger.
5. The backend process is terminated and restarted against the same database.
6. Both event records and both action states persist; the ledger still has exactly one entry.
7. The temporary database is deleted by the script.

Run it again with:

```bash
python scripts/verify_persistence_restart.py
```

## Remaining release blockers

1. Restore authorized network/DNS access to the npm registry or provide a reviewed dependency cache.
2. In `frontend/`, install dependencies and generate a real lockfile, then run:

   ```bash
   npm install
   npm run typecheck
   npm run build
   ```

3. Fix any genuine type/build errors revealed after the actual React/Vite packages are present.
4. Open `http://127.0.0.1:8000/demo` in a real browser and test the fallback controls against the backend.
5. Run the full React frontend in a browser after a successful Vite build and test its primary controls.
6. Test webcam permission/device states and uploaded-video preview/cancellation in a browser. To test actual person detection, configure a reviewed compatible ONNX model and validate its input/output format. Without it, the app must report detector availability honestly.
7. Repeat preflight, offline readiness, and the final release walkthrough after build completion.

## Trust boundary

The scenario evaluation is synthetic. A `VERIFIED_SUCCESS` ledger entry in the simulator represents a verified simulated result, not measured savings at a real campus. Camera/video detection is not validated until an actual configured model and browser test demonstrate it. The current project is **not yet production-ready as a complete browser application**.
