#!/usr/bin/env python3
"""Verify real API workflow and SQLite persistence across a full backend restart.

Run from the repository root with the backend dependencies installed:
    python scripts/verify_persistence_restart.py

The script uses a temporary SQLite database and loopback port, then removes its
artifacts. It does not touch the configured user/demo database.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(report_path: Path) -> int:
    results: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "LOCAL RELEASE CHECK; synthetic scenario inputs only",
        "checks": [],
    }
    checks: list[dict[str, Any]] = results["checks"]

    def record(name: str, detail: str) -> None:
        checks.append({"name": name, "status": "PASS", "detail": detail})

    try:
        with tempfile.TemporaryDirectory(prefix="campustwin-release-check-") as temporary:
            temp = Path(temporary)
            db_path = (temp / "release-check.db").resolve()
            port = free_loopback_port()
            base_url = f"http://127.0.0.1:{port}"
            log_path = temp / "backend.log"
            log_handle = log_path.open("w", encoding="utf-8")
            env = os.environ.copy()
            pythonpath = str(ROOT / "backend")
            if env.get("PYTHONPATH"):
                pythonpath += os.pathsep + env["PYTHONPATH"]
            env["PYTHONPATH"] = pythonpath
            env["CAMPUS_TWIN_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
            env.setdefault("CAMPUS_TWIN_LOG_LEVEL", "WARNING")
            command = [
                sys.executable, "-m", "uvicorn", "app.main:app",
                "--app-dir", str(ROOT / "backend"),
                "--host", "127.0.0.1", "--port", str(port),
                "--log-level", "warning",
            ]
            process: subprocess.Popen[str] | None = None

            def start() -> httpx.Client:
                nonlocal process
                process = subprocess.Popen(
                    command, cwd=ROOT, env=env, stdout=log_handle,
                    stderr=subprocess.STDOUT, text=True,
                )
                client = httpx.Client(base_url=base_url, timeout=8.0)
                deadline = time.monotonic() + 25.0
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        client.close()
                        raise RuntimeError(f"Backend exited at startup with code {process.returncode}.")
                    try:
                        response = client.get("/api/v1/health")
                        if response.status_code == 200:
                            return client
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.25)
                client.close()
                raise TimeoutError("Backend health endpoint did not become ready within 25 seconds.")

            def stop() -> None:
                nonlocal process
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                process = None

            client: httpx.Client | None = None
            try:
                client = start()
                check(client.get("/api/v1/ui/dashboard/overview").status_code == 200, "Overview endpoint failed.")
                demo_page = client.get("/demo")
                check(demo_page.status_code == 200 and "text/html" in demo_page.headers.get("content-type", ""), "No-build demo page did not serve valid HTML.")
                check('data-scenario="empty_room_high_power"' in demo_page.text and 'id="video-file"' in demo_page.text, "No-build demo is missing its core scenario or video input controls.")
                record("backend_start_1", "Backend started; dashboard API returned HTTP 200 and /demo served the dependency-free HTML UI.")

                first = client.post("/api/v1/ui/scenarios/run", json={"scenario": "empty_room_high_power"})
                check(first.status_code == 200, f"Success scenario failed: HTTP {first.status_code}.")
                first_body = first.json()
                success_action_id = first_body["actionId"]
                success_event_id = first_body["createdEventIds"][0]
                approval = client.post(
                    f"/api/v1/ui/actions/{success_action_id}/approve",
                    headers={"Idempotency-Key": "release-restart-verified-success"}, json={},
                )
                check(approval.status_code == 200 and approval.json().get("state") == "VERIFIED_SUCCESS",
                      f"Successful action did not independently verify: {approval.text[:400]}.")
                ledger_after_success = client.get("/api/v1/ui/dashboard/overview").json()["ledger"]
                check(len(ledger_after_success) == 1, "Verified success should create exactly one ledger entry.")
                record("verified_success", "Energy-waste scenario was approved, independently verified, and created exactly one simulated ledger entry.")

                second = client.post(
                    "/api/v1/ui/scenarios/run",
                    json={"scenario": "empty_room_high_power", "outcome": "COMMAND_DROPPED"},
                )
                check(second.status_code == 200, f"Dropped-command scenario failed: HTTP {second.status_code}.")
                second_body = second.json()
                failed_action_id = second_body["actionId"]
                failed_event_id = second_body["createdEventIds"][0]
                failed_approval = client.post(
                    f"/api/v1/ui/actions/{failed_action_id}/approve",
                    headers={"Idempotency-Key": "release-restart-command-dropped"}, json={},
                )
                check(failed_approval.status_code == 200 and failed_approval.json().get("state") == "ACK_TIMEOUT",
                      f"Dropped command did not reach ACK_TIMEOUT: {failed_approval.text[:400]}.")
                ledger_after_failure = client.get("/api/v1/ui/dashboard/overview").json()["ledger"]
                check(len(ledger_after_failure) == 1, "Dropped command incorrectly changed the ledger.")
                record("failed_action_no_savings", "Dropped command reached ACK_TIMEOUT and did not change the ledger.")
                client.close()
                client = None
                stop()
                record("backend_stop", "First backend process terminated before restart.")

                client = start()
                after = client.get("/api/v1/ui/dashboard/overview")
                check(after.status_code == 200, "Dashboard failed after backend restart.")
                ledger_after_restart = after.json()["ledger"]
                events_response = client.get("/api/v1/ui/events")
                actions_response = client.get("/api/v1/ui/actions")
                check(events_response.status_code == 200 and actions_response.status_code == 200,
                      "Events/actions endpoints failed after restart.")
                events = {item["id"] for item in events_response.json()}
                actions = {item["id"]: item for item in actions_response.json()}
                check({success_event_id, failed_event_id}.issubset(events), "Scenario events did not persist after restart.")
                check(actions.get(success_action_id, {}).get("state") == "VERIFIED_SUCCESS",
                      "Verified action state did not persist after restart.")
                check(actions.get(failed_action_id, {}).get("state") == "ACK_TIMEOUT",
                      "Failed action state did not persist after restart.")
                check(len(ledger_after_restart) == 1, "Ledger count changed across restart or was not persisted.")
                record("persistence_after_restart", f"Both events and actions persisted; ledger remained at one entry (events={len(events)}, actions={len(actions)}, ledger={len(ledger_after_restart)}).")
                results.update({
                    "status": "PASS",
                    "database": "temporary SQLite database; removed after test",
                    "backend_restarts": 1,
                    "persisted_events": len(events),
                    "persisted_actions": len(actions),
                    "ledger_entries": len(ledger_after_restart),
                })
            finally:
                if client is not None:
                    client.close()
                stop()
                log_handle.close()
                if not results.get("status"):
                    results["backend_log_tail"] = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
    except Exception as exc:  # Include truthful failure evidence for CI/local use.
        results["status"] = "FAIL"
        results["error"] = f"{type(exc).__name__}: {exc}"
        checks.append({"name": "release_restart_check", "status": "FAIL", "detail": results["error"]})

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"JSON report: {report_path}")
    return 0 if results.get("status") == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json-out", type=Path,
        default=ROOT / "artifacts" / "quality" / "persistence-restart-current.json",
        help="Path for the fresh machine-readable report.",
    )
    args = parser.parse_args()
    report_path = args.json_out if args.json_out.is_absolute() else ROOT / args.json_out
    return run(report_path.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
