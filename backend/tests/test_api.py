from __future__ import annotations

from datetime import datetime, timezone


def _building(client) -> str:
    response = client.post("/api/v1/buildings", json={"name": "Engineering Block", "code": "ENG-1"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_health_preflight_and_root(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["database"] == "healthy"
    assert health.headers.get("x-request-id")

    preflight = client.get("/api/v1/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["status"] == "WARN"  # Optional factors are intentionally unset.
    assert any(check["name"] == "database" and check["status"] == "PASS" for check in preflight.json()["checks"])

    assert client.get("/").status_code == 200


def test_building_room_and_reading_persist_and_idempotency(client):
    building_id = _building(client)
    room_response = client.post("/api/v1/rooms", json={
        "building_id": building_id,
        "name": "Lab 204",
        "code": "204",
        "capacity": 36,
    })
    assert room_response.status_code == 201, room_response.text
    room_id = room_response.json()["id"]

    reading = {
        "idempotency_key": "reading-demo-001",
        "sensor_id": "meter-204",
        "source_type": "power_meter",
        "resource_type": "energy",
        "building_id": building_id,
        "room_id": room_id,
        "value": "1000",
        "unit": "W",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source_status": "HEALTHY",
        "freshness_seconds": 0,
        "provenance": "SIMULATED",
        "metadata": {"scenario": "test"},
    }
    first = client.post("/api/v1/readings", json=reading)
    second = client.post("/api/v1/readings", json=reading)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]

    changed = {**reading, "value": "1500"}
    conflict = client.post("/api/v1/readings", json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    listed = client.get("/api/v1/readings", params={"building_id": building_id, "resource_type": "energy"})
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["provenance"] == "SIMULATED"


def test_reading_rejects_room_from_different_building(client):
    building_a = _building(client)
    building_b = client.post("/api/v1/buildings", json={"name": "Science Block", "code": "SCI-1"}).json()["id"]
    room_id = client.post("/api/v1/rooms", json={"building_id": building_a, "name": "Room A"}).json()["id"]
    reading = {
        "source_type": "power_meter",
        "resource_type": "energy",
        "building_id": building_b,
        "room_id": room_id,
        "value": 50,
        "unit": "W",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "provenance": "SIMULATED",
    }
    response = client.post("/api/v1/readings", json=reading)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ROOM_BUILDING_MISMATCH"


def test_event_evidence_is_persisted_and_facts_do_not_invent_savings(client):
    building_id = _building(client)
    observed = datetime.now(timezone.utc).isoformat()
    reading = client.post("/api/v1/readings", json={
        "source_type": "power_meter",
        "resource_type": "energy",
        "building_id": building_id,
        "value": 1000,
        "unit": "W",
        "observed_at": observed,
        "provenance": "SIMULATED",
    }).json()

    event_response = client.post("/api/v1/events", json={
        "event_type": "likely_energy_waste",
        "severity": "HIGH",
        "building_id": building_id,
        "trigger_rule": "empty_room_power_over_threshold",
        "first_seen_at": observed,
        "evidence_refs": [reading["id"]],
        "evidence_snapshot": {"reading_id": reading["id"], "value": "1000", "unit": "W"},
        "provenance": "SIMULATED",
    })
    assert event_response.status_code == 201, event_response.text
    assert event_response.json()["status"] == "OPEN"
    assert event_response.json()["evidence_snapshot"]["value"] == "1000"

    facts_response = client.get("/api/v1/facts/overview")
    assert facts_response.status_code == 200, facts_response.text
    facts = facts_response.json()
    assert facts["open_events"]["value"] == 1
    assert facts["latest_readings"][0]["provenance"] == "SIMULATED"
    assert facts["verified_energy_saved_kwh"]["value"] is None
    assert facts["verified_energy_saved_kwh"]["availability"] == "UNAVAILABLE"


def test_energy_impact_endpoint_keeps_unknown_factors_unavailable(client):
    response = client.post("/api/v1/impact/energy", json={"power_watts": "1000", "duration_virtual_seconds": "600"})
    assert response.status_code == 200
    body = response.json()
    assert body["energy_kwh"] == "0.1666667"
    assert body["estimated_cost"] is None
    assert body["estimated_co2_kg"] is None
    assert "PROJECTED" not in body["status"]


def test_naive_timestamps_are_rejected_and_ledger_has_no_public_write_route(client):
    building_id = _building(client)
    reading = client.post("/api/v1/readings", json={
        "source_type": "power_meter",
        "resource_type": "energy",
        "building_id": building_id,
        "value": 20,
        "unit": "W",
        "observed_at": "2026-10-15T12:00:00",
        "provenance": "SIMULATED",
    })
    assert reading.status_code == 422
    assert reading.json()["error"]["code"] == "VALIDATION_ERROR"

    assert client.get("/api/v1/ledger").json() == []
    assert client.post("/api/v1/ledger", json={"energy_kwh": 999}).status_code == 405


def test_ledger_read_api_returns_only_persisted_verified_entries(client, db_session):
    from decimal import Decimal

    from app.repositories import append_action_transition, create_action_record, create_building, create_event, record_verified_savings
    from app.schemas import BuildingCreate, EventCreate

    building = create_building(db_session, BuildingCreate(name="Ledger API Block"))
    event = create_event(db_session, EventCreate(
        event_type="likely_energy_waste",
        severity="HIGH",
        building_id=building.id,
        trigger_rule="power_above_threshold",
        first_seen_at=datetime.now(timezone.utc),
        evidence_snapshot={"origin": "TEST-SCENARIO"},
        provenance="SIMULATED",
    ))
    action = create_action_record(
        db_session,
        event_id=event.id,
        idempotency_key="ledger-api-action",
        action_type="reduce_simulated_power",
    )
    for state in ("COMMAND_SENT", "ACKED", "VERIFYING", "VERIFIED_SUCCESS"):
        transition = append_action_transition(db_session, action_id=action.id, new_state=state, actor_or_source="test")
    record_verified_savings(
        db_session,
        action_id=action.id,
        resource_type="energy",
        unit="kWh",
        calculation_version="energy-impact-v1",
        verification_transition_id=transition.id,
        status="VERIFIED_SIMULATED",
        energy_kwh=Decimal("0.1666667"),
        calculation_inputs={"power_watts": "1000", "duration_virtual_seconds": "600"},
        assumptions=["TEST-SCENARIO only"],
    )

    response = client.get("/api/v1/ledger", params={"resource_type": "energy"})
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    row = response.json()[0]
    assert row["status"] == "VERIFIED_SIMULATED"
    assert row["energy_kwh"] == "0.1666667"
    assert row["calculation_inputs"]["duration_virtual_seconds"] == "600"
    assert row["verification_transition_id"] == transition.id
