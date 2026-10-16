> **Implementation status:** the originally proposed ownership boundaries remain useful for maintenance, but the account workstreams have now been registered by the integration merge. See [`MERGE_REPORT.md`](MERGE_REPORT.md) for the current application layout and remaining release gate.

---

# Architecture Overview

## Component and data-flow overview

```mermaid
flowchart TD
  UI[React + Vite + TypeScript UI] --> API[FastAPI /api/v1]
  UI -. status updates .-> WS[WebSocket notifications]
  WS --> API
  API --> CORE[Core: config, clock, validation, errors]
  API --> READ[Readings and source-health services]
  API --> DET[Scenario runner and deterministic rules]
  DET --> EVT[Shared event and evidence model]
  EVT --> DB[(SQLite / SQLAlchemy)]
  API --> ACT[Action state machine]
  ACT --> SIM[Command simulator]
  ACT --> VER[Independent verification service]
  VER --> DB
  VER --> LEDGER[Impact calculation / ledger service]
  LEDGER --> DB
  API --> FACTS[Deterministic KPI and Copilot facts]
  FACTS --> COP[Provider adapter or TEMPLATE fallback]
  COP --> API
  API --> RPT[Report and What-If services]
  VISION[Optional local vision service] -->|derived counts/status only| READ
```

## Module dependency constraints

- `core` and shared schemas must not import UI concerns.
- Event/rule services depend on the shared reading/evidence schemas; they must not create resource-specific parallel event systems.
- Actions call a simulator/adapter and verification service; they do not calculate savings directly in UI code.
- The verifier creates a durable result; the ledger service consumes only eligible verification results.
- Copilot consumes a structured, server-created facts object and cannot write evidence, actions, KPIs or ledger entries.
- Reports read persisted facts and preserve provenance/assumptions.
- The optional vision service sends derived counts/status to the core domain. Raw frames never reach database, logs, reports or LLM.
- Feature routers export `APIRouter` objects under their assigned prefixes. Account 9 registers them in the central application.
- SQLite is the initial source of truth. WebSocket notifications can prompt refetch but never substitute for persisted REST state.

## Recommended repository layout (adapt to the existing repository)

```text
.
├── backend/
│   └── app/
│       ├── main.py                 # Account 9 only
│       ├── core/                   # A2
│       ├── db/                     # A2
│       ├── schemas/                # shared schemas: A2; frozen contract
│       ├── services/               # core/facts: A2; actions/verify: A3
│       ├── simulator/              # A3
│       ├── rules/                  # A3
│       ├── vision/                 # A4
│       ├── copilot/                # A7
│       ├── what_if/                # A7
│       └── routers/                # module owner exports; A9 registration
├── frontend/
│   └── src/
│       ├── app/                    # A5
│       ├── api/                    # A5
│       ├── components/shared/      # A5
│       └── features/
│           ├── camera/             # A4
│           ├── twin/               # A6
│           ├── charts/             # A6
│           ├── copilot/             # A7
│           └── what-if/            # A7
├── vision/                          # A4 local model instructions/artifacts policy
├── docs/                            # A1 architecture; A8 release docs/algorithm updates
├── contracts/examples/              # canonical examples
├── scripts/                          # A8; release integration from A9
└── tests/                            # A2/A3 unit tests; A8 integration/E2E
```

## Sequence diagram: approved intervention

```mermaid
sequenceDiagram
  participant O as Operator UI
  participant A as Action Service
  participant D as Database
  participant S as Simulator/Adapter
  participant V as Verifier
  participant L as Ledger Service
  O->>A: Approve action + idempotency key
  A->>D: Transaction: status + transition + baseline refs
  A->>S: Dispatch simulated command
  S-->>A: ACK or dropped/dispatch failure
  A->>D: Append ACK/FAIL/TIMEOUT transition
  A->>V: Begin independent post-command observation
  V->>D: Read healthy post-action samples
  V->>D: Persist verification outcome + transition
  alt VERIFIED_SUCCESS
    V->>L: Eligible verification ID
    L->>D: Insert unique immutable ledger record
  else failed/timeout/unknown
    V-->>A: No verified savings eligibility
  end
  A-->>O: Return persisted current state and evidence
```

## Important architectural boundary

The state machine is not a front-end animation. The current action state and append-only transition record are written by backend services. A UI can show progress only after receiving a persisted response or refetching authoritative state.
