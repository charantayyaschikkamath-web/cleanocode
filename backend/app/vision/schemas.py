from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class OccupancySignal(StrEnum):
    PERSON_DETECTED = "PERSON_DETECTED"
    NO_PERSON_DETECTED = "NO_PERSON_DETECTED"
    UNKNOWN = "UNKNOWN"


class Provenance(StrEnum):
    REAL = "REAL"
    SIMULATED = "SIMULATED"
    DERIVED = "DERIVED"


class PersistenceStatus(StrEnum):
    RECORDED = "RECORDED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    FAILED = "FAILED"
    NOT_DUE = "NOT_DUE"


class OccupancyEvidence(BaseModel):
    """Small metadata record. Deliberately has no image/frame field."""

    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    evidence_id: str
    room_id: str = Field(min_length=1, max_length=120)
    status: EvidenceStatus
    signal: OccupancySignal
    provenance: Provenance
    raw_person_count: int | None = Field(default=None, ge=0)
    smoothed_person_count: int | None = Field(default=None, ge=0)
    observed_at: datetime
    received_at: datetime
    frame_age_ms: int | None = Field(default=None, ge=0)
    camera_label: str | None = Field(default=None, max_length=120)
    coverage_confirmed: bool = False
    eligible_for_empty_timer: bool = False
    reason_code: str | None = None
    explanation: str
    frame_mean_luminance: float | None = Field(default=None, ge=0, le=255)
    frame_luminance_stddev: float | None = Field(default=None, ge=0, le=128)
    detector_name: str | None = None
    detector_confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    smoothing_window: int = Field(default=5, ge=1, le=15)
    persistence_status: PersistenceStatus = PersistenceStatus.NOT_CONFIGURED


class VisionHealth(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    status: EvidenceStatus
    detector_available: bool
    detector_name: str | None = None
    detector_confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    detector_nms_threshold: float | None = Field(default=None, ge=0, le=1)
    model_configured: bool
    model_license_reviewed: bool
    persistence_sink_configured: bool
    max_frame_bytes: int
    max_frame_age_ms: int
    smoothing_window: int
    privacy: Literal["TRANSIENT_FRAMES_DERIVED_EVIDENCE_ONLY"] = "TRANSIENT_FRAMES_DERIVED_EVIDENCE_ONLY"
    message: str


class SimulatedOccupancyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: str = Field(min_length=1, max_length=120)
    person_count: int = Field(ge=0, le=100)
    coverage_confirmed: bool = False
    camera_label: str = Field(default="Manual demo input", max_length=120)


class OccupancyCurrentResponse(BaseModel):
    status: EvidenceStatus
    evidence: OccupancyEvidence | None = None
    age_ms: int | None = None
    message: str
