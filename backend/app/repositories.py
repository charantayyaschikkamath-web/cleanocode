from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.db.models import (
    ActionRecord,
    ActionTransition,
    Building,
    CampusEvent,
    EventFeedback,
    Room,
    SavingsLedgerEntry,
    ScenarioRun,
    SensorReading,
    VerificationRecord,
)
from app.schemas import BuildingCreate, EventCreate, FeedbackCreate, ReadingCreate, RoomCreate

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "PENDING_APPROVAL": {"COMMAND_SENT", "REJECTED"},
    "COMMAND_SENT": {"ACKED", "COMMAND_FAILED", "ACK_TIMEOUT"},
    "ACKED": {"VERIFYING"},
    "VERIFYING": {"VERIFIED_SUCCESS", "VERIFICATION_FAILED", "VERIFICATION_TIMEOUT"},
    "REJECTED": set(),
    "COMMAND_FAILED": set(),
    "ACK_TIMEOUT": set(),
    "VERIFIED_SUCCESS": set(),
    "VERIFICATION_FAILED": set(),
    "VERIFICATION_TIMEOUT": set(),
}


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("DATA_CONFLICT", "The record conflicts with an existing record or database constraint.") from exc


def create_building(session: Session, payload: BuildingCreate) -> Building:
    item = Building(name=payload.name, code=payload.code, location=payload.location, metadata_json=payload.metadata)
    session.add(item)
    _commit(session)
    session.refresh(item)
    return item


def get_building(session: Session, building_id: str) -> Building:
    item = session.get(Building, building_id)
    if item is None:
        raise NotFoundError("building", building_id)
    return item


def list_buildings(session: Session, limit: int = 100) -> list[Building]:
    return list(session.scalars(select(Building).order_by(Building.name).limit(limit)).all())


def create_room(session: Session, payload: RoomCreate) -> Room:
    get_building(session, payload.building_id)
    item = Room(
        building_id=payload.building_id,
        name=payload.name,
        code=payload.code,
        floor=payload.floor,
        capacity=payload.capacity,
        metadata_json=payload.metadata,
    )
    session.add(item)
    _commit(session)
    session.refresh(item)
    return item


def get_room(session: Session, room_id: str) -> Room:
    item = session.get(Room, room_id)
    if item is None:
        raise NotFoundError("room", room_id)
    return item


def list_rooms(session: Session, building_id: str | None = None, limit: int = 250) -> list[Room]:
    query: Select[tuple[Room]] = select(Room).order_by(Room.building_id, Room.name).limit(limit)
    if building_id:
        query = query.where(Room.building_id == building_id)
    return list(session.scalars(query).all())


def _same_reading(existing: SensorReading, payload: ReadingCreate) -> bool:
    return (
        existing.sensor_id == payload.sensor_id
        and existing.source_type == payload.source_type
        and existing.resource_type == payload.resource_type
        and existing.building_id == payload.building_id
        and existing.room_id == payload.room_id
        and Decimal(existing.value) == Decimal(payload.value)
        and existing.unit == payload.unit
        and existing.observed_at == payload.observed_at
        and existing.source_status == payload.source_status
        and existing.freshness_seconds == payload.freshness_seconds
        and existing.provenance == payload.provenance
        and (existing.metadata_json or {}) == payload.metadata
    )


