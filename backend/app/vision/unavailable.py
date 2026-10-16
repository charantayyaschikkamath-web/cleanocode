"""Safe camera adapter used when native inference dependencies are unavailable."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

from .schemas import (
    EvidenceStatus, OccupancyCurrentResponse, OccupancyEvidence, OccupancySignal,
    PersistenceStatus, Provenance, SimulatedOccupancyRequest, VisionHealth,
)


class _Settings:
    max_frame_bytes = int(os.getenv("VISION_MAX_FRAME_BYTES", "2000000"))
    max_frame_age_ms = int(os.getenv("VISION_MAX_FRAME_AGE_MS", "4000"))
    smoothing_window = 5


class UnavailableCameraVisionService:
    """Keep camera endpoints explicit and fail closed without OpenCV/NumPy/ONNX."""

    def __init__(self) -> None:
        self.settings = _Settings()
        self._latest: dict[str, tuple[OccupancyEvidence, float]] = {}

    def health(self) -> VisionHealth:
        return VisionHealth(
            status=EvidenceStatus.UNAVAILABLE,
            detector_available=False,
            model_configured=bool(os.getenv("VISION_MODEL_PATH", "").strip()),
            model_license_reviewed=os.getenv("VISION_MODEL_LICENSE_REVIEWED", "false").lower() == "true",
            persistence_sink_configured=False,
            max_frame_bytes=self.settings.max_frame_bytes,
            max_frame_age_ms=self.settings.max_frame_age_ms,
            smoothing_window=self.settings.smoothing_window,
            message="Person detection is unavailable because the installed OpenCV/NumPy stack is incompatible. Camera preview can still run in the browser; no occupancy inference is performed.",
        )

    def _evidence(self, room_id: str, *, provenance: Provenance, signal: OccupancySignal,
                  status: EvidenceStatus, reason: str, explanation: str,
                  person_count: int | None = None, coverage_confirmed: bool = False,
                  camera_label: str | None = None) -> OccupancyEvidence:
        now = datetime.now(timezone.utc)
        record = OccupancyEvidence(
            evidence_id=str(uuid.uuid4()), room_id=room_id, status=status, signal=signal,
            provenance=provenance, raw_person_count=person_count,
            smoothed_person_count=person_count, observed_at=now, received_at=now,
            camera_label=camera_label, coverage_confirmed=coverage_confirmed,
            eligible_for_empty_timer=False, reason_code=reason, explanation=explanation,
            persistence_status=PersistenceStatus.NOT_CONFIGURED,
        )
        self._latest[room_id] = (record, time.monotonic())
        return record

    def analyze_jpeg(self, room_id: str, frame_bytes: bytes, *, coverage_confirmed: bool = False,
                     camera_label: str | None = None, captured_at=None) -> OccupancyEvidence:
        return self._evidence(
            room_id, provenance=Provenance.REAL, signal=OccupancySignal.UNKNOWN,
            status=EvidenceStatus.UNAVAILABLE, reason="INFERENCE_UNAVAILABLE",
            explanation="Camera frame received, but person detection is unavailable; occupancy remains unknown.",
            coverage_confirmed=coverage_confirmed, camera_label=camera_label,
        )

    def record_simulated(self, request: SimulatedOccupancyRequest) -> OccupancyEvidence:
        signal = OccupancySignal.PERSON_DETECTED if request.person_count else OccupancySignal.NO_PERSON_DETECTED
        return self._evidence(
            request.room_id, provenance=Provenance.SIMULATED, signal=signal,
            status=EvidenceStatus.AVAILABLE, reason="SIMULATED_INPUT",
            explanation="Explicit demo input; this is simulated occupancy and never qualifies for an empty-room timer.",
            person_count=request.person_count, coverage_confirmed=request.coverage_confirmed,
            camera_label=request.camera_label,
        )

    def current(self, room_id: str):
        item = self._latest.get(room_id)
        if item is None:
            return None, None, "No occupancy evidence has been received for this room."
        evidence, recorded = item
        age_ms = max(0, int((time.monotonic() - recorded) * 1000))
        return evidence.model_copy(update={"frame_age_ms": age_ms}), age_ms, evidence.explanation
