#!/usr/bin/env python3
"""Run deterministic CampusTwin scenarios and verify action/ledger invariants.

The default mode uses an isolated in-memory database and never touches a user's
persistent application data. Live mode performs writes and therefore requires
both --base-url and --allow-live-writes.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

EXPECTED_EVENTS = {
    "EMPTY_ROOM_HIGH_POWER": "likely_energy_waste",
    "NIGHT_WATER_FLOW": "likely_water_anomaly",
    "BIN_OVERFLOW": "likely_bin_overflow",
    "INEFFICIENT_ROOM_USE": "likely_inefficient_room_use",
    "NORMAL_OPERATION": None,
    "SENSOR_MISSING": "evidence_insufficient",
    "SENSOR_STALE": "sensor_unavailable",
    "COMMAND_DROPPED": "likely_energy_waste",
    "ACKNOWLEDGED_IGNORED": "likely_energy_waste",
    "VERIFIED_RESPONSE": "likely_energy_waste",
}
UNKNOWN_SCENARIOS = {"SENSOR_MISSING", "SENSOR_STALE"}
ACTION_EXPECTATIONS = {
    "VERIFIED_RESPONSE": "VERIFIED_SUCCESS",
    "COMMAND_DROPPED": "ACK_TIMEOUT",
    "ACKNOWLEDGED_IGNORED": "VERIFICATION_FAILED",
}


class ApiFailure(RuntimeError):
    pass


class LiveResponse:
    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self.text = body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text) if self.text else None


class LiveApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, *, payload: dict | None = None, headers: dict | None = None, params: dict | None = None):
        url = self.base_url + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = {"Accept": "application/json"}
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return LiveResponse(response.status, response.read())
        except urllib.error.HTTPError as exc:
            return LiveResponse(exc.code, exc.read())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ApiFailure(f"{method} {path} failed: {type(exc).__name__}") from exc

    def get(self, path: str, params: dict | None = None):
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None, headers: dict | None = None):
        return self._request("POST", path, payload=json, headers=headers)


@contextmanager
def isolated_client():
    """Create a clean test app and an in-memory SQLite DB for the scenario run."""
    old = os.environ.get("CAMPUS_TWIN_DATABASE_URL")
    old_disable = logging.root.manager.disable
    logging.disable(logging.INFO)
    # app.main exports a default `app` on import; keep that import isolated from
    # any persistent database configured in the caller's shell.
    os.environ["CAMPUS_TWIN_DATABASE_URL"] = "sqlite://"
    try:
        from fastapi.testclient import TestClient
        from app.core.config import Settings
        from app.db.session import make_engine
        from app.main import create_app
        from app.routers.actions import router as actions_router
        from app.routers.scenarios import router as scenarios_router

        settings = Settings(
            database_url="sqlite://",
            api_prefix="/api/v1",
            virtual_time_multiplier=30,
            allowed_origins=("http://localhost:5173",),
            tariff_per_kwh=None,
            co2_factor_kg_per_kwh=None,
        )
        engine = make_engine("sqlite://")
        app = create_app(settings=settings, engine=engine)
        app.include_router(actions_router, prefix=settings.api_prefix)
        app.include_router(scenarios_router, prefix=settings.api_prefix)
        with TestClient(app) as client:
            yield client
        engine.dispose()
    finally:
        if old is None:
            os.environ.pop("CAMPUS_TWIN_DATABASE_URL", None)
        else:
            os.environ["CAMPUS_TWIN_DATABASE_URL"] = old
        logging.disable(old_disable)


def _assert(response, expected_status: int, action: str) -> dict:
    if response.status_code != expected_status:
        raise ApiFailure(f"{action}: expected HTTP {expected_status}, got {response.status_code}: {response.text[:500]}")
    data = response.json()
    if not isinstance(data, dict):
        raise ApiFailure(f"{action}: expected a JSON object, got {type(data).__name__}")
    return data


def _get_ledger_count(client, prefix: str) -> int:
    response = client.get(f"{prefix}/ledger")
    if response.status_code != 200:
        raise ApiFailure(f"GET {prefix}/ledger: HTTP {response.status_code}: {response.text[:400]}")
    body = response.json()
    if not isinstance(body, list):
        raise ApiFailure(f"GET {prefix}/ledger: expected a list")
    return len(body)


def evaluate(client, *, prefix: str = "/api/v1", live: bool = False) -> dict:
    started = datetime.now(timezone.utc)
    run_id = uuid.uuid4().hex[:10]
    building_response = client.post(f"{prefix}/buildings", json={"name": f"QA Evaluation Block {run_id}", "code": f"QA-{run_id}"})
    building = _assert(building_response, 201, "create disposable evaluation building")
    building_id = building["id"]
    room_response = client.post(f"{prefix}/rooms", json={"building_id": building_id, "name": "QA Lab 101", "capacity": 40})
    room = _assert(room_response, 201, "create disposable evaluation room")
    room_id = room["id"]

    scenarios_response = client.get(f"{prefix}/scenarios")
    supported = set()
    if scenarios_response.status_code == 200:
        payload = scenarios_response.json()
        supported = {item.get("scenario_type") for item in payload.get("scenarios", []) if isinstance(item, dict)}
    else:
        supported = set(EXPECTED_EVENTS)

    rows: list[dict[str, Any]] = []
    action_checks: dict[str, dict[str, Any]] = {}
    for scenario_name, expected_event in EXPECTED_EVENTS.items():
        row: dict[str, Any] = {
            "scenario": scenario_name,
            "expected_detection": expected_event or "no event",
            "actual_detection": None,
            "provenance": None,
            "unknown_handling": "NOT_APPLICABLE",
            "action_result": None,
            "ledger_before": None,
            "ledger_after": None,
            "status": "FAIL",
            "error": None,
        }
        try:
            if supported and scenario_name not in supported:
                raise ApiFailure(f"Scenario is not advertised by GET {prefix}/scenarios.")
            before_count = _get_ledger_count(client, prefix)
            row["ledger_before"] = before_count
            body = _assert(client.post(f"{prefix}/scenarios/run", json={
                "scenario_type": scenario_name,
                "building_id": building_id,
                "room_id": room_id,
                "duration_virtual_seconds": 900,
                "seed": 42,
            }), 201, f"run scenario {scenario_name}")
            detections = body.get("detection_summary", [])
            actual_types = [str(item.get("event_type")) for item in detections if isinstance(item, dict) and item.get("event_type")]
            row["actual_detection"] = actual_types or "no event"
            row["provenance"] = body.get("provenance")
            if body.get("status") != "COMPLETED":
                raise ApiFailure(f"Scenario status was {body.get('status')!r}, expected COMPLETED.")
            if body.get("provenance") != "SIMULATED":
                raise ApiFailure(f"Scenario provenance was {body.get('provenance')!r}, expected SIMULATED.")
            expected_match = (not actual_types) if expected_event is None else (expected_event in actual_types)
            if not expected_match:
                raise ApiFailure(f"Expected event {expected_event!r}; observed {actual_types!r}.")
            # Follow evidence links for any emitted events. No event should cite non-simulated
            # sensor values inside these deterministic synthetic scenarios.
            for event_id in body.get("event_ids", []):
                evidence_resp = client.get(f"{prefix}/events/{event_id}/evidence")
                evidence = _assert(evidence_resp, 200, f"retrieve evidence for {scenario_name}")
                readings = evidence.get("readings", [])
                if any(reading.get("provenance") != "SIMULATED" for reading in readings):
                    raise ApiFailure(f"{scenario_name} returned evidence not marked SIMULATED.")
            if scenario_name in UNKNOWN_SCENARIOS:
                # A bad/stale source must not silently become a likely-energy-waste event.
                if "likely_energy_waste" in actual_types:
                    raise ApiFailure("Unknown/stale evidence was incorrectly promoted to likely_energy_waste.")
                row["unknown_handling"] = "PASS: unavailable/insufficient event surfaced; no energy-waste claim"
            else:
                row["unknown_handling"] = "PASS" if scenario_name != "NORMAL_OPERATION" else "PASS: normal operation did not emit an event"

            if scenario_name in ACTION_EXPECTATIONS:
                action_ids = body.get("action_ids", [])
                if len(action_ids) != 1:
                    raise ApiFailure(f"Expected one pending action for {scenario_name}; got {len(action_ids)}.")
                action_id = action_ids[0]
                key = f"qa-{run_id}-{scenario_name.lower()}"
                approved = _assert(client.post(
                    f"{prefix}/actions/{action_id}/approve",
                    headers={"Idempotency-Key": key},
                ), 200, f"approve action for {scenario_name}")
                expected_action = ACTION_EXPECTATIONS[scenario_name]
                actual_action = approved.get("status")
                row["action_result"] = actual_action
                if actual_action != expected_action:
                    raise ApiFailure(f"Expected action result {expected_action!r}; got {actual_action!r}.")
                after_count = _get_ledger_count(client, prefix)
                row["ledger_after"] = after_count
                if scenario_name == "VERIFIED_RESPONSE":
                    if not approved.get("ledger_entry") or approved["ledger_entry"].get("status") != "VERIFIED_SIMULATED":
                        raise ApiFailure("VERIFIED_SUCCESS did not return a VERIFIED_SIMULATED ledger entry.")
                    if after_count != before_count + 1:
                        raise ApiFailure(f"Successful verification should add exactly one ledger row ({before_count} -> {after_count}).")
                    # Repeated approval with the same idempotency key must not double count.
                    repeated = _assert(client.post(
                        f"{prefix}/actions/{action_id}/approve",
                        headers={"Idempotency-Key": key},
                    ), 200, f"repeat approval for {scenario_name}")
                    repeated_count = _get_ledger_count(client, prefix)
                    if repeated.get("status") != expected_action or repeated_count != after_count:
                        raise ApiFailure("Repeated approval changed the terminal action/ledger result.")
                    row["action_result"] = f"{actual_action}; idempotent repeat held"
                else:
                    if approved.get("ledger_entry") is not None:
                        raise ApiFailure("A failed/ignored action returned a savings ledger entry.")
                    if after_count != before_count:
                        raise ApiFailure(f"Failed action must leave ledger count unchanged ({before_count} -> {after_count}).")
            else:
                row["ledger_after"] = _get_ledger_count(client, prefix)
            row["status"] = "PASS"
        except Exception as exc:  # preserve a full scenario report instead of stopping at first failure
            row["error"] = f"{type(exc).__name__}: {str(exc)[:700]}"
            try:
                if row["ledger_after"] is None:
                    row["ledger_after"] = _get_ledger_count(client, prefix)
            except Exception:
                pass
        rows.append(row)

    ended = datetime.now(timezone.utc)
    counts = {status: sum(1 for row in rows if row["status"] == status) for status in ("PASS", "FAIL")}
    return {
        "report_type": "TEST-SCENARIO RESULTS",
        "schema_version": "1.0",
        "generated_at": ended.isoformat().replace("+00:00", "Z"),
        "duration_seconds": round((ended - started).total_seconds(), 3),
        "execution_mode": "LIVE_API_WRITE_TEST" if live else "ISOLATED_IN_PROCESS_TEST",
        "data_origin": "SYNTHETIC_SIMULATED_SCENARIOS",
        "real_world_accuracy_claim": False,
        "real_campus_savings_claim": False,
        "scope_note": "These synthetic scenarios validate the API workflow and invariants only. They do not measure real-campus detector accuracy, hardware control, production reliability, or real savings.",
        "fixture": {"building_id": building_id, "room_id": room_id, "records_persist_to_production_db": bool(live)},
        "counts": counts,
        "status": "PASS" if counts["FAIL"] == 0 and counts["PASS"] == len(rows) else "FAIL",
        "scenarios": rows,
    }


def write_reports(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "scenario-evaluation.json"
    md_path = output_dir / "scenario-evaluation.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# TEST-SCENARIO RESULTS",
        "",
        f"- **Status:** {report['status']}",
        f"- **Execution mode:** {report['execution_mode']}",
        f"- **Generated:** {report['generated_at']}",
        f"- **Duration:** {report['duration_seconds']} seconds",
        f"- **Passed:** {report['counts']['PASS']} / {sum(report['counts'].values())}",
        f"- **Scope:** {report['scope_note']}",
        "",
        "| Scenario | Expected | Actual | Provenance | Action result | Ledger before → after | Result |",
        "|---|---|---|---|---|---:|---|",
    ]
    for row in report["scenarios"]:
        actual = row.get("actual_detection")
        if isinstance(actual, list):
            actual = ", ".join(actual) if actual else "no event"
        lines.append("| {scenario} | {expected} | {actual} | {provenance} | {action} | {before} → {after} | {status} |".format(
            scenario=row["scenario"], expected=row["expected_detection"], actual=actual or "—",
            provenance=row.get("provenance") or "—", action=row.get("action_result") or "—",
            before=row.get("ledger_before") if row.get("ledger_before") is not None else "—",
            after=row.get("ledger_after") if row.get("ledger_after") is not None else "—", status=row["status"],
        ))
        if row.get("error"):
            lines.extend(["", f"**{row['scenario']} error:** `{row['error']}`"])
    lines.extend(["", "## Interpretation", "", report["scope_note"], ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Run against an already-running API; use only with --allow-live-writes")
    parser.add_argument("--allow-live-writes", action="store_true", help="Acknowledge that live evaluation writes buildings, rooms, events, actions and possibly one simulated ledger entry")
    parser.add_argument("--api-prefix", default=os.environ.get("CAMPUS_TWIN_API_PREFIX", "/api/v1"))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "quality")
    args = parser.parse_args()
    prefix = "/" + args.api_prefix.strip("/")
    if args.base_url and not args.allow_live_writes:
        parser.error("Live scenario evaluation mutates data. Add --allow-live-writes only on a dedicated demo/test database.")
    try:
        if args.base_url:
            client = LiveApiClient(args.base_url)
            report = evaluate(client, prefix=prefix, live=True)
        else:
            with isolated_client() as client:
                report = evaluate(client, prefix=prefix, live=False)
        json_path, md_path = write_reports(report, args.output_dir.resolve())
    except Exception as exc:
        print(f"EVALUATION SETUP FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"CampusTwin AI — {report['report_type']}")
    print(f"Mode: {report['execution_mode']} | Status: {report['status']} | PASS {report['counts']['PASS']} / FAIL {report['counts']['FAIL']}")
    for row in report["scenarios"]:
        actual = row.get("actual_detection")
        if isinstance(actual, list):
            actual = ", ".join(actual) if actual else "no event"
        print(f"[{row['status']:<4}] {row['scenario']:<24} detection={actual or '—'} action={row.get('action_result') or '—'} ledger={row.get('ledger_before')}→{row.get('ledger_after')}")
        if row.get("error"):
            print(f"       {row['error']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    print("Synthetic test results only; not evidence of real-world accuracy or campus savings.")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
