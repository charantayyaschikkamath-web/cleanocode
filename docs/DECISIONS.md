# Architecture Decision Records

**Status:** initial decisions for review. Dates use 2026-10-15. These are project choices, not proof of implementation.

## ADR-001 — Local-first hackathon architecture

- **Context:** live demo must remain useful without Wi-Fi, provider key, camera hardware, or optional model weights.
- **Decision:** FastAPI + SQLite/SQLAlchemy backend; React/Vite/TypeScript/Tailwind frontend; local simulator first; provider/vision adapters optional.
- **Alternatives:** cloud-only backend, remote hosted database, mandatory paid AI API.
- **Rationale:** reproducible local demo, lower setup risk, simple persistence, optional capabilities degrade independently.
- **Consequences:** the initial DB is single-node and not a production multi-campus control platform. Real hardware integration requires future adapter/security review.
- **Status:** proposed; reconcile with existing repo before implementation.

## ADR-002 — One shared multi-resource event model

- **Context:** separate energy/water/waste event models would fragment UI and reports.
- **Decision:** use one `Event` schema with enumerated event types and immutable evidence references.
- **Alternatives:** distinct event table/API per resource.
- **Rationale:** consistent triage, audit, and cross-resource UI without losing resource-specific evidence.
- **Consequences:** type-specific evidence remains structured by rule/source and must be validated carefully.
- **Status:** proposed; contract freeze required.

## ADR-003 — Explicit provenance and availability separate from health

- **Context:** simulated, derived, and real data have different meaning; stale data can still exist.
- **Decision:** every reading includes `provenance`; every reading/source includes a separate health/freshness state; KPI availability is explicit.
- **Alternatives:** a single `is_live` boolean or null-as-zero.
- **Rationale:** avoids presenting missing or simulated values as measured live data.
- **Consequences:** UI and exports carry additional labels and reasons.
- **Status:** proposed.

## ADR-004 — Acknowledgement is not verification

- **Context:** action command success can diverge from actual resource outcome.
- **Decision:** model command/acknowledgement and post-action verification as separate stages. Acknowledged-but-ignored is a required scenario.
- **Alternatives:** mark an action done on ACK.
- **Rationale:** proves the central trust property to judges and prevents inflated savings.
- **Consequences:** simulator and virtual clock require deterministic failure-injection tests.
- **Status:** proposed; release-blocking invariant.

## ADR-005 — Only verified outcomes create eligible savings entries

- **Context:** projected benefits can be confused with realized savings.
- **Decision:** projections appear in reports/what-if but not as verified savings ledger entries. `VERIFIED_SIMULATED` requires `VERIFIED_SUCCESS`; it is still labelled simulated.
- **Alternatives:** add estimated savings when recommending an action or dispatching a command.
- **Rationale:** ledger remains defensible and auditable.
- **Consequences:** failed demos show no positive ledger change; UI must explain why.
- **Status:** proposed; unique DB constraint and integration test required.

## ADR-006 — One injectable virtual clock for scenarios

- **Context:** tests and demo require accelerated repeatable time without long sleeps.
- **Decision:** scenario persistence/verification uses an injectable virtual clock; camera freshness, external-source reachability and real operational timeout use wall clock.
- **Alternatives:** speed up all timestamps uniformly or use real sleeps.
- **Rationale:** deterministic tests without falsely refreshing camera evidence or coupling savings to demo speed.
- **Consequences:** fields/time-domain comparisons must be explicit.
- **Status:** proposed.

## ADR-007 — REST is source of truth; WebSocket is advisory

- **Context:** realtime channels may disconnect or duplicate messages.
- **Decision:** notifications carry versioned entity IDs; clients refetch records through REST; polling/reconnect fallback exists.
- **Alternatives:** treat pushed payload as the only state source.
- **Rationale:** reconnect correctness and offline resilience are easier to validate.
- **Consequences:** duplicate message IDs and stale connection status need tests.
- **Status:** proposed.

## ADR-008 — Backend owns calculations and structured facts

- **Context:** LLM output is not a trustworthy numeric calculation engine.
- **Decision:** backend computes metrics/rankings/scenario outcomes; copilot receives a structured fact object and returns validated explanatory text.
- **Alternatives:** ask LLM to generate KPIs and savings estimates directly.
- **Rationale:** traceability, deterministic tests and no-key fallback.
- **Consequences:** template answers need to remain useful and fact-grounded.
- **Status:** proposed.

## ADR-009 — Optional local vision is isolated and privacy-preserving

- **Context:** runtime hardware/model/licensing can be unpredictable.
- **Decision:** vision is optional, person-class/count only, with explicit permission/status; frames stay in memory and are never stored/sent to LLM; missing/stale/dark/obstructed sources report unknown/unavailable.
- **Alternatives:** save video clips, rely on cloud vision, treat no detection as empty.
- **Rationale:** privacy and safe degradation.
- **Consequences:** optional capability may not run on every demo machine; simulated/manual mode remains available.
- **Status:** proposed; model license and setup must be verified.

## ADR-010 — 2D local twin before 3D

- **Context:** 3D can add dependency/performance risk without proving the workflow.
- **Decision:** interactive SVG/2D campus schematic is the required baseline; 3D is conditional after full 2D interaction and fallback work.
- **Alternatives:** lead with a 3D scene.
- **Rationale:** reliable click-through, low offline risk, clearer drill-down.
- **Consequences:** diagram data and states must still be linked to actual API data.
- **Status:** proposed.

## ADR-011 — Version rule/formula/config snapshots

- **Context:** thresholds/factors may change between test runs.
- **Decision:** every evidence snapshot and ledger calculation records rule/formula/config versions and effective inputs.
- **Alternatives:** recompute historical results from latest config.
- **Rationale:** historical records retain their original meaning.
- **Consequences:** config-version schema and export metadata required.
- **Status:** proposed.

## ADR-012 — Unknown competition rubric does not block product foundation

- **Context:** event name and judging rubric were not available.
- **Decision:** document the gap, use a clearly labelled provisional internal model, and build a demonstrable product; update pitch priorities when the official rubric is supplied.
- **Alternatives:** invent a rubric or block all work.
- **Rationale:** avoid false facts while proceeding productively.
- **Consequences:** no competition-specific optimization claim until official details are verified.
- **Status:** active until event details arrive.
