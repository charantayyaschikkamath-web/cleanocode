from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.copilot.facts import get_facts_snapshot
from app.copilot.router import get_copilot_service, router as copilot_router
from app.copilot.config import CopilotSettings
from app.copilot.service import CopilotService
from app.what_if.router import router as what_if_router
from app.copilot.models import FactsSnapshot


def test_router_health_and_exports_are_wired(facts, tmp_path):
    app = FastAPI()
    app.include_router(copilot_router)
    app.include_router(what_if_router)
    settings = CopilotSettings(api_base_url=None, api_key=None, model=None, cache_path=str(tmp_path / "cache.json"))
    app.dependency_overrides[get_facts_snapshot] = lambda: facts
    app.dependency_overrides[get_copilot_service] = lambda: CopilotService(settings=settings)
    client = TestClient(app)

    answer = client.post("/api/copilot/ask", json={"question": "Explain the event", "event_id": "event-energy-1"})
    assert answer.status_code == 200
    assert answer.json()["mode"] == "TEMPLATE"

    report = client.get("/api/copilot/reports/weekly")
    assert report.status_code == 200
    assert report.json()["metrics"]["reading_count"] == 1

    csv_export = client.get("/api/copilot/reports/weekly/export?format=csv")
    assert csv_export.status_code == 200
    assert "text/csv" in csv_export.headers["content-type"]
    assert "verified_simulated.energy_kwh" in csv_export.text

    html_export = client.get("/api/copilot/reports/weekly/export?format=html")
    assert html_export.status_code == 200
    assert "Verified simulated" in html_export.text

    what_if = client.post("/api/what-if/run", json={
        "room_id": "B1-R101", "duration_hours": 2, "scenario_baseline_watts": 1000,
        "intervention_name": "Moderate reduction", "reduction_percent": 25,
    })
    assert what_if.status_code == 200
    payload = what_if.json()
    assert payload["comparisons"][0]["projected_avoided_energy_kwh"] == "0.500000"
    assert payload["comparisons"][0]["impact_status"] == "PROJECTED_NOT_VERIFIED"


def test_contract_copilot_query_scopes_evidence_and_reports_version_mismatch(facts, tmp_path):
    from app.copilot.router import get_copilot_service
    from app.copilot.config import CopilotSettings
    from app.copilot.service import CopilotService

    app = FastAPI()
    app.include_router(copilot_router)
    app.include_router(what_if_router)
    app.dependency_overrides[get_facts_snapshot] = lambda: facts
    settings = CopilotSettings(api_base_url=None, api_key=None, model=None, cache_path=str(tmp_path / "cache.json"))
    app.dependency_overrides[get_copilot_service] = lambda: CopilotService(settings=settings)
    client = TestClient(app)

    response = client.post("/api/copilot/query", json={
        "question": "Why did this event happen?",
        "event_ids": ["event-energy-1", "event-does-not-exist"],
        "facts_version": "old-snapshot",
        "request_mode": "TEMPLATE",
    })
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"answer", "mode", "facts_version", "source_ids", "recommendations", "warnings", "generated_at"}
    assert payload["facts_version"] == "snap-test"
    assert payload["mode"] == "TEMPLATE"
    assert "event-energy-1" in payload["source_ids"]
    assert "reading-power-1" in payload["source_ids"]
    assert any("old-snapshot" in warning for warning in payload["warnings"])
    assert any("event-does-not-exist" in warning for warning in payload["warnings"])