def create_reading(session: Session, payload: ReadingCreate) -> SensorReading:
    if payload.idempotency_key:
        existing = session.scalar(select(SensorReading).where(SensorReading.idempotency_key == payload.idempotency_key))
        if existing:
            if not _same_reading(existing, payload):
                raise ConflictError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "This reading idempotency key was already used with a different payload.",
                    details={"reading_id": existing.id},
                )
            return existing

    get_building(session, payload.building_id)
    if payload.room_id:
        room = get_room(session, payload.room_id)
        if room.building_id != payload.building_id:
            raise DomainError(
                "ROOM_BUILDING_MISMATCH",
                "The room does not belong to the specified building.",
                status_code=422,
                details={"room_id": payload.room_id, "building_id": payload.building_id},
            )

    item = SensorReading(
        idempotency_key=payload.idempotency_key,
        sensor_id=payload.sensor_id,
        source_type=payload.source_type,
        resource_type=payload.resource_type,
        building_id=payload.building_id,
        room_id=payload.room_id,
        value=payload.value,
        unit=payload.unit,
        observed_at=payload.observed_at,
        source_status=payload.source_status,
        freshness_seconds=payload.freshness_seconds,
        provenance=payload.provenance,
        metadata_json=payload.metadata,
    )
    session.add(item)
    try:
        _commit(session)
    except ConflictError:
        # A concurrent request may have committed the same idempotency key after our read.
        if payload.idempotency_key:
            existing = session.scalar(select(SensorReading).where(SensorReading.idempotency_key == payload.idempotency_key))
            if existing and _same_reading(existing, payload):
                return existing
            if existing:
                raise ConflictError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "This reading idempotency key was already used with a different payload.",
                    details={"reading_id": existing.id},
                )
        raise
    session.refresh(item)
    return item


def list_readings(
    session: Session,
    *,
    building_id: str | None = None,
    room_id: str | None = None,
    resource_type: str | None = None,
    limit: int = 100,
) -> list[SensorReading]:
    query: Select[tuple[SensorReading]] = select(SensorReading).order_by(SensorReading.observed_at.desc()).limit(limit)
    if building_id:
        query = query.where(SensorReading.building_id == building_id)
    if room_id:
        query = query.where(SensorReading.room_id == room_id)
    if resource_type:
        query = query.where(SensorReading.resource_type == resource_type)
    return list(session.scalars(query).all())


def create_event(session: Session, payload: EventCreate) -> CampusEvent:
    get_building(session, payload.building_id)
    if payload.room_id:
        room = get_room(session, payload.room_id)
        if room.building_id != payload.building_id:
            raise DomainError(
                "ROOM_BUILDING_MISMATCH",
                "The room does not belong to the specified building.",
                status_code=422,
                details={"room_id": payload.room_id, "building_id": payload.building_id},
            )
    item = CampusEvent(
        event_type=payload.event_type,
        severity=payload.severity,
        status="OPEN",
        building_id=payload.building_id,
        room_id=payload.room_id,
        trigger_rule=payload.trigger_rule,
        first_seen_at=payload.first_seen_at,
        last_updated_at=payload.first_seen_at,
        evidence_refs=payload.evidence_refs,
        evidence_snapshot=payload.evidence_snapshot,
        provenance=payload.provenance,
    )
    session.add(item)
    _commit(session)
    session.refresh(item)
    return item


def list_events(session: Session, *, status: str | None = None, severity: str | None = None, limit: int = 100) -> list[CampusEvent]:
    query: Select[tuple[CampusEvent]] = select(CampusEvent).order_by(CampusEvent.first_seen_at.desc()).limit(limit)
    if status:
        query = query.where(CampusEvent.status == status)
    if severity:
        query = query.where(CampusEvent.severity == severity)
    return list(session.scalars(query).all())


def get_event(session: Session, event_id: str) -> CampusEvent:
    item = session.get(CampusEvent, event_id)
    if item is None:
        raise NotFoundError("event", event_id)
    return item


