> **Merged-state note (16 October 2026):** the central app now registers Account 3 actions/scenarios, and the canonical events router includes rule evaluation/evidence/feedback endpoints. The Account 9 integration steps below are historical. See [`MERGE_REPORT.md`](MERGE_REPORT.md) for current status.

---

# Account 3 — Simulator, Detection Rules, and Verified Action Workflow

## Status

Account 3 is implemented against the available Account 2 persistence/services and is separately runnable for integration review. It has deterministic synthetic scenarios, persisted evidence-backed events, a human-approved simulated-action lifecycle, independent post-action verification, and failure paths that do not add impact to the savings ledger.

**The test suite validates software behaviour with synthetic scenarios; it does not establish real-campus detection accuracy, real savings, or control of physical devices.** No real hardware command is sent by this workstream.

## Ownership / files

- `backend/app/simulator/`: scenario contracts and deterministic scenario runner.
- `backend/app/rules/engine.py`: configurable threshold-plus-persistence detection rules.
- `backend/app/services/actions.py`: proposal, human approval/rejection, idempotent lifecycle orchestration.
- `backend/app/services/verification.py`: independent verification of persisted pre/post readings and the atomic success + ledger transaction.
- `backend/app/routers/events.py`: event filters/evaluation/evidence/feedback routes; retains Account 2 event API compatibility.
- `backend/app/routers/actions.py`: proposal, approval, rejection, audit timeline and verification read APIs.
- `backend/app/routers/scenarios.py`: scenarios, scenario runs, logical demo reset.
- `backend/tests/test_account3_workflow.py`: simulator, state-machine and ledger guard tests.
- `backend/app/main_account3.py`: optional launcher for this workstream; the Account 2/9-owned `main.py` remains untouched.

## Main API endpoints

All endpoints use the configured API prefix, `/api/v1` by default.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/scenarios` | Supported scenarios, explicit simulated provenance, current scenario threshold policy |
| `POST` | `/scenarios/run` | Create a reproducible synthetic scenario and persist readings/events/action proposal |
| `GET` | `/scenarios/runs` | List recent persisted scenario runs |
| `POST` | `/scenarios/reset-demo` | Close active simulated incidents and reject pending simulated actions with audit history preserved; requires `confirm: true` |
| `POST` | `/events/evaluate` | Run detection rules over persisted readings |
| `GET` | `/events/{id}/evidence` | Read event snapshot plus linked source readings |
| `POST` | `/events/{id}/feedback` | Add operator feedback, including false-positive feedback |
| `POST` | `/actions/proposals` | Propose a supported action from a qualifying, simulated rule-generated energy event |
| `GET` | `/actions` / `/actions/{id}` | List / inspect actions, verification and any ledger entry |
| `POST` | `/actions/{id}/approve` | Human approval followed by simulated command and independent verification; requires `Idempotency-Key` |
| `POST` | `/actions/{id}/reject` | Reject a pending proposal with an audit transition |
| `GET` | `/actions/{id}/transitions` | Append-only lifecycle trail |
| `GET` | `/actions/{id}/verification` | Latest verification evidence/result |

## Scenario coverage

- `EMPTY_ROOM_HIGH_POWER` → can produce `likely_energy_waste` only when healthy occupancy and power evidence overlap for the configured persistence interval.
- `NIGHT_WATER_FLOW` → can produce `likely_water_anomaly` only when the input explicitly marks a low-use window and the high flow persists.
- `BIN_OVERFLOW` → can produce `likely_bin_overflow` when the measured/simulated fill percentage persists over threshold.
- `INEFFICIENT_ROOM_USE` → can produce `likely_inefficient_room_use` from the declared low-occupancy ratio and sustained high power.
- `NORMAL_OPERATION` → should not generate a waste event.
- `SENSOR_MISSING` / `SENSOR_STALE` → yield evidence-insufficient / unavailable states rather than asserting that a room is empty.
- `COMMAND_DROPPED` → reaches `ACK_TIMEOUT`; no ledger entry.
- `ACKNOWLEDGED_IGNORED` → acknowledgement is recorded but verification fails; no ledger entry.
- `VERIFIED_RESPONSE` → creates a pending proposal; only after human approval and independent measured-in-simulation post-reading comparison can it reach `VERIFIED_SUCCESS`.

Rule names use `likely_*` vocabulary. Thresholds are configurable and explicitly documented as demo defaults, not scientifically validated campus settings. Each event stores its triggering rule, thresholds, source reading IDs, source snapshot, timestamp, unit, provenance and explanatory limitations. There is no fabricated probability/confidence field.

## Action / ledger invariants

1. Only a qualifying rule-generated simulated energy event can propose the supported reduce-power action.
2. The baseline is frozen before command dispatch and links to persisted reading IDs.
3. A human approval is mandatory; the action simulator does not control real hardware.
4. Action transitions are recorded through Account 2's append-only transition mechanism, with an idempotency key for approval requests.
5. `ACKED` is not treated as success. Post-action readings must be compatible, healthy, linked and compared with the baseline within the configured virtual-time window.
6. The final verification record, `VERIFIED_SUCCESS` transition and exactly one simulated-savings ledger row are committed in a single database transaction. A failed result, drop, timeout, rejection or replay must not add savings.
7. Repeated approval with the same idempotency key reuses the recorded action outcome; it must not create a duplicate command, verification or ledger entry.
8. Demo reset is a logical reset, not destructive erasure: it closes active simulated incidents and rejects pending actions while preserving readings, audit history, verification records and the impact ledger.

## Local run

Requires Python 3.11+ and the `backend/requirements.txt` dependencies.

Windows PowerShell, from the repository root:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main_account3:app --reload --env-file ../.env
```