def test_contract_report_artifacts_persist_metadata_and_all_download_formats(facts, tmp_path):
    from app.copilot.config import CopilotSettings
    from app.copilot.router import get_copilot_service, get_report_store, reports_router
    from app.copilot.report_store import ReportStore
    from app.copilot.service import CopilotService

    app = FastAPI()
    app.include_router(copilot_router)
    app.include_router(reports_router)
    app.dependency_overrides[get_facts_snapshot] = lambda: facts
    settings = CopilotSettings(api_base_url=None, api_key=None, model=None, cache_path=str(tmp_path / "cache.json"))
    app.dependency_overrides[get_copilot_service] = lambda: CopilotService(settings=settings)
    app.dependency_overrides[get_report_store] = lambda: ReportStore(tmp_path / "persisted-reports")
    client = TestClient(app)

    created = client.post("/api/reports", json={"report_type": "WEEKLY_SUSTAINABILITY", "format": "CSV"})
    assert created.status_code == 201, created.text
    metadata = created.json()
    assert metadata["id"].startswith("report-")
    assert metadata["format"] == "CSV"
    assert metadata["file_reference"] == f"/api/reports/{metadata['id']}/download"
    assert set(metadata["source_event_ids"]) == {"event-energy-1"}
    assert metadata["provenance_summary"]["SIMULATED"] > 0
    assert not str(tmp_path) in created.text

    detail = client.get(f"/api/reports/{metadata['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == metadata["id"]

    json_file = client.get(f"/api/reports/{metadata['id']}/download?format=JSON")
    assert json_file.status_code == 200
    assert json_file.json()["report_id"] == metadata["id"]

    csv_file = client.get(f"/api/reports/{metadata['id']}/download?format=CSV")
    assert csv_file.status_code == 200
    assert "verified_simulated.energy_kwh" in csv_file.text
    assert "reading-power-1.value" in csv_file.text
    assert "action-failed-1.status" in csv_file.text
    assert "ledger-failed-1.verification_status" in csv_file.text

    html_file = client.get(f"/api/reports/{metadata['id']}/download?format=HTML")
    assert html_file.status_code == 200
    assert "Verified vs simulated" in html_file.text
    assert "Sensor evidence register" in html_file.text
    assert "action-failed-1" in html_file.text

    traversal = client.get("/api/reports/../../etc/passwd")
    assert traversal.status_code in (404, 405)


def test_report_create_respects_explicit_period_start_and_end(facts, tmp_path):
    from app.copilot.config import CopilotSettings
    from app.copilot.router import get_copilot_service, get_report_store, reports_router, router as copilot_router
    from app.copilot.report_store import ReportStore
    from app.copilot.service import CopilotService

    app = FastAPI()
    app.include_router(copilot_router)
    app.include_router(reports_router)
    app.dependency_overrides[get_facts_snapshot] = lambda: facts
    settings = CopilotSettings(api_base_url=None, api_key=None, model=None, cache_path=str(tmp_path / "cache.json"))
    app.dependency_overrides[get_copilot_service] = lambda: CopilotService(settings=settings)
    app.dependency_overrides[get_report_store] = lambda: ReportStore(tmp_path / "reports")
    client = TestClient(app)

    period_start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    period_end = datetime(2024, 1, 8, tzinfo=timezone.utc)
    response = client.post("/api/reports", json={
        "report_type": "WEEKLY_SUSTAINABILITY",
        "format": "JSON",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    })
    assert response.status_code == 201, response.text
    metadata = response.json()
    assert datetime.fromisoformat(metadata["period_start"].replace("Z", "+00:00")) == period_start
    assert datetime.fromisoformat(metadata["period_end"].replace("Z", "+00:00")) == period_end
    assert metadata["source_event_ids"] == []


def test_contract_action_plan_export_includes_impact_status_and_unavailable_values(facts, tmp_path):
    from app.copilot.router import get_copilot_service
    from app.copilot.config import CopilotSettings
    from app.copilot.service import CopilotService

    app = FastAPI()
    app.include_router(copilot_router)
    app.dependency_overrides[get_facts_snapshot] = lambda: facts
    settings = CopilotSettings(api_base_url=None, api_key=None, model=None, cache_path=str(tmp_path / "cache.json"))
    app.dependency_overrides[get_copilot_service] = lambda: CopilotService(settings=settings)
    client = TestClient(app)

    csv_response = client.get("/api/copilot/reports/action-plan/export?format=csv")
    assert csv_response.status_code == 200
    assert "impact_status" in csv_response.text
    assert "UNAVAILABLE" in csv_response.text
    html_response = client.get("/api/copilot/reports/action-plan/export?format=html")
    assert html_response.status_code == 200
    assert "Impact status" in html_response.text
