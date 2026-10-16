# Algorithms and Evaluation Map

This document describes the code in the **integrated local demo**. Default detection thresholds are configurable demonstration settings, not campus-calibrated production limits.

| Feature | Implemented algorithm / rule | Code location | Automated evidence | Important limitation |
|---|---|---|---|---|
| Persisted impact calculation | Decimal-safe energy conversion, `kWh = (watts / 1000) × virtual_seconds / 3600`; tariff and CO₂ factors are optional and never silently defaulted | `backend/app/core/impact.py` | `backend/tests/test_impact.py`, `backend/tests/test_action_ledger.py` | A calculation/projection is not measured or causally attributable campus savings. |
| Energy waste | Requires healthy repeated high-power readings and corresponding healthy occupancy evidence over the persistence window | `backend/app/rules/engine.py`; `backend/app/simulator/schemas.py` | `backend/tests/test_account3_workflow.py`; `tests/quality/test_scenario_evaluator.py` | Default power threshold and persistence are demo defaults, not a trained predictive model. |
| Water anomaly | Persistent healthy flow at/above the configured limit in a defined low-use window | `backend/app/rules/engine.py` | `backend/tests/test_account3_workflow.py`; scenario evaluator | A flow anomaly does not alone prove a physical leak or quantify avoided water. |
| Bin overflow | Consecutive healthy waste-fill samples crossing the configured threshold for the persistence interval | `backend/app/rules/engine.py` | `backend/tests/test_account3_workflow.py`; scenario evaluator | The reproducible demo event is simulated; no real bin detector is bundled. |
| Inefficient room use | Combines sustained elevated power with healthy occupancy and a capacity ratio heuristic | `backend/app/rules/engine.py` | `backend/tests/test_account3_workflow.py`; scenario evaluator | The ratio is an explainable heuristic, not a learned score. |
| Missing/stale/unhealthy evidence | Blocks confident resource classification and reports insufficient/unavailable evidence | `backend/app/rules/engine.py` | `backend/tests/test_clock_and_safety.py`; scenario evaluator | `UNKNOWN` never means empty, normal, or confirmed waste. |
| Human-approved action | Appends action state transitions; approval is idempotent; ACK proceeds to separate verification | `backend/app/services/actions.py`; `backend/app/repositories.py` | `backend/tests/test_account3_workflow.py`; `backend/tests/test_action_ledger.py`; `tests/integration/test_merged_app.py` | The current action driver is simulated and does not control real campus equipment. |
| Independent verification | Captures baseline, creates post-action simulated readings, compares observed change with configured threshold | `backend/app/services/verification.py` | `backend/tests/test_action_ledger.py`; scenario evaluator; merged-app integration tests | Verifies only that the simulator met its condition, not physical-world results. |
| Savings ledger | Only independently `VERIFIED_SUCCESS` actions credit a ledger entry; failures/replays do not duplicate entries | `backend/app/services/actions.py`; `backend/app/services/verification.py` | `backend/tests/test_action_ledger.py`; scenario evaluator; merged-app integration tests | Verified simulated impact remains simulated—not measured savings. |
| Copilot | Builds context from persisted structured records; validates provider narrative; falls back to template/cached output; backend owns all numeric facts | `backend/app/integration/facts_adapter.py`; `backend/app/copilot/service.py`; `backend/app/copilot/provider.py` | `tests/copilot/test_copilot_service.py`; `tests/copilot/test_router.py`; merged-app integration test | No API key is needed for `TEMPLATE` mode; provider availability is not guaranteed. |
| What-if projection | Computes avoided and remaining energy from room baseline, intervention and duration; omits unsupported cost/CO₂ results | `backend/app/what_if/engine.py`; `backend/app/routers/ui.py` | `tests/copilot/test_what_if.py`; merged-app integration test | Projection only. It issues no device command and adds no ledger row. |
| Camera / uploaded-video evidence | Local configurable person-only inference with rolling count smoothing, input-health checks and fail-closed states. The browser decodes a selected recording locally and sends sampled JPEG frames only. | `backend/app/vision/inference.py`; `backend/app/vision/service.py`; `frontend/src/features/camera/CameraPanel.tsx` | `backend/tests/test_vision_service.py`; `backend/tests/test_vision_api.py`; merged-app integration test | No model weights are bundled, and detector availability is not verified in this environment. No face recognition or identity tracking. Uploaded-video evidence is retrospective and cannot start a live empty-room timer. |
| Frontend syntax | Parses all `.ts` / `.tsx` source files using the globally available TypeScript transpiler | `frontend/src/` | Latest source syntax check recorded in `artifacts/quality/VALIDATION_REPORT.md` | Full `tsc` typecheck, Vite production build and browser E2E are still blocked because npm dependencies could not be retrieved in this environment. |
| Release preflight | Static config/dependency/file/router-registration checks with repair suggestions; optional live route inventory | `scripts/preflight.py` | `tests/quality/test_preflight.py`; `artifacts/quality/preflight.json` | Static checks do not substitute for a browser walkthrough or real hardware validation. |
| Offline readiness | Audits build/lockfile/assets/requirements/wheelhouse/model readiness | `scripts/check_offline.py` | `tests/quality/test_offline_audit.py`; `artifacts/quality/offline-readiness.json` | Current report is intentionally not green: the frontend build/lockfile and model/wheelhouse are not prepared. |
| Synthetic scenario evaluation | Executes ten deterministic scenarios and checks expected event/action outcomes, provenance, idempotency and ledger invariants | `scripts/evaluate_scenarios.py` | `tests/quality/test_scenario_evaluator.py`; `artifacts/quality/scenario-evaluation.*` | These are test-scenario results, not real-world accuracy, production reliability or campus savings. |

## Standard synthetic scenario catalog

`GET /api/v1/scenarios` advertises the supported scenarios. The evaluator covers:

- `EMPTY_ROOM_HIGH_POWER` → `likely_energy_waste`.
- `NIGHT_WATER_FLOW` → `likely_water_anomaly`.
- `BIN_OVERFLOW` → `likely_bin_overflow`.
- `INEFFICIENT_ROOM_USE` → `likely_inefficient_room_use`.
- `NORMAL_OPERATION` → no event.
- `SENSOR_MISSING` → insufficient evidence.
- `SENSOR_STALE` → unavailable evidence.
- `COMMAND_DROPPED` → `ACK_TIMEOUT`, ledger unchanged.
- `ACKNOWLEDGED_IGNORED` → `VERIFICATION_FAILED`, ledger unchanged.
- `VERIFIED_RESPONSE` → `VERIFIED_SUCCESS`, one `VERIFIED_SIMULATED` ledger entry; idempotent replay adds no second entry.

Rerun the evaluator and automated tests after code changes. Never describe synthetic scenarios as a field benchmark.
