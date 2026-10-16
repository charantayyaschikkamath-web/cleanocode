# Feature Map and Acceptance Traceability

**Status vocabulary:** `SPECIFIED` means requirements exist; it does not mean implemented. Accounts must update status only with code/test evidence.

| ID | Feature | Tier/gate | Owner | API/data dependencies | Acceptance test / demo proof | Fallback |
|---|---|---|---|---|---|---|
| F-001 | Backend startup/config/health/preflight | T1 / A | A2, A8, A9 | `/health`, `/health/ready`, `/preflight`; config | Clean documented startup; health reports DB/config correctly; missing optional key/model is WARN | Actionable FAIL/WARN with repair command |
| F-002 | SQLite persistence and schema initialization | T1 / A | A2 | Buildings, rooms, readings, events, actions, transitions, verification, ledger, scenarios | Create records, restart full app, verify same records; no destructive init | Safe schema init/migration and helpful DB error |
| F-003 | Shared sensor reading/provenance model | T1 / A-C | A2 | Sensor reading/source enums | REAL/SIMULATED/DERIVED and freshness survive through API and UI | Unknown/unavailable is explicit, never coerced to normal |
| F-004 | Campus/building/room metadata | T1 / A-D | A2 | `/campus`, `/buildings`, `/rooms` | Click room and see persisted metadata/current known data | Useful no-data view |
| F-005 | Energy waste detection | T1 / B | A3 | Reading/evidence/event schemas; scenario runner | Empty + high simulated power sustained creates rule-backed event with exact threshold, IDs and provenance | Unknown occupancy produces evidence-insufficient event, not empty-room claim |
| F-006 | Human-approved action lifecycle | T1 / B | A3 | Action/action-transition schemas; approval routes | Reject and approve paths; repeated approval creates no duplicate command | API reports conflict or original result |
| F-007 | Independent post-action verification | T1 / B | A3 | Baseline/post readings; verification record | Success based on qualifying post readings; ACK alone is not success | Timeout/unknown state when evidence unavailable |
| F-008 | No false savings on failure | T1 / B | A2 + A3 | Unique ledger constraint; verification state | Dropped and ACK-ignored paths leave ledger count/sum unchanged | Terminal failure with no eligible ledger entry |
| F-009 | Energy impact formula | T1 / B | A2 | Formula/config versions, readings | 1000 W × 600 s = approximately 0.1666667 kWh independent of speed; units included | Missing tariff/CO₂ factor returns null + reason |
| F-010 | Water anomaly | T1 / C | A3 | Flow readings/config, evidence/event | Persistent configured night-flow scenario triggers `likely_water_anomaly` with unit/time window | Missing flow factor/sensor yields unknown, no invented volume savings |
| F-011 | Bin overflow event | T1 / C | A3, A4 if detector | Bin reading/manual/simulated event | Scenario/manual mode creates visibly SIMULATED event; no false claim of CV detection | Detector not installed: manual/simulated only |
| F-012 | Inefficient room use rule | T1 / C | A3 | Occupancy/schedule/power/capacity | Documented rule triggers only when required signals are present | Missing schedule/occupancy gives `evidence_insufficient` |
| F-013 | Missing/stale/unhealthy input handling | T1 / C | A2, A3, A4 | Source health/freshness contracts | Stale, missing, dark, obstructed, no-weights tests never report likely-empty | `UNKNOWN` / `UNAVAILABLE` state and recovery instructions |
| F-014 | Evidence-first event details | T1 / C-D | A5 | Event/evidence/reading endpoints | Show exact rule/threshold/reading/unit/age/health/provenance/unknowns | Empty/missing evidence panel clearly explains unavailable state |
| F-015 | Command center overview | T1 / D | A5 | KPI/events/buildings/ledger/health | Data-driven metrics with time period, unit, origin, empty/error handling | Null values shown as unavailable, never invented zeros |
| F-016 | Interactive 2D digital twin | T1 / D | A6 | Buildings/rooms/latest reading/event contracts | Building and room click drive detail/navigation; keyboard accessible | Stable static SVG schematic with data-driven states; no network tiles |
| F-017 | History charts and verification comparison | T1 / D | A6 | Readings/verification responses | Chart changes with API data; baseline/required/observed drop match verifier | No-data chart summary, not fabricated series |
| F-018 | AI Sustainability Copilot | T1 / D | A7 | Structured facts, `/copilot/query` | Why/prioritize/missing-evidence questions grounded in source IDs; numeric output from backend | `TEMPLATE` without key/internet; timeout and malformed output tested |
| F-019 | What-if and scenario lab | T1 / D | A3, A7, A6 | `/scenarios/run`, `/what-if/run` | Controls alter backend scenario/result and persist output | Clear error; never animation-only simulation |
| F-020 | Transparent impact ledger | T1 / D | A2, A3 | Ledger endpoint, formula and verification IDs | Display inputs/units/period/provenance/formula/status; ledger unchanged on failure | Missing factor shown as unavailable |
| F-021 | Reports and exports | T1 / D | A7, A5 | Report schema, events/actions/ledger | Downloadable valid HTML/CSV/JSON includes sources/limits | Explicit unsupported-format error; no fake PDF button |
| F-022 | Search/filter/feedback/audit timeline | T1 / D | A5, A3 | Filtered events/actions and transition history | Search/filter updates result set; feedback persists; audit is chronological | Clear no-results/error state |
| F-023 | Offline/polling/reconnect behavior | T1 / E | A5, A8, A9 | REST authority, WebSocket envelope | Kill WS/network; core simulator/product remains usable or displays precise offline limit; reconnect refetches state | Polling fallback; no fake “live” badge |
| F-024 | Accessibility/responsive/error states | T1 / D-E | A5, A6, A7 | Design tokens and component contracts | Keyboard, visible focus, labels, color+text state, reduced motion, mobile layout | Usable list/detail layout if visualization constrained |
| F-025 | Demo reset and scenario replay | T1 / D-E | A3, A8, A9 | Scenario run IDs, isolated demo flag | Reset only demo rows after confirmation; replay matches persisted evidence/outcomes | Keep history if isolation cannot be proven; disable reset safely |
| F-026 | Sustainability Pulse | T2 / after D | A2, A5 | Named deterministic inputs/formula | Components and weights visible; tests cover missing inputs | Mark score unavailable/partial |
| F-027 | Transparent action-priority heuristic | T2 / after D | A2, A5 | Severity/evidence/impact/effort factors | UI shows factors/weights and sample calculation | Rank only comparable known data |
| F-028 | Evidence replay and one-click packet | T2 / after D | A3, A7, A8 | Event → action → verification → ledger records | Reconstruct exact timeline, include assumptions and limitations | Export JSON/HTML if shareable view not ready |
| F-029 | Hot-spot ranking | T2 / after D | A2, A5, A6 | Comparable period/unit per building | Sort same measure/period only; incomplete data visibly excluded/flagged | No ranking when inputs incomparable |
| F-030 | What-If Arena | T2 / after D | A7, A6 | Same baseline and configuration snapshot | Compare 2–3 alternatives using identical assumptions; formulas visible | Single-scenario form if comparison is not reliable |
| F-031 | Action plan/weekly report | T2 / after D | A7 | Facts/cached/template copilot and exports | Numeric claims link to deterministic facts; provider mode visible | Template report offline |
| F-032 | Notifications/role presentation/history | T2 / after D | A5, A7 | Events/actions timeline | Read/dismiss/history interactions persist where required | Disable unauthenticated role switching if meaningless |
| F-033 | Local person detector | T3 / conditional | A4 | Local model path, license, health | Real local inference with labeled mode and test clips; no raw-frame persistence | `UNKNOWN` or manual simulated occupancy |
| F-034 | Local bin detector | T3 / conditional | A4/A3 | Licensed dataset/model and evaluator | Reproducible setup, license file, documented synthetic/real evaluation | Explicit simulated/manual event |
| F-035 | 3D campus rendering / advanced forecasts | T3 / conditional | A6/A3 | Existing stable twin and documented model | Only if materially improves interaction and has a tested 2D/offline fallback | Keep 2D twin as primary |
| F-036 | Real hardware integration | T3 / conditional | A2/A3/A9 | Hardware access, protocol, safety approval | End-to-end signal provenance and actuator outcome independently verified | Simulator remains default; no claim of live control |

## Release blockers

Do not call Gate B complete while F-005 through F-009 fail. Do not prioritize T2/T3 work while any release-blocking Tier 1 item has no verified fallback. Status updates require actual implementation/test evidence from the owner.
