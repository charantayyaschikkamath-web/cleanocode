from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import DomainError
from app.db.models import ActionTransition, Building, CampusEvent, SavingsLedgerEntry
from app.repositories import append_action_transition, create_action_record, record_verified_savings
from app.schemas import BuildingCreate, EventCreate
from app.repositories import create_building, create_event


def _make_event(session):
    building = create_building(session, BuildingCreate(name="Action Test Building"))
    event = create_event(session, EventCreate(
        event_type="likely_energy_waste",
        severity="HIGH",
        building_id=building.id,
        trigger_rule="power_above_threshold",
        first_seen_at=datetime.now(timezone.utc),
        evidence_snapshot={"power_watts": "1000"},
        provenance="SIMULATED",
    ))
    return event


def test_savings_cannot_be_recorded_without_verified_success(db_session):
    event = _make_event(db_session)
    action = create_action_record(
        db_session,
        event_id=event.id,
        idempotency_key="action-no-verify",
        action_type="reduce_simulated_power",
    )
    with pytest.raises(DomainError, match="VERIFIED_SUCCESS"):
        record_verified_savings(
            db_session,
            action_id=action.id,
            resource_type="energy",
            unit="kWh",
            calculation_version="test-v1",
            verification_transition_id="not-a-transition",
            energy_kwh=Decimal("0.25"),
        )
    assert db_session.scalars(select(SavingsLedgerEntry)).all() == []


def test_only_successful_verified_action_creates_one_idempotent_ledger_entry(db_session):
    event = _make_event(db_session)
    action = create_action_record(
        db_session,
        event_id=event.id,
        idempotency_key="action-success",
        action_type="reduce_simulated_power",
    )
    assert action.state == "PENDING_APPROVAL"
    assert create_action_record(
        db_session,
        event_id=event.id,
        idempotency_key="action-success",
        action_type="reduce_simulated_power",
    ).id == action.id

    for state in ("COMMAND_SENT", "ACKED", "VERIFYING", "VERIFIED_SUCCESS"):
        transition = append_action_transition(
            db_session,
            action_id=action.id,
            new_state=state,
            actor_or_source="test",
            request_key=f"transition-{state}",
        )
    assert action.state == "VERIFIED_SUCCESS"
    assert transition.new_state == "VERIFIED_SUCCESS"

    entry = record_verified_savings(
        db_session,
        action_id=action.id,
        resource_type="energy",
        unit="kWh",
        calculation_version="test-v1",
        verification_transition_id=transition.id,
        energy_kwh=Decimal("0.2500000"),
        cost_amount=None,
        status="VERIFIED_SIMULATED",
        calculation_inputs={"power_watts": "1000", "duration_virtual_seconds": "900"},
        assumptions=["synthetic scenario"],
    )
    repeated = record_verified_savings(
        db_session,
        action_id=action.id,
        resource_type="energy",
        unit="kWh",
        calculation_version="test-v1",
        verification_transition_id=transition.id,
        energy_kwh=Decimal("0.2500000"),
        cost_amount=None,
        status="VERIFIED_SIMULATED",
        calculation_inputs={"power_watts": "1000", "duration_virtual_seconds": "900"},
        assumptions=["synthetic scenario"],
    )
    assert entry.id == repeated.id
    assert repeated.energy_kwh == Decimal("0.2500000")
    assert len(db_session.scalars(select(SavingsLedgerEntry)).all()) == 1


def test_invalid_transition_is_rejected_and_action_audit_is_append_only(db_session):
    event = _make_event(db_session)
    action = create_action_record(
        db_session,
        event_id=event.id,
        idempotency_key="action-invalid-transition",
        action_type="no_op",
    )
    with pytest.raises(DomainError, match="not allowed"):
        append_action_transition(db_session, action_id=action.id, new_state="VERIFIED_SUCCESS", actor_or_source="test")

    first_transition = db_session.scalar(select(ActionTransition).where(ActionTransition.action_id == action.id))
    first_transition.note = "tampered"
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_failed_verification_never_creates_ledger_entry(db_session):
    event = _make_event(db_session)
    action = create_action_record(
        db_session,
        event_id=event.id,
        idempotency_key="action-ignored-command",
        action_type="reduce_simulated_power",
    )
    for state in ("COMMAND_SENT", "ACKED", "VERIFYING", "VERIFICATION_FAILED"):
        terminal = append_action_transition(
            db_session,
            action_id=action.id,
            new_state=state,
            actor_or_source="failure-test",
            request_key=f"ignored-{state}",
        )
    assert action.state == "VERIFICATION_FAILED"
    with pytest.raises(DomainError, match="VERIFIED_SUCCESS"):
        record_verified_savings(
            db_session,
            action_id=action.id,
            resource_type="energy",
            unit="kWh",
            calculation_version="test-v1",
            verification_transition_id=terminal.id,
            energy_kwh=Decimal("0.5"),
        )
    assert db_session.scalars(select(SavingsLedgerEntry)).all() == []


def test_simulated_readings_cannot_be_labeled_measured(db_session):
    from app.schemas import ReadingCreate
    from app.repositories import create_reading

    event = _make_event(db_session)
    reading = create_reading(db_session, ReadingCreate(
        source_type="power_meter",
        resource_type="energy",
        building_id=event.building_id,
        value=Decimal("800"),
        unit="W",
        observed_at=datetime.now(timezone.utc),
        source_status="HEALTHY",
        provenance="SIMULATED",
    ))
    action = create_action_record(
        db_session,
        event_id=event.id,
        idempotency_key="action-measured-check",
        action_type="reduce_simulated_power",
    )
    for state in ("COMMAND_SENT", "ACKED", "VERIFYING", "VERIFIED_SUCCESS"):
        transition = append_action_transition(
            db_session,
            action_id=action.id,
            new_state=state,
            actor_or_source="measurement-test",
        )
    with pytest.raises(DomainError, match="REAL, HEALTHY"):
        record_verified_savings(
            db_session,
            action_id=action.id,
            resource_type="energy",
            unit="kWh",
            calculation_version="test-v1",
            verification_transition_id=transition.id,
            status="MEASURED",
            energy_kwh=Decimal("0.1"),
            source_reading_ids=[reading.id],
        )
    assert db_session.scalars(select(SavingsLedgerEntry)).all() == []
