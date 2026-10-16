# Account 1 Handoff Packet for Accounts 2–9

## Global rules (must be appended to each agent prompt)

> Inspect the existing repository before editing. Read `docs/COMPETITION_BRIEF.md`, `docs/PROJECT_BRIEF.md`, `docs/CONTRACTS.md`, `docs/FILE_OWNERSHIP.md`, `docs/FEATURE_MAP.md`, and `docs/KNOWN_LIMITATIONS.md`. Keep changes within assigned paths. Do not silently change shared schemas, endpoint paths, status enums, timestamps, clock semantics, provenance, formulas, or ledger eligibility. If a change is needed, propose the exact diff, affected consumers, migration, and tests. Preserve working features. Add tests for normal and error paths. Run relevant commands and report actual output/exit status. Never fake test results, detections, metrics, citations, savings, deployment or provider status. A visible control must work or be disabled with a reason. Distinguish REAL, SIMULATED, DERIVED, PROJECTED, VERIFIED_SIMULATED and MEASURED values precisely.

## Account 2 — Backend Core / Persistence / Impact Engine

**Own:** `backend/app/core/`, `backend/app/db/`, shared backend schemas, core routes, deterministic facts/KPI assembly and impact calculation services, associated tests.

**Implement:** FastAPI health/readiness/preflight; safe SQLite/SQLAlchemy initialization/migration; configuration and injectable clock; structured errors/request IDs and redacted logs; buildings/rooms/sensor configs/readings/events/feedback/actions/transitions/verification/ledger/scenarios/reports persistence; facts/KPI assembly; unit-aware deterministic energy/cost/CO₂ calculations; unique ledger constraints and transactions.

**Consume:** the exact models and route payloads in `CONTRACTS.md`. Do not change central `main.py` or own Account 3's action state machine.

**Acceptance:** persistence survives app restart; missing factors stay null/unavailable; 1000 W for 600 virtual seconds yields about 0.1666667 kWh regardless of multiplier; invalid units/timestamps are rejected; failed/unverified actions cannot be added to eligible savings ledger.

## Account 3 — Simulator / Rules / Action Verification

**Own:** simulator/rules/action/verification services and corresponding router modules/tests.

**Implement:** repeatable scenarios, shared event schema, rule evidence snapshots, false-positive feedback, state machine, baseline capture, ACK/drop/ignored-command simulation, verification samples, idempotency, scenario reset restricted to demo data.

**Consume:** shared schemas and DB services from Account 2. Do not implement a competing ledger formula or edit central app registration.

**Acceptance:** test every allowed/forbidden transition; duplicate approval dispatches once; ACK-ignore ends verification failed and creates no ledger entry; dropped command times out/fails without savings; success creates exactly one entry and full audit trail.

## Account 4 — Camera / Local Vision

**Own:** `vision/`, `backend/app/vision/`, vision router export, `frontend/src/features/camera/`, camera tests/docs.

**Implement:** consent-driven source selection/start/stop/health; local person-class count only if dependencies/weights/license are available; derived occupancy state, smoothing, freshness; safe unknown/unavailable behavior. Frames remain memory-only and never go to database/logs/reports/LLM.

**Acceptance:** permission denied, stale/dark/obstructed frame, missing weights, inference error all produce UNKNOWN/UNAVAILABLE rather than empty; optional feature does not block simulated demo.

## Account 5 — Main Frontend / Shell / API client

**Own:** `frontend/src/app/`, `frontend/src/api/`, shared transport types, shared components/design tokens, overview/events/actions/reports/settings views and tests.

**Implement:** navigable product UI, KPI/event/action surfaces, search/filters, health/preflight, provenance and source-age labels, loading/empty/error/retry/offline/reconnect states, confirmations/toasts and accessible interactions. Wire every primary control to real API behavior.

**Consume:** Account 6 twin and Account 7 copilot/what-if components. Do not overwrite those directories or backend schemas.

**Acceptance:** user can complete golden slice via UI; no decorative primary button; API failure is shown honestly; no green success before persisted status; keyboard/focus/responsive behavior works.

## Account 6 — Digital Twin / Charts

**Own:** `frontend/src/features/twin/`, `frontend/src/features/charts/`, tests.

**Implement:** data-driven 2D SVG campus/building/room drill-down, chart history, before/after verification view, accessible labels and missing-data state. 3D is conditional only after 2D fallback passes.

**Acceptance:** building/room selection changes the actual detail state; chart values and units match API responses; incomplete data are visible; no online tile/font dependency.

## Account 7 — Copilot / What-if / Reports

**Own:** `backend/app/copilot/`, `backend/app/what_if/`, report service/router export as agreed, `frontend/src/features/copilot/`, `frontend/src/features/what-if/`, assigned tests.

**Implement:** provider adapter; fact-grounded schema; timeout/retry; `LLM/CACHED/TEMPLATE` mode; deterministic what-if calculations and comparable alternatives; report exports HTML/CSV/JSON; weekly action plan with numeric data from backend only.

**Acceptance:** no key/network works via TEMPLATE; timeout/malformed/provider failure does not block core workflow; no unsupported facts/numbers/citations; exports include provenance, assumptions, source IDs and limitations.

## Account 8 — Quality / Preflight / Demo / Offline

**Own:** `scripts/`, `tests/integration/`, `tests/e2e/`, README, release docs, actual-code update to `docs/ALGORITHMS.md`, evaluation and test result artifacts.

**Implement:** actionable PASS/WARN/FAIL preflight, repeatable scenario evaluator, test suite, clean-install/offline/persistence/failure-injection instructions, demo script and fallback. Update this package's algorithm spec only after comparing with actual code.

**Acceptance:** evaluator gives per-scenario expected/actual state, result, error/unknown behavior, action result and ledger before/after. Use exact outputs; label synthetic outcomes as synthetic.

## Account 9 — Integration / Release / Pitch

**Own:** central app and router registration, root dependencies/lock files, release config, approved integration fixes, `presentation/`.

**Implement:** merge/integrate one workstream at a time; reconcile schemas/types/routes; run test/build/preflight/restart/offline/failure tests; verify all primary buttons; prepare deck/script/Q&A from actual release app and verified sources.

**Acceptance:** success plus failure demo pass; ledger increments only after verification; camera unknown never implies empty; real screenshots from final app; every claim traced to a source/formula/test; unresolved limitations disclosed.

## Recommended dependency order

`A1 contract review → A2 persistence/core + A3 simulator/action seam → Gate B prove → A5 shell / A4 vision / A6 twin / A7 copilot in bounded modules → A8 test/preflight → A9 integration and release.`
