from pathlib import Path
from scripts.evaluate_scenarios import evaluate, isolated_client

def test_all_deterministic_scenarios_and_action_ledger_invariants():
    with isolated_client() as client:
        report = evaluate(client)
    assert report["report_type"] == "TEST-SCENARIO RESULTS"
    assert report["data_origin"] == "SYNTHETIC_SIMULATED_SCENARIOS"
    assert report["real_world_accuracy_claim"] is False
    assert report["real_campus_savings_claim"] is False
    assert report["status"] == "PASS"
    assert report["counts"] == {"PASS": 10, "FAIL": 0}
    cases = {row["scenario"]: row for row in report["scenarios"]}
    assert cases["SENSOR_MISSING"]["status"] == "PASS"
    assert cases["SENSOR_STALE"]["status"] == "PASS"
    assert cases["COMMAND_DROPPED"]["ledger_before"] == cases["COMMAND_DROPPED"]["ledger_after"]
    assert cases["ACKNOWLEDGED_IGNORED"]["ledger_before"] == cases["ACKNOWLEDGED_IGNORED"]["ledger_after"]
    assert cases["VERIFIED_RESPONSE"]["ledger_after"] == cases["VERIFIED_RESPONSE"]["ledger_before"] + 1
    assert "idempotent repeat held" in cases["VERIFIED_RESPONSE"]["action_result"]
