from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import DomainError
from app.db.session import initialize_database, make_engine
from app.main import create_app
from app.routers.actions import router as actions_router
from app.routers.scenarios import router as scenarios_router
from app.repositories import append_action_transition, create_building, create_event
from app.schemas import BuildingCreate, EventCreate


@pytest.fixture
def account3_client():
    settings = Settings(
        database_url="sqlite://",
        api_prefix="/api/v1",
        virtual_time_multiplier=30,
        allowed_origins=("http://localhost:5173",),
        tariff_per_kwh=None,
        co2_factor_kg_per_kwh=None,
    )
    engine = make_engine("sqlite://")
    initialize_database(engine)
    app = create_app(settings=settings, engine=engine)
    # Account 9 owns production router registration; this test app mounts the
    # Account 3 feature routers without modifying the central entrypoint.
    app.include_router(actions_router, prefix=settings.api_prefix)
    app.include_router(scenarios_router, prefix=settings.api_prefix)
    with TestClient(app) as client:
        yield client
    engine.dispose()


def _building_room(client, capacity=40):
    building = client.post("/api/v1/buildings", json={"name": "Account 3 Test Block", "code": f"T-{datetime.now(timezone.utc).microsecond}"})
    assert building.status_code == 201, building.text
    building_id = building.json()["id"]
    room = client.post("/api/v1/rooms", json={"building_id": building_id, "name": "Lab 101", "capacity": capacity})
    assert room.status_code == 201, room.text
    return building_id, room.json()["id"]


