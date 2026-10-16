from __future__ import annotations

import logging
import math
import os
import statistics
import time
import uuid
import warnings
from collections import deque
from io import BytesIO
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from .inference import InferenceUnavailable, PersonDetector, detector_from_environment
from .schemas import (
    EvidenceStatus,
    OccupancyEvidence,
    OccupancySignal,
    PersistenceStatus,
    Provenance,
    SimulatedOccupancyRequest,
    VisionHealth,
)

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class VisionSettings:
    max_frame_bytes: int = 2_000_000
    max_frame_width: int = 1920
    max_frame_height: int = 1080
    max_frame_age_ms: int = 4_000
    smoothing_window: int = 5
    min_mean_luminance: float = 8.0
    min_luminance_stddev: float = 1.5
    evidence_persist_interval_seconds: float = 5.0
    model_configured: bool = False
    model_license_reviewed: bool = False

    def __post_init__(self) -> None:
        if self.max_frame_bytes < 1 or self.max_frame_width < 1 or self.max_frame_height < 1:
            raise ValueError("Frame byte and dimension limits must be positive.")
        if self.max_frame_age_ms < 1:
            raise ValueError("max_frame_age_ms must be positive.")
        if not 1 <= self.smoothing_window <= 15:
            raise ValueError("smoothing_window must be between 1 and 15.")
        if self.min_mean_luminance < 0 or self.min_luminance_stddev < 0:
            raise ValueError("Frame quality thresholds cannot be negative.")
        if self.evidence_persist_interval_seconds < 0:
            raise ValueError("evidence_persist_interval_seconds cannot be negative.")


def vision_settings_from_environment() -> VisionSettings:
    """Read safe camera-service limits. Shared config loaders may instead build VisionSettings directly."""
    model_path = os.getenv("VISION_MODEL_PATH", "").strip()
    reviewed = os.getenv("VISION_MODEL_LICENSE_REVIEWED", "false").lower() == "true"
    return VisionSettings(
        max_frame_bytes=int(os.getenv("VISION_MAX_FRAME_BYTES", "2000000")),
        max_frame_width=int(os.getenv("VISION_MAX_FRAME_WIDTH", "1920")),
        max_frame_height=int(os.getenv("VISION_MAX_FRAME_HEIGHT", "1080")),
        max_frame_age_ms=int(os.getenv("VISION_MAX_FRAME_AGE_MS", "4000")),
        smoothing_window=int(os.getenv("VISION_SMOOTHING_WINDOW", "5")),
        min_mean_luminance=float(os.getenv("VISION_MIN_MEAN_LUMINANCE", "8")),
        min_luminance_stddev=float(os.getenv("VISION_MIN_LUMINANCE_STDDEV", "1.5")),
        evidence_persist_interval_seconds=float(os.getenv("VISION_EVIDENCE_PERSIST_INTERVAL_SECONDS", "5")),
        model_configured=bool(model_path),
        model_license_reviewed=reviewed,
    )


class EvidenceSink(Protocol):
    """Adapter to Account 2's persistence service; must persist metadata only, never frames."""

    def record_occupancy_evidence(self, evidence: OccupancyEvidence) -> None: ...


class InMemoryEvidenceSink:
    """Optional local-development sink. Do not use as production persistence."""

    def __init__(self) -> None:
        self.records: list[OccupancyEvidence] = []
        self._lock = RLock()

    def record_occupancy_evidence(self, evidence: OccupancyEvidence) -> None:
        # Schema contains only counts and metadata; raw frame bytes are not accepted here.
        with self._lock:
            self.records.append(evidence.model_copy(deep=True))


@dataclass
class _RoomState:
    recent_counts: deque[int] = field(default_factory=deque)
    latest: OccupancyEvidence | None = None
    latest_monotonic: float | None = None
    last_persisted_monotonic: float = 0.0
    last_persisted_signature: tuple | None = None


