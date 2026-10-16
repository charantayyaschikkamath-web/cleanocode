> **Merged-state note (16 October 2026):** the vision router is mounted in the canonical app. The original workstream ownership checklist below is retained as historical context; see [`../MERGE_REPORT.md`](../MERGE_REPORT.md) for current integration status.

---

# Account 4 Workstream Summary

## Owned files

- `backend/app/vision/` — schemas, local inference adapter, service/state safety, router.
- `frontend/src/features/camera/` — isolated React camera panel, styles, API response types.
- `tests/test_vision_*.py` — focused service/route/inference-shape tests.
- `docs/CAMERA_VISION.md`, `docs/INTEGRATION_CONTRACT.md`, `docs/FRONTEND_MANUAL_TESTS.md`, `docs/MODEL_LICENSES.md` — setup and integration guidance.

## Intentionally not owned

- Main FastAPI entry point and router registry (Account 9).
- Shared event/action schema, DB tables, migrations, evidence repository (Accounts 1–2).
- Occupancy dwell/event decisions and verified-savings state machine (Account 3).
- Shared global style system/navigation and central React shell (Account 5).
- Full-repository dependency lockfile, app-level E2E suite, preflight/release flow (Account 8).

## Merge prerequisites

1. Read and align to the main repo's frozen `docs/CONTRACTS.md`; this isolated package did not have access to that file.
2. Replace/inject `EvidenceSink` with Account 2's persistence adapter.
3. Register `build_vision_router()` in Account 9's central app and follow the shared API error envelope.
4. Install this component in Account 5's frontend and provide existing design tokens/API base URL.
5. Configure a specific approved local model and record its SHA/license before claiming real person detection.

## Key decision

Use browser capture + backend local inference rather than cloud vision. The browser only starts after explicit user action; frames are downsized, submitted one at a time, and never accepted by persistence or copilot interfaces. A no-person signal is only a potentially usable sample for Account 3's sustained dwell rule, never a complete empty-room claim.
