> **Merged-state note (16 October 2026):** this is the original Account 2 handoff, preserved for implementation history. The canonical integration is now in `backend/app/main.py`; current route/facts status and remaining release blockers are documented in [`MERGE_REPORT.md`](MERGE_REPORT.md). Do not follow this document as a statement that the other routers remain unregistered.

---

# Account 2 — Integration Notes and Assumptions

## Integration status

The provided source was the CampusTwin AI Competition-Optimized Build Prompt Pack, not an existing repository. Account 1's `docs/CONTRACTS.md` and `docs/FILE_OWNERSHIP.md` were not supplied. Therefore, this workstream defines a coherent local contract, but these exact schema/route choices must be compared to Account 1's frozen contracts before merging. This is an explicit integration dependency, not a claim that the shared contract has already been approved.

## Suggested ownership in the shared repo

- `backend/app/core/`: settings, logging, request/error dependencies, clock, impact engine, overview facts.
- `backend/app/db/`: SQLAlchemy base, database/session setup, persistent models and schema version.
- `backend/app/schemas.py`: Account 2 request/response types, subject to shared-contract review.
- `backend/app/repositories.py`: core data services and safe verified-ledger write guard.
- `backend/app/routers/`: health, metadata, readings, event persistence/read views, facts, impact, and ledger read endpoint.

The central app entrypoint and module registration should be reconciled by Account 9. This standalone package currently registers the Account 2 routers in `app/main.py` only to make it runnable and testable.

## Shared vocabulary in this implementation

- Provenance: `REAL`, `SIMULATED`, `DERIVED`.
- Reading health: `HEALTHY`, `STALE`, `UNAVAILABLE`, `UNKNOWN`.
- Action states: `PENDING_APPROVAL`, `COMMAND_SENT`, `ACKED`, `VERIFYING`, `VERIFIED_SUCCESS`, `REJECTED`, `COMMAND_FAILED`, `ACK_TIMEOUT`, `VERIFICATION_FAILED`, `VERIFICATION_TIMEOUT`.
- Ledger statuses: `VERIFIED_SIMULATED`, `MEASURED`.
- Time storage: timezone-aware UTC at service boundaries and UTC storage/serialization. SQLite's lack of timezone-preserving `DATETIME` storage is handled by `UTCDateTime`.

Account 1 may select different exact spellings; if so, change them in one reviewed contract change rather than letting modules diverge.

## Persistence model

| Table | Purpose |
|---|---|
| `buildings`, `rooms` | Persistent campus location metadata |
| `sensor_readings` | Time-stamped values, units, status, age/freshness and provenance |
| `events` | Event state, rule name, evidence IDs, immutable evidence snapshot and provenance |
| `event_feedback` | Operator false-alarm/resolution feedback |
| `actions` | Current action state, event reference, idempotency key and baseline IDs |
| `action_transitions` | Append-only per-action transition history |
| `verification_records` | Baseline/post-action evidence and required vs observed change |
| `savings_ledger` | Single verified impact entry per successful action, with formula inputs and assumptions |
| `scenario_runs` | Reproducible scenario request/result and separate wall/virtual timestamps |
| `schema_versions` | Explicit version tracking for safe initialization |

The SQLite setup turns on foreign-key enforcement and `busy_timeout`. Action-transition update/delete triggers prevent ordinary SQL writes from altering or removing audit history. Future migrations must preserve those triggers.

## Services Account 3 should reuse

```python
from app.repositories import (
    create_action_record,
    append_action_transition,
    record_verification,
    record_verified_savings,
)
```

- Create the action once with a stable `idempotency_key` and frozen baseline reading IDs.
- Call `append_action_transition` for each valid state change. Use a stable per-request key when possible.
- Save verification snapshots before attempting a ledger write.
- Write the ledger only using the transition row whose `new_state` is exactly `VERIFIED_SUCCESS`.
- Never translate `ACKED` into success. The service rejects it because there is no `VERIFIED_SUCCESS` transition and the action state is not successful.
- For `MEASURED` entries, provide real, healthy, persisted reading IDs from the same building and (when applicable) room. Synthetic readings cannot be marked measured.

The service's transition map is a defensive baseline, not a replacement for Account 3's fuller simulator/state machine. The simulator still needs explicit dropped-command, acknowledged-but-ignored, and timeout behavior plus its own scenario tests.

## Facts/KPI contract

`GET /api/v1/facts/overview` returns `schema_version`, `as_of`, `open_events`, latest persisted reading by resource type, and verified ledger totals for energy, cost, water and CO₂. Each metric includes availability, provenance, source IDs and a note. The endpoint does not sum instantaneous meter readings into ungrounded campus totals. Missing factors keep affected aggregates unavailable/partial.

`GET /api/v1/ledger` is read-only and returns the persisted calculation version, input snapshot, assumptions, source reading IDs and verification transition reference for each ledger row.

## Core assumptions that need Account 1 review

1. The local API prefix is `/api/v1`.
2. The database is SQLite/SQLAlchemy; the first schema version is 1.
3. `resource_type` is a string rather than an enum so new resource types can be introduced without a schema migration.
4. Event creation persists a new `OPEN` event. Detection quality/rules are Account 3's responsibility.
5. API readings and events use `metadata` at input and output; the ORM stores it as `metadata_json` because SQLAlchemy reserves its own `metadata` attribute.
6. The action-state map currently uses the lifecycle specified in the build pack.
7. The ledger supports energy, cost, water and CO₂ values, but it does not infer missing units, tariffs or emission factors.
8. No real hardware command is sent by this backend core.

## Validation performed

- Automated tests: `python -m pytest -q`.
- Syntax compilation: `python -m compileall -q app tests`.
- API tests run through FastAPI's test client with isolated SQLite databases.
- Persistence test closes one app/engine and opens a second app against the same file database.

Confirm final results in the live test output after any integration or contract changes. The test suite only validates this local Account 2 implementation; it is not proof that the complete CampusTwin product is release-ready.