class CameraVisionService:
    def __init__(
        self,
        detector: PersonDetector | None = None,
        *,
        settings: VisionSettings | None = None,
        evidence_sink: EvidenceSink | None = None,
    ) -> None:
        self.detector = detector or detector_from_environment()
        self.settings = settings or vision_settings_from_environment()
        self.evidence_sink = evidence_sink
        self._rooms: dict[str, _RoomState] = {}
        self._lock = RLock()

    def health(self) -> VisionHealth:
        available = bool(self.detector.available)
        status = EvidenceStatus.AVAILABLE if available else EvidenceStatus.UNAVAILABLE
        detector_reason = getattr(self.detector, "unavailable_reason", "")
        message = "Local person detector is ready." if available else (
            f"Local inference is unavailable ({detector_reason or 'MODEL_NOT_CONFIGURED'}). "
            "Camera frames will not be treated as occupancy evidence."
        )
        return VisionHealth(
            status=status,
            detector_available=available,
            detector_name=self.detector.name if available else None,
            model_configured=self.settings.model_configured,
            model_license_reviewed=self.settings.model_license_reviewed,
            persistence_sink_configured=self.evidence_sink is not None,
            max_frame_bytes=self.settings.max_frame_bytes,
            max_frame_age_ms=self.settings.max_frame_age_ms,
            detector_confidence_threshold=getattr(self.detector, "confidence_threshold", None),
            detector_nms_threshold=getattr(self.detector, "nms_threshold", None),
            smoothing_window=self.settings.smoothing_window,
            message=message,
        )

    def _room(self, room_id: str) -> _RoomState:
        if room_id not in self._rooms:
            self._rooms[room_id] = _RoomState(
                recent_counts=deque(maxlen=self.settings.smoothing_window)
            )
        return self._rooms[room_id]

    def _metadata_evidence(
        self,
        *,
        room_id: str,
        status: EvidenceStatus,
        signal: OccupancySignal,
        provenance: Provenance,
        coverage_confirmed: bool,
        reason_code: str | None,
        explanation: str,
        raw_count: int | None = None,
        smoothed_count: int | None = None,
        observed_at: datetime | None = None,
        frame_age_ms: int | None = None,
        mean_luminance: float | None = None,
        luminance_stddev: float | None = None,
        camera_label: str | None = None,
        eligible_for_empty_timer: bool = False,
    ) -> OccupancyEvidence:
        return OccupancyEvidence(
            evidence_id=str(uuid.uuid4()),
            room_id=room_id,
            status=status,
            signal=signal,
            provenance=provenance,
            raw_person_count=raw_count,
            smoothed_person_count=smoothed_count,
            observed_at=observed_at or utc_now(),
            received_at=utc_now(),
            frame_age_ms=frame_age_ms,
            camera_label=camera_label,
            coverage_confirmed=coverage_confirmed,
            eligible_for_empty_timer=eligible_for_empty_timer,
            reason_code=reason_code,
            explanation=explanation,
            frame_mean_luminance=mean_luminance,
            frame_luminance_stddev=luminance_stddev,
            detector_name=self.detector.name if self.detector.available else None,
            detector_confidence_threshold=getattr(self.detector, "confidence_threshold", None),
            smoothing_window=self.settings.smoothing_window,
        )

    def _commit(self, evidence: OccupancyEvidence, *, persist_now: bool = False) -> OccupancyEvidence:
        with self._lock:
            state = self._room(evidence.room_id)
            signature = (
                evidence.status,
                evidence.signal,
                evidence.provenance,
                evidence.raw_person_count,
                evidence.smoothed_person_count,
                evidence.reason_code,
            )
            should_persist = persist_now or signature != state.last_persisted_signature or (
                time.monotonic() - state.last_persisted_monotonic
                >= self.settings.evidence_persist_interval_seconds
            )
            if self.evidence_sink is None:
                stored = evidence.model_copy(update={"persistence_status": PersistenceStatus.NOT_CONFIGURED})
            elif not should_persist:
                stored = evidence.model_copy(update={"persistence_status": PersistenceStatus.NOT_DUE})
            else:
                try:
                    # Pass only Pydantic metadata. Frame bytes never enter the sink interface.
                    to_record = evidence.model_copy(update={"persistence_status": PersistenceStatus.RECORDED})
                    self.evidence_sink.record_occupancy_evidence(to_record)
                    stored = to_record
                    state.last_persisted_monotonic = time.monotonic()
                    state.last_persisted_signature = signature
                except Exception as exc:
                    # Avoid logging any request body or image data.
                    logger.warning("Occupancy evidence metadata persistence failed (%s)", type(exc).__name__)
                    stored = evidence.model_copy(update={"persistence_status": PersistenceStatus.FAILED})
            state.latest = stored
            state.latest_monotonic = time.monotonic()
            return stored

    def analyze_jpeg(
        self,
        room_id: str,
        frame_bytes: bytes,
        *,
        coverage_confirmed: bool = False,
        camera_label: str | None = None,
        captured_at: datetime | None = None,
    ) -> OccupancyEvidence:
        """Decode, quality-check and infer without writing the frame to disk or logs."""
        now = utc_now()
        if not room_id.strip():
            raise ValueError("room_id is required")
        if not frame_bytes:
            return self._commit(self._metadata_evidence(
                room_id=room_id, status=EvidenceStatus.UNKNOWN, signal=OccupancySignal.UNKNOWN,
                provenance=Provenance.REAL, coverage_confirmed=coverage_confirmed,
                reason_code="EMPTY_FRAME", explanation="No frame bytes were received."
            ))
        if len(frame_bytes) > self.settings.max_frame_bytes:
            return self._commit(self._metadata_evidence(
                room_id=room_id, status=EvidenceStatus.UNKNOWN, signal=OccupancySignal.UNKNOWN,
                provenance=Provenance.REAL, coverage_confirmed=coverage_confirmed,
                reason_code="FRAME_TOO_LARGE", explanation="The frame exceeded the configured size limit."
            ))
        if not self.detector.available:
            reason = getattr(self.detector, "unavailable_reason", "MODEL_NOT_CONFIGURED")
            return self._commit(self._metadata_evidence(
                room_id=room_id, status=EvidenceStatus.UNAVAILABLE, signal=OccupancySignal.UNKNOWN,
                provenance=Provenance.REAL, coverage_confirmed=coverage_confirmed,
                reason_code=reason or "INFERENCE_UNAVAILABLE",
                explanation="Local person detection is unavailable; occupancy remains unknown.",
                camera_label=camera_label,
            ))

        try:
            # Inspect image dimensions from the header before full decode to reduce decompression-bomb risk.
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(BytesIO(frame_bytes)) as image_header:
                        if image_header.format != "JPEG":
                            raise ValueError("INVALID_IMAGE")
                        header_width, header_height = image_header.size
                        if header_width > self.settings.max_frame_width or header_height > self.settings.max_frame_height:
                            raise ValueError("FRAME_DIMENSIONS_EXCEEDED")
                        image_header.verify()
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                raise ValueError("INVALID_IMAGE") from exc
            raw = np.frombuffer(frame_bytes, dtype=np.uint8)
            frame = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError("INVALID_IMAGE")
            height, width = frame.shape[:2]
            if width > self.settings.max_frame_width or height > self.settings.max_frame_height:
                raise ValueError("FRAME_DIMENSIONS_EXCEEDED")
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_luma = float(np.mean(gray))
            std_luma = float(np.std(gray))
            if mean_luma < self.settings.min_mean_luminance or std_luma < self.settings.min_luminance_stddev:
                reason = "DARK_OR_UNUSABLE_FRAME" if mean_luma < self.settings.min_mean_luminance else "LOW_VISUAL_VARIATION"
                evidence = self._metadata_evidence(
                    room_id=room_id, status=EvidenceStatus.UNKNOWN, signal=OccupancySignal.UNKNOWN,
                    provenance=Provenance.REAL, coverage_confirmed=coverage_confirmed,
                    reason_code=reason,
                    explanation="Frame quality is insufficient for occupancy evidence. Check lighting, obstruction and camera view.",
                    observed_at=captured_at or now, mean_luminance=mean_luma,
                    luminance_stddev=std_luma, camera_label=camera_label,
                )
                return self._commit(evidence)
            detections = self.detector.detect(frame)
            raw_count = len(detections)
            with self._lock:
                state = self._room(room_id)
                state.recent_counts.append(raw_count)
                # Round fractional medians upward: missing a possible person is less safe than a brief extra occupied signal.
                smoothed_count = int(math.ceil(statistics.median(state.recent_counts)))
            # Any current raw detection resets downstream likely-empty dwell immediately.
            # Smoothing may keep the signal occupied for a short window after detections stop.
            signal = (
                OccupancySignal.PERSON_DETECTED
                if raw_count > 0 or smoothed_count > 0
                else OccupancySignal.NO_PERSON_DETECTED
            )
            eligible = (
                signal == OccupancySignal.NO_PERSON_DETECTED
                and coverage_confirmed
                and self.detector.available
            )
            if signal == OccupancySignal.PERSON_DETECTED:
                explanation = "A person was detected in the current or recent valid frames; reset any likely-empty timer immediately."
            elif coverage_confirmed:
                explanation = "No person was detected in this valid frame window. This is one signal only; downstream rules must require sustained evidence before flagging likely-empty."
            else:
                explanation = "No person was detected, but camera coverage has not been manually confirmed; do not use this as empty-room evidence."
            processing_age_ms = max(0, int((utc_now() - now).total_seconds() * 1000))
            evidence = self._metadata_evidence(
                room_id=room_id, status=EvidenceStatus.AVAILABLE, signal=signal,
                provenance=Provenance.REAL, coverage_confirmed=coverage_confirmed,
                reason_code=None, explanation=explanation, raw_count=raw_count,
                smoothed_count=smoothed_count, observed_at=captured_at or now,
                frame_age_ms=processing_age_ms, mean_luminance=mean_luma, luminance_stddev=std_luma,
                camera_label=camera_label, eligible_for_empty_timer=eligible,
            )
            return self._commit(evidence)
        except ValueError as exc:
            reason = str(exc) if str(exc) in {"INVALID_IMAGE", "FRAME_DIMENSIONS_EXCEEDED"} else "INVALID_FRAME"
            return self._commit(self._metadata_evidence(
                room_id=room_id, status=EvidenceStatus.UNKNOWN, signal=OccupancySignal.UNKNOWN,
                provenance=Provenance.REAL, coverage_confirmed=coverage_confirmed,
                reason_code=reason, explanation="The frame could not be safely analyzed; occupancy remains unknown.",
                camera_label=camera_label,
            ))
        except InferenceUnavailable as exc:
            return self._commit(self._metadata_evidence(
                room_id=room_id, status=EvidenceStatus.UNAVAILABLE, signal=OccupancySignal.UNKNOWN,
                provenance=Provenance.REAL, coverage_confirmed=coverage_confirmed,
                reason_code=str(exc) or "INFERENCE_UNAVAILABLE",
                explanation="Local inference failed; occupancy remains unknown.", camera_label=camera_label,
            ))
        except Exception as exc:
            # Fail closed. The exception's message/tensors are intentionally not returned or logged.
            logger.warning("Local vision inference failed (%s)", type(exc).__name__)
            return self._commit(self._metadata_evidence(
                room_id=room_id, status=EvidenceStatus.UNKNOWN, signal=OccupancySignal.UNKNOWN,
                provenance=Provenance.REAL, coverage_confirmed=coverage_confirmed,
                reason_code="INFERENCE_ERROR",
                explanation="Local inference encountered an error; occupancy remains unknown.",
                camera_label=camera_label,
            ))

    def record_simulated(self, request: SimulatedOccupancyRequest) -> OccupancyEvidence:
        signal = OccupancySignal.PERSON_DETECTED if request.person_count > 0 else OccupancySignal.NO_PERSON_DETECTED
        explanation = (
            "Explicit demo input: simulated person count is above zero. This is not camera evidence."
            if request.person_count > 0 else
            "Explicit demo input: simulated person count is zero. This is not proof that a real room is empty."
        )
        evidence = self._metadata_evidence(
            room_id=request.room_id, status=EvidenceStatus.AVAILABLE, signal=signal,
            provenance=Provenance.SIMULATED, coverage_confirmed=request.coverage_confirmed,
            reason_code="SIMULATED_INPUT", explanation=explanation,
            raw_count=request.person_count, smoothed_count=request.person_count,
            camera_label=request.camera_label, eligible_for_empty_timer=False,
        )
        return self._commit(evidence, persist_now=True)

    def current(self, room_id: str) -> tuple[OccupancyEvidence | None, int | None, str]:
        with self._lock:
            state = self._rooms.get(room_id)
            if state is None or state.latest is None or state.latest_monotonic is None:
                return None, None, "No occupancy evidence has been received for this room."
            age_ms = max(0, int((time.monotonic() - state.latest_monotonic) * 1000))
            evidence = state.latest
            if age_ms > self.settings.max_frame_age_ms and evidence.provenance == Provenance.REAL:
                stale = evidence.model_copy(update={
                    "status": EvidenceStatus.UNKNOWN,
                    "signal": OccupancySignal.UNKNOWN,
                    "eligible_for_empty_timer": False,
                    "reason_code": "STALE_FRAME",
                    "frame_age_ms": age_ms,
                    "explanation": "No fresh camera frame has arrived within the allowed window; occupancy is unknown, not empty.",
                })
                return stale, age_ms, stale.explanation
            return evidence.model_copy(update={"frame_age_ms": age_ms}), age_ms, evidence.explanation
