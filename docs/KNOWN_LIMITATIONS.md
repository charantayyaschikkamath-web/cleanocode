# Known Limitations — Current Integrated Build

This list reflects the merged source as currently tested. Re-check it before each release or pitch.

## Confirmed limitations

1. **Not a campus deployment.** The project is a local prototype; no campus pilot, partnership, measured savings, or real-world detector benchmark is claimed.
2. **Frontend build gate remains blocked in this environment.** The npm registry request failed with DNS `EAI_AGAIN`. As a result, this workspace has no verified `frontend/package-lock.json`, `frontend/node_modules`, production `frontend/dist`, TypeScript project typecheck, or browser E2E walkthrough. Source syntax was parsed separately; that is not a substitute for a build.
3. **Local model weights are not bundled.** The Camera & video page is present, but actual person inference requires an operator-supplied compatible local ONNX model, runtime availability, license/source/hash review and a successful `/api/vision/health` check. Without it, the service must report `UNAVAILABLE`.
4. **Real hardware control is not configured.** Approve/reject and verification flows act on deterministic simulated commands; there is no actuator driver or verified connection to campus electrical/water systems.
5. **Impact numbers depend on evidence and config.** Cost and carbon stay unavailable if tariff/emission factors are unset. What-if estimates are projections, not verified savings. Verified simulated ledger entries are not measured campus savings.
6. **Official competition rules are unknown.** No official event URL or judging rubric was provided. Do not present provisional weights as the event's actual scoring criteria.
7. **Authentication is not a full production authorization system.** API access is intended for local, loopback-bound demo use. Before deployment, add real operator authentication/authorization, secret management, network hardening, retention controls and an approved campus security review.
8. **No full offline-ready frontend package yet.** No npm lockfile/build or Python wheelhouse has been prepared; an offline readiness audit currently reports blockers. Do not claim Wi-Fi-off readiness until it is tested on the target device.

## Risk controls already in the code

- Unknown, stale, missing or unhealthy source evidence does not become a confident empty-room or normal-state claim.
- No face recognition, identity matching, biometric inference or identity tracking is implemented.
- Raw camera/video frames are not written to DB/logs/reports or sent to the Copilot. Uploaded recordings are decoded locally in the browser and only sampled downsized JPEG frames are sent to the configured backend.
- Human approval precedes simulated actions. An acknowledgement is not verification; dropped/ignored/failed actions do not credit the ledger.
- Scenario inputs and simulated occupancy remain labelled `SIMULATED`; missing cost/carbon factors remain unavailable.

## Before any real-world use

Calibrate and validate detectors against appropriately governed data; review model/data licenses, privacy, notice and retention; validate sensor units/freshness and rules with campus staff; implement authenticated roles, operational monitoring, security controls and safe fallbacks; integrate hardware only behind tested and authorized adapters; and validate savings with an agreed measurement/verification method.