macOS/Linux, from the repository root:

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main_account3:app --reload --env-file ../.env
```

Open `http://127.0.0.1:8000/docs`. The core/Account 2 routes are available through the base app, and this Account 3 shim adds action/scenario routes. Use an empty/test SQLite database for review rather than reusing a database containing valuable operator history.

## Test commands and results

Run from `backend/`:

```bash
python -m compileall -q app tests
python -m pytest -q
```

The completed run for this package reported **33 passed** (21 Account 2 core tests + 12 Account 3 workflow tests). These are synthetic and application-level tests, not real-world accuracy measurements. Re-run tests after integrating into the canonical repository.

The Account 3 tests cover successful detection; the human-approval requirement; final verification before ledger insertion; duplicate approval; dropped command; acknowledged-but-ignored command; normal operation; missing/stale readings; other-resource scenarios; duration below persistence; evidence immutability under false-positive feedback; invalid transitions and rejection; safe reset; invalid scenario/outcome combinations; recovery after stale sensors return to healthy operation; and rejection of action proposals based on manually asserted events without rule evidence.

## Account 9 integration instructions

`backend/app/main.py` remains unchanged because Account 9 owns the canonical entrypoint. For final integration, import the two routers and add them to the router registration loop in `app.main.create_app`:

```python
from app.routers import actions, scenarios

# Include actions.router and scenarios.router in the existing router list.
# Existing events.router already points to the Account 3-extended events router.
for router in (
    health.router,
    buildings.router,
    readings.router,
    events.router,
    impact.router,
    facts.router,
    ledger.router,
    actions.router,
    scenarios.router,
):
    app.include_router(router, prefix=settings.api_prefix)
```

Then use the canonical launcher (normally `app.main:app`) and remove the temporary `app.main_account3` shim if desired. Do not register routes twice.

## Contract reconciliation required before release

The Account 1 contract pack and Account 2 implementation were both available, but Account 2's integration note explicitly states that its local schema choices have not yet been reconciled with the proposed shared contract. Account 9/Account 1 must compare exact enum values, verification record fields, source-health vocabulary, event lifecycle states, route names, and schema field names before declaring integration complete. Confirmed examples to reconcile: Account 1 lists `ERROR` as a source status while Account 2 currently accepts `HEALTHY | STALE | UNAVAILABLE | UNKNOWN`; Account 1 event statuses omit `CLOSED` while Account 2 supports it and demo reset currently uses it; Account 1 example payloads use a verification `outcome`, while Account 2 persists/serializes a `result`. This module intentionally reuses Account 2's actual persistence models and does not silently rewrite shared schemas.

## Known limits

- Sensor streams, water/bins/occupancy and action outcomes in the scenarios are labelled synthetic; test success is not an accuracy claim.
- The supported simulated actuation is limited to `SIMULATED_REDUCE_POWER` for a qualifying energy-waste event. This module does not command physical switches/valves.
- Water anomaly detection requires an explicit low-use window; no water savings are created by the energy-action workflow.
- The current Account 2 feedback model has no unique idempotency field. Event feedback uses the supplied key for request correlation but not for strong database-level deduplication. That needs a shared-contract/schema decision before treating feedback submission as exactly-once.
- Exact rule limits must be calibrated with campus meter semantics, realistic persistence windows, local schedules and operator review before any real deployment.
