from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import make_engine
from app.main import create_app


@pytest.fixture
def client():
    settings = Settings(
        database_url="sqlite:///:memory:",
        api_prefix="/api/v1",
        allowed_origins=("http://localhost:5173", "http://127.0.0.1:5173"),
        virtual_time_multiplier=30,
    )
    engine = make_engine(settings.database_url)
    app = create_app(settings, engine=engine)
    with TestClient(app) as test_client:
        yield test_client


def test_merged_golden_flow_copilot_what_if_and_idempotent_verified_ledger(client):
    initial = client.get("/api/v1/ui/dashboard/overview")
    assert initial.status_code == 200
    assert initial.json()["kpis"]["energy"]["value"] is None

    scenario = client.post("/api/v1/ui/scenarios/run", json={"scenario": "empty_room_high_power"})
    assert scenario.status_code == 200, scenario.text
    assert scenario.json()["provenance"] == "SIMULATED"
    assert scenario.json()["actionId"]
    event_id = scenario.json()["createdEventIds"][0]

    events = client.get("/api/v1/ui/events")
    assert events.status_code == 200
    event = next(item for item in events.json() if item["id"] == event_id)
    assert event["eventType"] == "likely_energy_waste"
    assert event["provenance"] == "SIMULATED"
    assert event["evidence"]

    answer = client.post("/api/copilot/query", json={
        "question": "Why did this alert happen?",
        "event_ids": [event_id],
        "request_mode": "AUTO",
    })
    assert answer.status_code == 200, answer.text
    assert answer.json()["mode"] in {"TEMPLATE", "LLM", "CACHED"}
    assert "SIMULATED" in answer.json()["answer"]

    pending = next(item for item in client.get("/api/v1/ui/actions").json() if item["id"] == scenario.json()["actionId"])
    assert pending["state"] == "PENDING_APPROVAL"
    before_count = len(initial.json()["ledger"])
    approval_key = "integration-success-approval"
    approved = client.post(
        f"/api/v1/ui/actions/{pending['id']}/approve",
        headers={"Idempotency-Key": approval_key},
        json={},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "VERIFIED_SUCCESS"
    assert approved.json()["outcome"] == "VERIFIED_SUCCESS"

    replay = client.post(
        f"/api/v1/ui/actions/{pending['id']}/approve",
        headers={"Idempotency-Key": approval_key},
        json={},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["state"] == "VERIFIED_SUCCESS"
    overview = client.get("/api/v1/ui/dashboard/overview").json()
    assert len(overview["ledger"]) == before_count + 1

    building = client.get("/api/v1/ui/buildings").json()[0]
    room_id = building["rooms"][0]["id"]
    estimate = client.post("/api/v1/ui/what-if", json={
        "buildingId": building["id"],
        "roomId": room_id,
        "intervention": "REDUCE_POWER",
        "durationHours": 2,
        "reductionPercent": 20,
    })
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["status"] == "PROJECTED"
    assert estimate.json()["delta"] is not None
    assert estimate.json()["costDelta"] is None  # No tariff configured; do not invent one.

    export = client.get("/api/v1/ui/reports/export?format=csv")
    assert export.status_code == 200
    assert "record_type,id,status_or_type" in export.text


def test_failed_command_does_not_credit_impact_ledger(client):
    scenario = client.post("/api/v1/ui/scenarios/run", json={
        "scenario": "empty_room_high_power",
        "outcome": "COMMAND_DROPPED",
    })
    assert scenario.status_code == 200, scenario.text
    action_id = scenario.json()["actionId"]
    before = len(client.get("/api/v1/ui/dashboard/overview").json()["ledger"])

    response = client.post(
        f"/api/v1/ui/actions/{action_id}/approve",
        headers={"Idempotency-Key": "integration-dropped-command"},
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "ACK_TIMEOUT"
    after = len(client.get("/api/v1/ui/dashboard/overview").json()["ledger"])
    assert after == before


def test_camera_degrades_truthfully_without_local_model_and_manual_input_stays_simulated(client):
    health = client.get("/api/vision/health")
    assert health.status_code == 200
    if not health.json()["detector_available"]:
        assert health.json()["status"] == "UNAVAILABLE"

    simulated = client.post("/api/vision/simulated", json={
        "room_id": "CS-LAB-01",
        "person_count": 0,
        "coverage_confirmed": True,
        "camera_label": "Integration test manual input",
    })
    assert simulated.status_code == 200, simulated.text
    assert simulated.json()["provenance"] == "SIMULATED"
    assert simulated.json()["eligible_for_empty_timer"] is False


def test_no_build_fallback_ui_is_served_without_frontend_dependencies(client):
    response = client.get("/demo")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "CampusTwin AI" in response.text
    assert 'data-scenario="empty_room_high_power"' in response.text
    assert 'id="video-file"' in response.text
    assert "/api/v1/ui/scenarios/run" in response.text
    assert "/api/v1/ui/actions/" in response.text
