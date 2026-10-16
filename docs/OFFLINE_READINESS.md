# Offline Readiness and Clean Setup

## Current status

The project has a standard-library offline audit at `scripts/check_offline.py`, but **offline-ready is not an assumed status**. A committed frontend lockfile, prepared Python wheelhouse, reviewed optional vision weights, and a successful Wi-Fi-off walkthrough are still required before the release can be described as offline-ready.

## Prepare while online

1. Use the documented Python version (3.11+) and an approved Node.js/npm LTS installation.
2. Resolve the frontend dependency tree, review `frontend/package.json`, generate and commit `frontend/package-lock.json`, then use `npm ci` rather than an unpinned `npm install` for release builds.
3. Prepare pinned Python dependencies into the wheelhouse:

   ```bash
   python scripts/prepare_offline.py --prepare-python
   ```

   This command downloads packages from configured package indexes, so run it only in a trusted connected environment. Inspect the exact package list and license notices. If the backend requirements are changed, regenerate the wheelhouse.
4. Prepare the frontend after committing the lockfile:

   ```bash
   python scripts/prepare_offline.py --build-frontend
   ```

5. Model weights are **not downloaded** by startup or these scripts. If using local inference, select a compatible model, review its license/redistribution rights, record hash/source in `docs/camera-vision/MODEL_LICENSES.md`, place the file locally and configure `VISION_MODEL_PATH`. Do not include unreviewed weights in an event submission.
6. Run the audits and tests:

   ```bash
   python scripts/check_offline.py --json-out artifacts/quality/offline-readiness.json
   python scripts/preflight.py --json-out artifacts/quality/preflight.json
   python -m compileall -q backend scripts tests
   python -m pytest -q backend/tests tests
   ```

## Prove it offline

After dependency and frontend build preparation, disable Wi-Fi/network access on the same demo machine and repeat the commands above plus a browser walkthrough. Verify locally served JS/CSS/fonts, backend DB startup, simulator scenarios, report export, error/retry states, and camera-unavailable handling. Record actual command output in `artifacts/quality/VALIDATION_REPORT.md`.

A static audit does not prove every application path is offline-safe. Keep screenshots/logs only from the actual run and describe any untested browser route as unverified.

## What can require network or optional configuration

- Python/npm package preparation and initial install, unless a wheelhouse/cache is already prepared.
- Any configured remote LLM endpoint; core Copilot must use its truthful template/cached fallback when unavailable.
- Real campus sensors and real actuator control are not bundled; no hardware integration is claimed.
- Optional local vision inference requires an operator-supplied compatible model file and its runtime dependencies. Without it, camera inference must return unavailable/unknown and never auto-download model weights.
- Maps, remote fonts, external CDN scripts, telemetry and online map tiles must not be required by the release build.

## Security notes

Keep `.env` private, never publish API keys in frontend `VITE_*` variables, keep camera frames in memory only, do not send them to the LLM, and do not store frames in logs/reports. The absence of an LLM key or a vision model should be a clear warning and a supported reduced-capability state—not a false overall success claim.
