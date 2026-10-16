from pathlib import Path

from scripts.preflight import Check, collect_checks, parse_env_file, route_registration_checks

ROOT = Path(__file__).resolve().parents[2]

def test_env_parser_keeps_values_after_equals_and_ignores_comments(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nEMPTY=\nCOPILOT_API_BASE_URL=https://example.test/api?x=a=b\nQUOTED='hello world'\n", encoding="utf-8")
    parsed = parse_env_file(env)
    assert parsed["COPILOT_API_BASE_URL"] == "https://example.test/api?x=a=b"
    assert parsed["QUOTED"] == "hello world"
    assert "EMPTY" in parsed

def test_preflight_confirms_integrated_workstreams_in_canonical_app():
    checks = {item.name: item for item in route_registration_checks(ROOT)}
    assert checks["core_route_registration"].status == "PASS"
    assert checks["action_and_scenario_routes"].status == "PASS"
    assert checks["camera_vision_routes"].status == "PASS"
    assert checks["copilot_and_reports_routes"].status == "PASS"
    assert checks["what_if_routes"].status == "PASS"

def test_check_dataclass_contract():
    row = Check("sample", "WARN", "optional dependency missing", "install it", required=False)
    assert row.required is False
    assert row.status == "WARN"

def test_sqlite_url_parser_handles_relative_absolute_and_memory_urls(tmp_path):
    from scripts.preflight import _sqlite_target
    relative, error = _sqlite_target("sqlite:///./data/campus.db", tmp_path)
    assert error is None
    assert relative == str((tmp_path / "data" / "campus.db").resolve())
    absolute, error = _sqlite_target("sqlite:////var/tmp/campus.db", tmp_path)
    assert error is None
    assert absolute == "/var/tmp/campus.db"
    memory, note = _sqlite_target("sqlite:///:memory:", tmp_path)
    assert memory is None and "process-local" in note

def test_preflight_does_not_count_imported_but_unmounted_routers(tmp_path):
    app_dir = tmp_path / "backend" / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "main.py").write_text(
        "from app.routers.actions import router as actions_router\n"
        "from app.routers.scenarios import router as scenarios_router\n"
        "app = FastAPI()\n",
        encoding="utf-8",
    )
    checks = {item.name: item for item in route_registration_checks(tmp_path)}
    assert checks["action_and_scenario_routes"].status == "FAIL"
