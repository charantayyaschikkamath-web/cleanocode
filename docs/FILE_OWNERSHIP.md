# File Ownership and Agent Boundaries

## 1. Ownership principles

- Each shared path has one primary owner. A reviewer may suggest changes, but must not concurrently edit that path.
- Account 9 owns integration and the central app entrypoint. Feature accounts export modules/routers instead of editing central registration.
- Account 2 owns shared backend schemas and DB foundation; changes are made only through a reviewed contract change.
- Account 5 owns shared frontend transport types/API client, except isolated type definitions owned by feature modules that do not redefine shared entities.
- No agent rewrites another account's assigned files to make their own work easier.
- Dependencies and lock files are integrated sequentially by Account 9; agents propose changes with rationale.

## 2. Module owner matrix

| Account | Primary responsibility | Owned paths (adapt to current repo) | Must not independently modify |
|---|---|---|---|
| 1 | Architecture and contract owner | `docs/PROJECT_BRIEF.md`, `docs/CONTRACTS.md`, `docs/FILE_OWNERSHIP.md`, `docs/FEATURE_MAP.md`, `docs/COMPETITION_BRIEF.md`, `docs/REFERENCES.md`, `docs/THIRD_PARTY_NOTICES.md`, `docs/DECISIONS.md`, initial `docs/KNOWN_LIMITATIONS.md`, initial `docs/ALGORITHMS.md`, `.env.example`, `config.yaml` | Feature implementation; central app; other agents' code |
| 2 | Backend core, persistence, config/clock/errors/facts | `backend/app/core/`, `backend/app/db/`, `backend/app/schemas/shared.py` (or agreed equivalent), `backend/app/services/facts.py`, `backend/app/routers/core.py`, related unit/API tests | `backend/app/main.py`, simulator/action module files, vision module, frontend feature modules |
| 3 | Simulator, detection rules, action state machine, verification orchestration | `backend/app/simulator/`, `backend/app/rules/`, `backend/app/services/actions.py`, `backend/app/services/verification.py`, `backend/app/routers/events.py`, `backend/app/routers/actions.py`, `backend/app/routers/scenarios.py`, related tests | Shared schema definitions without approval; central app; ledger formula implementation owned by A2 |
| 4 | Camera and local vision | `vision/`, `backend/app/vision/`, `backend/app/routers/vision.py`, `frontend/src/features/camera/`, camera docs and tests | Raw-frame persistence, main frontend shell, shared event model, face recognition, central registration |
| 5 | Main frontend shell and shared API transport | `frontend/src/app/`, `frontend/src/api/`, `frontend/src/components/shared/`, `frontend/src/features/overview/`, `events/`, `actions/`, `reports/`, `settings/`, global styles/design tokens, shared API types, frontend integration tests | `frontend/src/features/twin/`, `frontend/src/features/camera/`, copilot/what-if implementation owned by A7, backend code |
| 6 | Digital twin and data visualizations | `frontend/src/features/twin/`, `frontend/src/features/charts/`, isolated tests | Global styles, main app shell, shared API types; proposes additions to A5 rather than editing them |
| 7 | Copilot, what-if reasoning, reports service | `backend/app/copilot/`, `backend/app/what_if/`, report-generation service/router exports, `frontend/src/features/copilot/`, `frontend/src/features/what-if/`, report-specific data logic if agreed with A5 | Shared facts schema, main app shell, ledger calculation engine, central router registration |
| 8 | Quality engineering, preflight integration, evaluator, docs/demo | `scripts/`, `tests/e2e/`, `tests/integration/`, `README.md`, final `docs/ALGORITHMS.md`, release/offline/demo documentation, generated test reports | Feature code except via explicit defect report/assigned fix; cannot weaken tests to produce pass |
| 9 | Integration/release authority/pitch | `backend/app/main.py`, `backend/app/routers/__init__.py` or router registry, root dependency/lock files, release config, integration fixes approved across owners, `presentation/` | Rewriting feature modules wholesale; changing contracts without notifying affected agents |

## 3. Shared-file decision owners

| Shared resource | Primary owner | Approval/change mechanism |
|---|---|---|
| Backend shared schemas/enums | A2 | Contract change request; A9 integration approval |
| Shared API/TypeScript transport types | A5 | Contract change request; A9 approves integration |
| DB schema/migrations | A2 | A2 authors; A9 integrates; never two migration authors at once |
| Formula implementations / source factors | A2 | Contract/spec reviewed; ledger invariants tested |
| Detection/event and action transitions | A3 | Must match `CONTRACTS.md`; all status changes tested |
| Camera-derived evidence payload | A4 proposes, A2/A3 integrate | Shared schema reviewed before route wiring |
| Central FastAPI registration | A9 | Modules expose routers; A9 registers one-by-one |
| Root dependency and lock files | A9 | Agents submit dependency request + license/runtime note |
| Design tokens/global CSS | A5 | A6/A7 request changes via PR/handoff, not direct edits |
| Demo reset | A3 implementation; A9 release sign-off | Isolated demo data only; explicit confirmation and reset test |
| E2E integration tests | A8 | Owners provide test seams and test data setup; defects go to module owner |
| Presentation claims/results | A9 | Every claim traced to research URL, formula, or actual run output |

## 4. Required agent handoff format

Every account must report:

1. Paths created/changed.
2. Behavior implemented.
3. Shared contracts consumed/changed (contract changes must be explicit).
4. Commands run and actual exit statuses/output summaries.
5. Tests added and actual results.
6. Known blockers/limitations.
7. Integration instructions and required environment variables.
8. Demo/test case to reproduce the feature.

No answer that only says “done” or “works perfectly” is acceptable.

## 5. Safe parallel work plan

1. A1 creates/reviews/finalizes the contracts and file map.
2. A2 and A3 coordinate the exact schema/transaction seam, then implement the golden vertical slice sequentially or through isolated paths.
3. Prove Gate B and restart persistence before broadening.
4. A4 builds the isolated optional vision component; A5 builds product shell against frozen contracts; A6 and A7 use dedicated directories.
5. A8 writes acceptance tests using stable fixtures and documented reset; feature owners fix their own defects.
6. A9 merges one branch/workstream at a time and runs tests after each merge.

The table is a proposed layout. If the existing repository differs, Account 9 should preserve its layout while retaining one-owner boundaries.
