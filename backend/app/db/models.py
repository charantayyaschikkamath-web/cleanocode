from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, new_id, utc_now


class SchemaVersion(Base):
    __tablename__ = "schema_versions"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    description: Mapped[str] = mapped_column(String(250), nullable=False)


class Building(Base):
    __tablename__ = "buildings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    location: Mapped[str | None] = mapped_column(String(250), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now)


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    building_id: Mapped[str] = mapped_column(ForeignKey("buildings.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(40), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now)
    __table_args__ = (
        CheckConstraint("capacity IS NULL OR capacity >= 0", name="room_capacity_nonnegative"),
        UniqueConstraint("building_id", "code", name="uq_rooms_building_code"),
    )


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    sensor_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    building_id: Mapped[str] = mapped_column(ForeignKey("buildings.id", ondelete="RESTRICT"), nullable=False, index=True)
    room_id: Mapped[str | None] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=True, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    source_status: Mapped[str] = mapped_column(String(30), nullable=False, default="HEALTHY", index=True)
    freshness_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provenance: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    __table_args__ = (
        CheckConstraint("source_status IN ('HEALTHY','STALE','UNAVAILABLE','UNKNOWN')", name="reading_source_status"),
        CheckConstraint("provenance IN ('REAL','SIMULATED','DERIVED')", name="reading_provenance"),
        CheckConstraint("freshness_seconds IS NULL OR freshness_seconds >= 0", name="reading_freshness_nonnegative"),
        Index("ix_reading_location_resource_time", "building_id", "room_id", "resource_type", "observed_at"),
    )


class CampusEvent(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM", index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN", index=True)
    building_id: Mapped[str] = mapped_column(ForeignKey("buildings.id", ondelete="RESTRICT"), nullable=False, index=True)
    room_id: Mapped[str | None] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=True, index=True)
    trigger_rule: Mapped[str] = mapped_column(String(200), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    last_updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    provenance: Mapped[str] = mapped_column(String(20), nullable=False, default="SIMULATED")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now)
    __table_args__ = (
        CheckConstraint("severity IN ('INFO','LOW','MEDIUM','HIGH','CRITICAL')", name="event_severity"),
        CheckConstraint("status IN ('OPEN','ACKNOWLEDGED','RESOLVED','FALSE_POSITIVE','CLOSED')", name="event_status"),
        CheckConstraint("provenance IN ('REAL','SIMULATED','DERIVED')", name="event_provenance"),
    )


class EventFeedback(Base):
    __tablename__ = "event_feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"), nullable=False, index=True)
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="operator")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class ActionRecord(Base):
    __tablename__ = "actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="PENDING_APPROVAL", index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="operator")
    command_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    baseline_reading_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now)


class ActionTransition(Base):
    __tablename__ = "action_transitions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id", ondelete="RESTRICT"), nullable=False, index=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    request_key: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    previous_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    new_state: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_or_source: Mapped[str] = mapped_column(String(120), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint("action_id", "sequence_no", name="uq_action_transition_sequence"),
        CheckConstraint("sequence_no >= 1", name="transition_sequence_positive"),
    )


class VerificationRecord(Base):
    __tablename__ = "verification_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id", ondelete="RESTRICT"), nullable=False, index=True)
    result: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    baseline_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    post_action_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    required_change: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    observed_change: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evidence_reading_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    verification_window_start: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    verification_window_end: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class SavingsLedgerEntry(Base):
    __tablename__ = "savings_ledger"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id", ondelete="RESTRICT"), nullable=False, unique=True)
    verification_transition_id: Mapped[str] = mapped_column(ForeignKey("action_transitions.id", ondelete="RESTRICT"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    energy_kwh: Mapped[Decimal | None] = mapped_column(Numeric(18, 7), nullable=True)
    cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    water_liters: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    co2_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    observation_start: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    observation_end: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    source_reading_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    calculation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    calculation_inputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    assumptions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    __table_args__ = (
        CheckConstraint("status IN ('VERIFIED_SIMULATED','MEASURED')", name="ledger_status_verified_only"),
        CheckConstraint("energy_kwh IS NULL OR energy_kwh >= 0", name="ledger_energy_nonnegative"),
        CheckConstraint("cost_amount IS NULL OR cost_amount >= 0", name="ledger_cost_nonnegative"),
        CheckConstraint("water_liters IS NULL OR water_liters >= 0", name="ledger_water_nonnegative"),
        CheckConstraint("co2_kg IS NULL OR co2_kg >= 0", name="ledger_co2_nonnegative"),
    )


class ScenarioRun(Base):
    __tablename__ = "scenario_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scenario_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    provenance: Mapped[str] = mapped_column(String(20), nullable=False, default="SIMULATED")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="COMPLETED")
    virtual_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    virtual_ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    wall_started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    wall_ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("provenance IN ('REAL','SIMULATED','DERIVED')", name="scenario_provenance"),
    )