def list_savings_ledger(
    session: Session,
    *,
    resource_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[SavingsLedgerEntry]:
    query: Select[tuple[SavingsLedgerEntry]] = select(SavingsLedgerEntry).order_by(SavingsLedgerEntry.created_at.desc()).limit(limit)
    if resource_type:
        query = query.where(SavingsLedgerEntry.resource_type == resource_type)
    if status:
        query = query.where(SavingsLedgerEntry.status == status)
    return list(session.scalars(query).all())


def create_feedback(session: Session, payload: FeedbackCreate) -> EventFeedback:
    event_item = session.get(CampusEvent, payload.event_id)
    if event_item is None:
        raise NotFoundError("event", payload.event_id)
    item = EventFeedback(
        event_id=payload.event_id,
        feedback_type=payload.feedback_type,
        comment=payload.comment,
        actor=payload.actor,
    )
    session.add(item)
    _commit(session)
    session.refresh(item)
    return item


def create_action_record(
    session: Session,
    *,
    event_id: str,
    idempotency_key: str,
    action_type: str,
    actor: str = "operator",
    command_payload: dict[str, Any] | None = None,
    baseline_reading_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> ActionRecord:
    request_command = command_payload or {}
    request_baseline_ids = baseline_reading_ids or []
    request_metadata = metadata or {}

    def same_action_request(existing: ActionRecord) -> bool:
        return (
            existing.event_id == event_id
            and existing.action_type == action_type
            and existing.actor == actor
            and existing.command_payload == request_command
            and existing.baseline_reading_ids == request_baseline_ids
            and existing.metadata_json == request_metadata
        )

    existing = session.scalar(select(ActionRecord).where(ActionRecord.idempotency_key == idempotency_key))
    if existing:
        if same_action_request(existing):
            return existing
        raise ConflictError("IDEMPOTENCY_KEY_REUSED", "The action idempotency key belongs to a different action payload.", details={"action_id": existing.id})
    if session.get(CampusEvent, event_id) is None:
        raise NotFoundError("event", event_id)

    now = now or datetime.now(timezone.utc)
    item = ActionRecord(
        event_id=event_id,
        idempotency_key=idempotency_key,
        action_type=action_type,
        state="PENDING_APPROVAL",
        actor=actor,
        command_payload=request_command,
        baseline_reading_ids=request_baseline_ids,
        metadata_json=request_metadata,
        created_at=now,
        updated_at=now,
    )
    try:
        session.add(item)
        session.flush()
        session.add(ActionTransition(
            action_id=item.id,
            sequence_no=1,
            previous_state=None,
            new_state="PENDING_APPROVAL",
            actor_or_source=actor,
            occurred_at=now,
            evidence={"event_id": event_id},
            note="Action created; awaiting human approval.",
        ))
        _commit(session)
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(ActionRecord).where(ActionRecord.idempotency_key == idempotency_key))
        if existing and same_action_request(existing):
            return existing
        if existing:
            raise ConflictError("IDEMPOTENCY_KEY_REUSED", "The action idempotency key belongs to a different action payload.", details={"action_id": existing.id})
        raise ConflictError("DATA_CONFLICT", "The action conflicts with an existing record or database constraint.")
    except ConflictError:
        existing = session.scalar(select(ActionRecord).where(ActionRecord.idempotency_key == idempotency_key))
        if existing and same_action_request(existing):
            return existing
        if existing:
            raise ConflictError("IDEMPOTENCY_KEY_REUSED", "The action idempotency key belongs to a different action payload.", details={"action_id": existing.id})
        raise
    session.refresh(item)
    return item


def append_action_transition(
    session: Session,
    *,
    action_id: str,
    new_state: str,
    actor_or_source: str,
    evidence: dict[str, Any] | None = None,
    note: str | None = None,
    request_key: str | None = None,
    now: datetime | None = None,
) -> ActionTransition:
    if request_key:
        prior = session.scalar(select(ActionTransition).where(ActionTransition.request_key == request_key))
        if prior:
            same_request = (
                prior.action_id == action_id
                and prior.new_state == new_state
                and prior.actor_or_source == actor_or_source
                and prior.evidence == (evidence or {})
                and prior.note == note
            )
            if same_request:
                return prior
            raise ConflictError("TRANSITION_KEY_REUSED", "The transition request key was already used for a different transition.")

    action = session.get(ActionRecord, action_id)
    if action is None:
        raise NotFoundError("action", action_id)
    if action.state == new_state:
        latest = session.scalar(
            select(ActionTransition).where(ActionTransition.action_id == action_id).order_by(ActionTransition.sequence_no.desc())
        )
        if latest is not None and latest.new_state == new_state:
            return latest
    if new_state not in ALLOWED_TRANSITIONS.get(action.state, set()):
        raise DomainError(
            "INVALID_ACTION_TRANSITION",
            f"Transition from {action.state} to {new_state} is not allowed.",
            status_code=409,
            details={"action_id": action_id, "current_state": action.state, "requested_state": new_state},
        )

    latest_seq = session.scalar(
        select(ActionTransition.sequence_no).where(ActionTransition.action_id == action_id).order_by(ActionTransition.sequence_no.desc()).limit(1)
    ) or 0
    when = now or datetime.now(timezone.utc)
    transition = ActionTransition(
        action_id=action_id,
        sequence_no=latest_seq + 1,
        request_key=request_key,
        previous_state=action.state,
        new_state=new_state,
        actor_or_source=actor_or_source,
        occurred_at=when,
        evidence=evidence or {},
        note=note,
    )
    action.state = new_state
    action.updated_at = when
    session.add(transition)
    _commit(session)
    session.refresh(transition)
    return transition


def record_verification(
    session: Session,
    *,
    action_id: str,
    result: str,
    baseline_snapshot: dict[str, Any],
    post_action_snapshot: dict[str, Any],
    required_change: dict[str, Any],
    observed_change: dict[str, Any],
    evidence_reading_ids: list[str],
    verification_window_start: datetime | None = None,
    verification_window_end: datetime | None = None,
) -> VerificationRecord:
    action = session.get(ActionRecord, action_id)
    if action is None:
        raise NotFoundError("action", action_id)
    item = VerificationRecord(
        action_id=action_id,
        result=result,
        baseline_snapshot=baseline_snapshot,
        post_action_snapshot=post_action_snapshot,
        required_change=required_change,
        observed_change=observed_change,
        evidence_reading_ids=evidence_reading_ids,
        verification_window_start=verification_window_start,
        verification_window_end=verification_window_end,
    )
    session.add(item)
    _commit(session)
    session.refresh(item)
    return item


def record_verified_savings(
    session: Session,
    *,
    action_id: str,
    resource_type: str,
    unit: str,
    calculation_version: str,
    verification_transition_id: str,
    energy_kwh: Decimal | None = None,
    cost_amount: Decimal | None = None,
    currency: str | None = None,
    water_liters: Decimal | None = None,
    co2_kg: Decimal | None = None,
    status: str = "VERIFIED_SIMULATED",
    observation_start: datetime | None = None,
    observation_end: datetime | None = None,
    source_reading_ids: list[str] | None = None,
    calculation_inputs: dict[str, Any] | None = None,
    assumptions: list[str] | None = None,
) -> SavingsLedgerEntry:
    """Create one ledger entry only after a persisted VERIFIED_SUCCESS transition."""
    if cost_amount is not None:
        if not currency or len(currency) != 3 or not currency.isalpha():
            raise DomainError("CURRENCY_REQUIRED", "A three-letter currency code is required when recording a cost amount.", status_code=422)
        currency = currency.upper()
    if any(value is not None and value < 0 for value in (energy_kwh, cost_amount, water_liters, co2_kg)):
        raise DomainError("NEGATIVE_IMPACT_VALUE", "Savings and impact values must be non-negative.", status_code=422)

    prior = session.scalar(select(SavingsLedgerEntry).where(SavingsLedgerEntry.action_id == action_id))
    if prior:
        same_payload = (
            prior.verification_transition_id == verification_transition_id
            and prior.resource_type == resource_type
            and prior.unit == unit
            and prior.calculation_version == calculation_version
            and prior.status == status
            and prior.energy_kwh == energy_kwh
            and prior.cost_amount == cost_amount
            and prior.currency == currency
            and prior.water_liters == water_liters
            and prior.co2_kg == co2_kg
            and prior.source_reading_ids == (source_reading_ids or [])
            and prior.calculation_inputs == (calculation_inputs or {})
            and prior.assumptions == (assumptions or [])
            and prior.observation_start == observation_start
            and prior.observation_end == observation_end
        )
        if same_payload:
            return prior
        raise ConflictError(
            "LEDGER_ENTRY_ALREADY_EXISTS",
            "This action already has a verified ledger entry with different calculation inputs; the original was preserved.",
            details={"ledger_entry_id": prior.id, "action_id": action_id},
        )
    action = session.get(ActionRecord, action_id)
    if action is None:
        raise NotFoundError("action", action_id)
    transition = session.get(ActionTransition, verification_transition_id)
    if transition is None or transition.action_id != action_id or transition.new_state != "VERIFIED_SUCCESS":
        raise DomainError(
            "VERIFICATION_REQUIRED",
            "Savings can only be recorded against this action's persisted VERIFIED_SUCCESS transition.",
            status_code=409,
            details={"action_id": action_id, "verification_transition_id": verification_transition_id},
        )
    if action.state != "VERIFIED_SUCCESS":
        raise DomainError(
            "ACTION_NOT_VERIFIED",
            "Savings cannot be recorded unless the action's current state is VERIFIED_SUCCESS.",
            status_code=409,
            details={"action_id": action_id, "state": action.state},
        )
    if status not in {"VERIFIED_SIMULATED", "MEASURED"}:
        raise DomainError("INVALID_LEDGER_STATUS", "Ledger status must be VERIFIED_SIMULATED or MEASURED.", status_code=422)
    if status == "MEASURED":
        if not source_reading_ids:
            raise DomainError("MEASURED_EVIDENCE_REQUIRED", "Measured impact must include source reading IDs.", status_code=422)
        event = session.get(CampusEvent, action.event_id)
        if event is None:
            raise NotFoundError("event", action.event_id)
        readings = list(session.scalars(select(SensorReading).where(SensorReading.id.in_(source_reading_ids))).all())
        found_ids = {reading.id for reading in readings}
        if found_ids != set(source_reading_ids):
            raise DomainError(
                "MEASURED_READING_NOT_FOUND",
                "Every measured source reading ID must exist in the database.",
                status_code=422,
                details={"missing_reading_ids": sorted(set(source_reading_ids) - found_ids)},
            )
        if any(reading.provenance != "REAL" or reading.source_status != "HEALTHY" for reading in readings):
            raise DomainError(
                "MEASURED_READING_NOT_REAL_AND_HEALTHY",
                "Measured impact requires REAL, HEALTHY source readings; simulated or unhealthy readings cannot be labeled measured.",
                status_code=422,
            )
        if any(
            reading.building_id != event.building_id
            or (event.room_id is not None and reading.room_id != event.room_id)
            for reading in readings
        ):
            raise DomainError(
                "MEASURED_EVIDENCE_LOCATION_MISMATCH",
                "Measured evidence must belong to the building and room associated with the action's event.",
                status_code=422,
            )

    item = SavingsLedgerEntry(
        action_id=action_id,
        verification_transition_id=verification_transition_id,
        status=status,
        energy_kwh=energy_kwh,
        cost_amount=cost_amount,
        currency=currency,
        water_liters=water_liters,
        co2_kg=co2_kg,
        resource_type=resource_type,
        unit=unit,
        observation_start=observation_start,
        observation_end=observation_end,
        source_reading_ids=source_reading_ids or [],
        calculation_version=calculation_version,
        calculation_inputs=calculation_inputs or {},
        assumptions=assumptions or [],
    )
    session.add(item)
    try:
        _commit(session)
    except ConflictError:
        existing = session.scalar(select(SavingsLedgerEntry).where(SavingsLedgerEntry.action_id == action_id))
        if existing:
            raise ConflictError(
                "LEDGER_ENTRY_ALREADY_EXISTS",
                "A concurrent request recorded the ledger entry; review the existing entry before retrying.",
                details={"ledger_entry_id": existing.id, "action_id": action_id},
            )
        raise
    session.refresh(item)
    return item


def create_scenario_run(
    session: Session,
    *,
    scenario_name: str,
    request_payload: dict[str, Any],
    result_payload: dict[str, Any] | None = None,
    status: str = "COMPLETED",
    provenance: str = "SIMULATED",
    virtual_started_at: datetime | None = None,
    virtual_ended_at: datetime | None = None,
    wall_started_at: datetime | None = None,
    wall_ended_at: datetime | None = None,
    error_message: str | None = None,
) -> ScenarioRun:
    item = ScenarioRun(
        scenario_name=scenario_name,
        request_payload=request_payload,
        result_payload=result_payload or {},
        status=status,
        provenance=provenance,
        virtual_started_at=virtual_started_at,
        virtual_ended_at=virtual_ended_at,
        wall_started_at=wall_started_at or datetime.now(timezone.utc),
        wall_ended_at=wall_ended_at,
        error_message=error_message,
    )
    session.add(item)
    _commit(session)
    session.refresh(item)
    return item
