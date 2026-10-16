# Project Brief — CampusTwin AI

## 1. Product definition

**CampusTwin AI is an explainable campus sustainability operations system that detects likely resource waste, presents evidence, recommends a response, supports human-approved actions, independently verifies the result, and records only defensible impact.**

It is an operations workflow, not just a chatbot, dashboard, anomaly alarm, or 3D visualization.

## 2. Users and jobs to be done

**Primary user:** campus facilities/building operator responsible for investigating resource issues and coordinating maintenance or operational changes.

**Secondary users:** sustainability officer or campus administrator reviewing trends, evidence, reports, and potential impact.

**Job to be done:** help an operator answer (1) what may be wrong, (2) why the system thinks so, (3) what evidence is missing, (4) what response is safe to approve, and (5) whether the response actually changed the measured or simulated resource signal.

No customer interviews, campus pilots, real deployments, or validated user needs are claimed by this brief. Interviews and local observations can strengthen the problem evidence later.

## 3. User value hypothesis

Disconnected meters, manual inspections, and siloed building tools can make resource anomalies hard to investigate and outcomes hard to verify. CampusTwin proposes to shorten the path from a visible anomaly to a traceable, human-approved and verified response. This is a problem hypothesis to validate for the target campus, not a statement that every campus has the same operating model.

## 4. Differentiation hypothesis

The proposed combination integrates:

1. Multi-resource event normalization.
2. Evidence snapshots and sensor freshness/provenance.
3. Human approval and auditable action states.
4. Independent pre/post verification.
5. A ledger that refuses to count failed/unverified interventions.
6. Deterministic impact calculations with explicit assumptions.
7. AI explanations grounded in structured backend facts.

Existing building-management and energy-management platforms already offer substantial monitoring, automation, analytics, or optimization capabilities. We must not claim the individual building blocks are invented here. The intended value is in the coherent and demonstrable evidence-to-verified-outcome workflow. See `REFERENCES.md`.

## 5. In scope

### Tier 1 — complete and reliable
- Command center with energy/water/waste/cost/CO₂ metrics only when the inputs support them.
- Clickable 2D campus/building/room twin with accessible health/status labels.
- Shared event/evidence model for energy, water, waste-bin, and room-use scenarios.
- Unknown/unavailable/stale input behavior.
- Evidence-first incident detail, filters, false-positive feedback, and audit timeline.
- Human-approved action state machine with command/ack/independent verification.
- SQLite persistence for required entities and idempotent state changes.
- Deterministic scenario lab, including success, dropped command, ignored command, normal conditions, and stale/missing data.
- AI Copilot grounded in backend-generated facts, with offline/template fallback.
- Transparent impact calculations and savings-ledger invariants.
- Search, status/resource filters, report export, health/preflight panel, accessible error/empty/loading states, and resettable demo.

### Tier 2 — only after Tier 1 passes
- Sustainability pulse using an explicit deterministic formula.
- Transparent prioritization heuristic.
- Event replay, hot-spot comparison on comparable data, action plan, evidence packet.
- HTML/CSV/JSON reports, What-If Arena, notification/history views.

### Tier 3 — conditional
- Local person-count detector, only with model/license/setup verified and a reliable unavailable fallback.
- Local bin detector, only with dataset/model license and reproducible evaluation.
- Forecasts and 3D only if they improve the demo and do not weaken the 2D fallback.
- Real hardware integration only if access, safety, protocol, and end-to-end testing are available.

## 6. Non-goals for the hackathon prototype

- No face recognition, identity tracking, biometric matching, or surveillance profiling.
- No unapproved live control of campus equipment.
- No claiming that a simulated meter is a live IoT connection.
- No claiming a formula projection is realized financial or carbon savings.
- No LLM-sourced KPI arithmetic, rankings, confidence values, or evidence records.
- No required cloud connection, CDN fonts, remote map tiles, or startup model download for the core demo.
- No distributed systems stack, multi-agent runtime, blockchain, or Kubernetes unless a specific testable need emerges.

## 7. Release gates

### Gate A — Foundations
The app can start from documented steps; health/preflight works; frontend-to-backend connectivity is defined; SQLite persists data across restart; configuration/error behavior is explicit; secrets are not committed.

### Gate B — Golden vertical slice
One simulated energy scenario can be triggered, inspected, approved, commanded, acknowledged, verified from post-action readings, and added to the ledger. The dropped/ignored command paths do not add savings.

### Gate C — Resource breadth
Water, bin, room-use, normal, and unhealthy/missing-sensor cases use the same domain contracts and have distinct, labelled provenance.

### Gate D — Product completeness
Twin, analytics, copilot, what-if, reports, replay, ranking, settings, responsive behavior, offline fallback, and all advertised interactions are implemented and tested.

### Gate E — Release proof
Preflight, unit/API/frontend/E2E tests, clean install, restart persistence, offline run, failure injection, actual screenshots, and demo rehearsal have documented results. Known failures are visible and cannot masquerade as passes.

A gate is complete only when implementation, error behavior, persistence (where applicable), tests, docs, and a demo/acceptance path all work.

## 8. Trust and safety invariants

1. An alert is a hypothesis supported by readings/rules, not ground truth.
2. Model output is not ground truth.
3. A command being sent is not proof it worked.
4. An acknowledgement is not independent verification.
5. Missing/stale/unhealthy sensors do not mean normal conditions or an empty room.
6. AI prose cannot create numbers, source records, citations, or successful action records.
7. Only `VERIFIED_SUCCESS` can create one verified simulated-savings ledger entry for an action.
8. No raw camera frames/video are written to storage, logs, reports, crash reports, or an LLM request.
9. Values must declare origin/provenance, unit, period, calculation, and unavailability behavior.
10. A simulated impact entry must never be presented as measured real-world savings.

## 9. Architecture at a glance

- **Frontend:** React, Vite, TypeScript, Tailwind; typed API client; feature directories owned by one agent.
- **Backend:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, SQLite, pytest.
- **Core modules:** config/clock/errors, persistence/domain schemas, readings/events, scenario runner, action/verification/ledger services, facts/copilot adapter, report export.
- **Realtime:** WebSocket events with polling/reconnect fallback; ordinary REST routes remain the source of truth.
- **Vision:** optional isolated local person-count service; no face recognition; safe `UNKNOWN`/`UNAVAILABLE` outcomes.
- **Clock:** injectable virtual clock for scenarios and virtual persistence windows; wall clock for physical camera freshness and actual operational timeouts.

## 10. Delivery rule

Do not broaden resource features until Gate B is repeatable. A smaller, flawless audited incident workflow is stronger than a larger feature checklist with broken state transitions.
