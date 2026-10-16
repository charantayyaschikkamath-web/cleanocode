> **Merged-state note (16 October 2026):** `backend/app/main.py` now mounts the vision router at `/api/vision`. This document remains the module contract/privacy reference; its instruction to mount the router is historical. Model weights are still not bundled, and health status must remain unavailable until a reviewed model is configured.

---

# Account 4 Integration Contract

## Router registration

Account 9 owns the central FastAPI entry point and should register the injected router:

```python
from backend.app.vision import CameraVisionService, build_vision_router
from backend.app.vision.inference import detector_from_environment

vision_service = CameraVisionService(
    detector_from_environment(),
    settings=vision_settings,
    evidence_sink=account2_evidence_adapter,
)
app.include_router(build_vision_router(vision_service))
```

Do not create a second competing FastAPI app in the production repository. `backend/vision_standalone.py` is only a local inspection/test harness.

## API

- `GET /api/vision/health` — returns detector availability, model configuration/licence review flags, persistence sink status and safe-mode configuration.
- `POST /api/vision/frame?room_id=...&coverage_confirmed=...&camera_label=...` — body is one JPEG (`image/jpeg`), max bytes configured by service; returns derived evidence metadata only.
- `POST /api/vision/simulated` — accepts `{ room_id, person_count, coverage_confirmed, camera_label? }`; always `SIMULATED`, never eligible for real empty-room evidence.
- `GET /api/vision/occupancy/current?room_id=...` — returns most recent metadata; real evidence becomes `UNKNOWN` after max age.

## Evidence invariants

- `PERSON_DETECTED` is emitted when the raw current count is above zero **or** the rolling median remains above zero. The raw-positive signal is immediate and must reset Account 3's likely-empty timer immediately.
- `NO_PERSON_DETECTED` means only that the valid inference window did not detect a person. It never means “room is empty” by itself.
- `eligible_for_empty_timer` is true only for a valid `REAL` detector result with operator-confirmed coverage and `NO_PERSON_DETECTED`. Account 3 must still enforce dwell/persistence requirements against the shared virtual clock.
- Any `UNKNOWN`, `UNAVAILABLE`, stale, simulated, invalid, dark/flat, unsupported-output or inference-error result resets/blocks the empty-room timer; none may be coerced to zero occupants.
- Commands/acknowledgements/savings are outside this module. Camera evidence cannot mark an action verified.

## Persistence adapter

`EvidenceSink.record_occupancy_evidence(OccupancyEvidence)` is deliberately narrow. It receives no frame buffer, tensor, path or image. Production adapter should map `evidence_id`, room, status, signal, provenance, counts, `observed_at`, camera label, coverage attestation, reason code, detector/version, and the evidence explanation into Account 2's frozen schema. Follow the shared contract's retention policy and avoid persisting every 1 Hz frame unnecessarily; service coalesces equal metadata snapshots to a configured interval while persisting changes sooner.

The module reports `NOT_CONFIGURED`, `NOT_DUE`, `RECORDED`, or `FAILED` truthfully. It never represents a failed/unwired persistence sink as successful. API responses with `persistence_status=NOT_DUE` have not themselves been written as a new row; an event/audit record must therefore persist an immutable evidence snapshot or reference the actual persisted sample, never assume every frame response ID exists in storage.

## Error handling

The route rejects non-JPEG content types (`415`) and oversized frames (`413`). Invalid image bytes return `UNKNOWN`; missing model returns `UNAVAILABLE`; no route logs or returns raw frame bytes. The module does not implement campus user authentication itself: Account 9 must keep these routes behind the same authenticated/operator authorization and configured CORS boundary as the rest of the API, and should not expose the standalone service beyond loopback. Account 2/9 should maintain the shared error response envelope during integration without exposing request payloads.