def _run(client, scenario, building_id, room_id=None, **extra):
    payload = {"scenario_type": scenario, "building_id": building_id, "duration_virtual_seconds": 900, "seed": 123, **extra}
    if room_id:
        payload["room_id"] = room_id
    response = client.post("/api/v1/scenarios/run", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_scenario_detection_is_evidence_backed_and_provenance_is_simulated(account3_client):
    building_id, room_id = _building_room(account3_client)
    result = _run(account3_client, "EMPTY_ROOM_HIGH_POWER", building_id, room_id)
    assert result["status"] == "COMPLETED"
    assert result["provenance"] == "SIMULATED"
    assert len(result["reading_ids"]) == 6
    assert len(result["event_ids"]) == 1
    event = account3_client.get(f"/api/v1/events/{result['event_ids'][0]}").json()
    assert event["event_type"] == "likely_energy_waste"
    assert event["provenance"] == "SIMULATED"
    snapshot = event["evidence_snapshot"]
    assert snapshot["rule_id"] == "ENERGY_EMPTY_HIGH_POWER_V1"
    assert snapshot["thresholds"]["min_power_w"] == 500
    assert "confidence" not in snapshot
    evidence = account3_client.get(f"/api/v1/events/{event['id']}/evidence").json()
    assert len(evidence["readings"]) == 6
    assert {x["provenance"] for x in evidence["readings"]} == {"SIMULATED"}


def test_verified_success_needs_human_approval_and_creates_exactly_one_ledger_row(account3_client):
    building_id, room_id = _building_room(account3_client)
    result = _run(account3_client, "VERIFIED_RESPONSE", building_id, room_id)
    assert len(result["action_ids"]) == 1
    action_id = result["action_ids"][0]
    before = account3_client.get("/api/v1/ledger").json()
    assert before == []
    action_before = account3_client.get(f"/api/v1/actions/{action_id}").json()
    assert action_before["status"] == "PENDING_APPROVAL"
    assert len(action_before["baseline_reading_ids"]) == 3

    headers = {"Idempotency-Key": "operator-approve-001"}
    approved = account3_client.post(f"/api/v1/actions/{action_id}/approve", headers=headers)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "VERIFIED_SUCCESS"
    assert body["acknowledgement_is_success"] is False
    assert body["verification"]["result"] == "VERIFIED_SUCCESS"
    assert Decimal(body["verification"]["observed_change"]["observed_drop_percent"]) >= Decimal("30")
    assert body["ledger_entry"]["status"] == "VERIFIED_SIMULATED"
    assert Decimal(body["ledger_entry"]["energy_kwh"]) > 0
    assert body["ledger_entry"]["cost_amount"] is None
    assert body["ledger_entry"]["co2_kg"] is None

    repeated = account3_client.post(f"/api/v1/actions/{action_id}/approve", headers=headers)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["status"] == "VERIFIED_SUCCESS"
    assert len(account3_client.get("/api/v1/ledger").json()) == 1
    states = [row["new_state"] for row in account3_client.get(f"/api/v1/actions/{action_id}/transitions").json()]
    assert states == ["PENDING_APPROVAL", "COMMAND_SENT", "ACKED", "VERIFYING", "VERIFIED_SUCCESS"]


def test_dropped_command_times_out_without_savings(account3_client):
    building_id, room_id = _building_room(account3_client)
    result = _run(account3_client, "COMMAND_DROPPED", building_id, room_id)
    action_id = result["action_ids"][0]
    response = account3_client.post(f"/api/v1/actions/{action_id}/approve", headers={"Idempotency-Key": "approve-drop-001"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ACK_TIMEOUT"
    assert response.json()["ledger_entry"] is None
    assert account3_client.get("/api/v1/ledger").json() == []
    states = [row["new_state"] for row in account3_client.get(f"/api/v1/actions/{action_id}/transitions").json()]
    assert states == ["PENDING_APPROVAL", "COMMAND_SENT", "ACK_TIMEOUT"]


def test_acknowledged_but_ignored_action_fails_independent_verification(account3_client):
    building_id, room_id = _building_room(account3_client)
    result = _run(account3_client, "ACKNOWLEDGED_IGNORED", building_id, room_id)
    action_id = result["action_ids"][0]
    response = account3_client.post(f"/api/v1/actions/{action_id}/approve", headers={"Idempotency-Key": "approve-ignore-001"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "VERIFICATION_FAILED"
    assert response.json()["verification"]["result"] == "VERIFICATION_FAILED"
    assert Decimal(response.json()["verification"]["observed_change"]["observed_drop_percent"]) < Decimal("30")
    assert response.json()["ledger_entry"] is None
    assert account3_client.get("/api/v1/ledger").json() == []


def test_all_resource_scenarios_and_unknown_states(account3_client):
    building_id, room_id = _building_room(account3_client)
    cases = [
        ("NIGHT_WATER_FLOW", "likely_water_anomaly", None),
        ("BIN_OVERFLOW", "likely_bin_overflow", None),
        ("INEFFICIENT_ROOM_USE", "likely_inefficient_room_use", room_id),
        ("SENSOR_MISSING", "evidence_insufficient", room_id),
        ("SENSOR_STALE", "sensor_unavailable", room_id),
    ]
    for scenario, expected_event, required_room in cases:
        result = _run(account3_client, scenario, building_id, required_room)
        event_types = [account3_client.get(f"/api/v1/events/{event_id}").json()["event_type"] for event_id in result["event_ids"]]
        assert expected_event in event_types, (scenario, event_types)
        if scenario in {"SENSOR_MISSING", "SENSOR_STALE"}:
            assert "likely_energy_waste" not in event_types

    normal = _run(account3_client, "NORMAL_OPERATION", building_id, room_id)
    assert normal["event_ids"] == []


def test_duration_shorter_than_persistence_does_not_trigger_event(account3_client):
    building_id, room_id = _building_room(account3_client)
    result = _run(
        account3_client,
        "EMPTY_ROOM_HIGH_POWER",
        building_id,
        room_id,
        duration_virtual_seconds=60,
    )
    assert result["event_ids"] == []
    assert result["action_ids"] == []
    assert any("No event rule qualified" in x for x in result["warnings"])


def test_feedback_marks_false_positive_without_mutating_evidence_snapshot(account3_client):
    building_id, room_id = _building_room(account3_client)
    result = _run(account3_client, "EMPTY_ROOM_HIGH_POWER", building_id, room_id)
    event_id = result["event_ids"][0]
    before = account3_client.get(f"/api/v1/events/{event_id}").json()
    response = account3_client.post(f"/api/v1/events/{event_id}/feedback", json={
        "label": "FALSE_POSITIVE", "reason": "Manual inspection found occupancy sensor blocked.", "actor": "operator-test"
    })
    assert response.status_code == 201, response.text
    after = account3_client.get(f"/api/v1/events/{event_id}").json()
    assert after["status"] == "FALSE_POSITIVE"
    assert after["evidence_snapshot"] == before["evidence_snapshot"]
    assert account3_client.get("/api/v1/ledger").json() == []


def test_reject_and_invalid_transition_do_not_create_ledger(account3_client):
    building_id, room_id = _building_room(account3_client)
    result = _run(account3_client, "VERIFIED_RESPONSE", building_id, room_id)
    action_id = result["action_ids"][0]
    response = account3_client.post(
        f"/api/v1/actions/{action_id}/reject",
        headers={"Idempotency-Key": "reject-001"},
        json={"actor": "operator-test", "reason": "Room is needed for a scheduled event."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "REJECTED"
    assert account3_client.get("/api/v1/ledger").json() == []

    # A proposal cannot jump from PENDING_APPROVAL to ACKED.
    from app.core.dependencies import get_db
    from app.main import create_app
    # Transition validation is also exercised by Account 2's guarded repository.
    settings = account3_client.app.state.settings
    with account3_client.app.state.session_factory() as db:
        action = db.get(__import__("app.db.models", fromlist=["ActionRecord"]).ActionRecord, action_id)
        assert action.state == "REJECTED"
        with pytest.raises(DomainError):
            append_action_transition(db, action_id=action_id, new_state="ACKED", actor_or_source="test")


def test_reset_is_explicit_and_preserves_audit_ledger(account3_client):
    building_id, room_id = _building_room(account3_client)
    result = _run(account3_client, "VERIFIED_RESPONSE", building_id, room_id)
    action_id = result["action_ids"][0]
    success = account3_client.post(f"/api/v1/actions/{action_id}/approve", headers={"Idempotency-Key": "approve-before-reset"})
    assert success.json()["status"] == "VERIFIED_SUCCESS"
    before_ledger = account3_client.get("/api/v1/ledger").json()
    assert len(before_ledger) == 1

    denied = account3_client.post("/api/v1/scenarios/reset-demo", json={"confirm": False})
    assert denied.status_code == 422
    reset = account3_client.post("/api/v1/scenarios/reset-demo", json={"confirm": True, "actor": "operator-test", "reason": "Begin clean judge demo."})
    assert reset.status_code == 200, reset.text
    assert reset.json()["audit_history_preserved"] is True
    assert account3_client.get(f"/api/v1/actions/{action_id}").json()["status"] == "VERIFIED_SUCCESS"
    assert account3_client.get("/api/v1/ledger").json() == before_ledger


def test_invalid_outcome_combination_rejected_by_schema(account3_client):
    building_id, room_id = _building_room(account3_client)
    response = account3_client.post("/api/v1/scenarios/run", json={
        "scenario_type": "BIN_OVERFLOW", "building_id": building_id, "room_id": room_id,
        "outcome_mode": "SUCCESS",
    })
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_detection_recovers_after_stale_sensor_with_fresh_persistent_samples(account3_client):
    building_id, room_id = _building_room(account3_client)
    stale = _run(account3_client, "SENSOR_STALE", building_id, room_id)
    stale_types = [account3_client.get(f"/api/v1/events/{event_id}").json()["event_type"] for event_id in stale["event_ids"]]
    assert "sensor_unavailable" in stale_types

    # The same simulated sensors later recover. Historical STALE rows must not
    # permanently suppress a fresh, healthy, time-aligned detection.
    _run(account3_client, "EMPTY_ROOM_HIGH_POWER", building_id, room_id)
    evaluated = account3_client.post("/api/v1/events/evaluate", json={"building_id": building_id, "room_id": room_id})
    assert evaluated.status_code == 200, evaluated.text
    event_types = [event["event_type"] for event in evaluated.json()["events"]]
    assert "likely_energy_waste" in event_types


def test_manually_asserted_event_cannot_trigger_action_without_rule_evidence(account3_client):
    building_id, room_id = _building_room(account3_client)
    created = account3_client.post("/api/v1/events", json={
        "event_type": "likely_energy_waste",
        "severity": "HIGH",
        "building_id": building_id,
        "room_id": room_id,
        "trigger_rule": "operator-entered",
        "evidence_refs": [],
        "evidence_snapshot": {"explanation": "Manually entered; no machine-verified evidence."},
        "provenance": "SIMULATED",
    })
    assert created.status_code == 201, created.text
    proposal = account3_client.post("/api/v1/actions/proposals", json={
        "event_id": created.json()["id"],
        "idempotency_key": "proposal-from-manual-event",
        "actor": "operator-test",
        "outcome_mode": "SUCCESS",
    })
    assert proposal.status_code == 422
    assert proposal.json()["error"]["code"] == "RULE_EVIDENCE_REQUIRED"
