from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Provenance = Literal["REAL", "SIMULATED", "DERIVED"]
SourceStatus = Literal["HEALTHY", "STALE", "UNAVAILABLE", "UNKNOWN"]
Severity = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
EventStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED", "FALSE_POSITIVE", "CLOSED"]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class BuildingCreate(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=250)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class BuildingOut(OrmModel):
    id: str
    name: str
    code: str | None
    location: str | None
    metadata_json: dict[str, Any] = Field(validation_alias="metadata_json", serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime


class RoomCreate(StrictModel):
    building_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=80)
    floor: str | None = Field(default=None, max_length=40)
    capacity: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class RoomOut(OrmModel):
    id: str
    building_id: str
    name: str
    code: str | None
    floor: str | None
    capacity: int | None
    metadata_json: dict[str, Any] = Field(validation_alias="metadata_json", serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime


class ReadingCreate(StrictModel):
    idempotency_key: str | None = Field(default=None, max_length=160)
    sensor_id: str | None = Field(default=None, max_length=160)
    source_type: str = Field(min_length=1, max_length=80)
    resource_type: str = Field(min_length=1, max_length=80)
    building_id: str = Field(min_length=1, max_length=36)
    room_id: str | None = Field(default=None, max_length=36)
    value: Decimal
    unit: str = Field(min_length=1, max_length=40)
    observed_at: datetime
    source_status: SourceStatus = "HEALTHY"
    freshness_seconds: int | None = Field(default=None, ge=0)
    provenance: Provenance
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_be_utc_aware(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("source_type", "resource_type", "unit")
    @classmethod
    def strip_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field cannot be blank")
        return value

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("value must be finite")
        return value


class ReadingOut(OrmModel):
    id: str
    idempotency_key: str | None
    sensor_id: str | None
    source_type: str
    resource_type: str
    building_id: str
    room_id: str | None
    value: Decimal
    unit: str
    observed_at: datetime
    source_status: SourceStatus
    freshness_seconds: int | None
    provenance: Provenance
    metadata_json: dict[str, Any] = Field(validation_alias="metadata_json", serialization_alias="metadata")
    created_at: datetime


class EventCreate(StrictModel):
    event_type: str = Field(min_length=1, max_length=100)
    severity: Severity = "MEDIUM"
    building_id: str = Field(min_length=1, max_length=36)
    room_id: str | None = Field(default=None, max_length=36)
    trigger_rule: str = Field(min_length=1, max_length=200)
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evidence_refs: list[str] = Field(default_factory=list, max_length=250)
    evidence_snapshot: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance

    @field_validator("first_seen_at")
    @classmethod
    def first_seen_is_aware(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("event_type", "trigger_rule")
    @classmethod
    def event_text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field cannot be blank")
        return value


class EventOut(OrmModel):
    id: str
    event_type: str
    severity: Severity
    status: EventStatus
    building_id: str
    room_id: str | None
    trigger_rule: str
    first_seen_at: datetime
    last_updated_at: datetime
    evidence_refs: list[str]
    evidence_snapshot: dict[str, Any]
    provenance: Provenance
    created_at: datetime
    updated_at: datetime


class FeedbackCreate(StrictModel):
    event_id: str = Field(min_length=1, max_length=36)
    feedback_type: str = Field(min_length=1, max_length=50)
    comment: str | None = Field(default=None, max_length=3000)
    actor: str = Field(default="operator", min_length=1, max_length=120)


class FeedbackOut(OrmModel):
    id: str
    event_id: str
    feedback_type: str
    comment: str | None
    actor: str
    created_at: datetime


class EnergyImpactRequest(StrictModel):
    power_watts: Decimal = Field(ge=0)
    duration_virtual_seconds: Decimal = Field(ge=0)
    tariff_per_kwh: Decimal | None = Field(default=None, ge=0)
    co2_factor_kg_per_kwh: Decimal | None = Field(default=None, ge=0)


class LedgerEntryOut(OrmModel):
    id: str
    action_id: str
    verification_transition_id: str
    status: Literal["VERIFIED_SIMULATED", "MEASURED"]
    energy_kwh: Decimal | None
    cost_amount: Decimal | None
    currency: str | None
    water_liters: Decimal | None
    co2_kg: Decimal | None
    resource_type: str
    unit: str
    observation_start: datetime | None
    observation_end: datetime | None
    source_reading_ids: list[str]
    calculation_version: str
    calculation_inputs: dict[str, Any]
    assumptions: list[str]
    created_at: datetime


class PreflightCheck(BaseModel):
    name: str
    status: Literal["PASS", "WARN", "FAIL"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class PreflightOut(BaseModel):
    status: Literal["PASS", "WARN", "FAIL"]
    timestamp: datetime
    checks: list[PreflightCheck]


class MetricFact(BaseModel):
    value: str | int | None
    unit: str
    availability: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"]
    provenance: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class OverviewFactsOut(BaseModel):
    schema_version: str
    as_of: datetime
    open_events: MetricFact
    latest_readings: list[dict[str, Any]]
    verified_energy_saved_kwh: MetricFact
    verified_cost_saved: MetricFact
    verified_water_saved_liters: MetricFact
    verified_co2_avoided_kg: MetricFact
