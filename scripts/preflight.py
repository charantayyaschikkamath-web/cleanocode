#!/usr/bin/env python3
"""CampusTwin AI release preflight. Uses only the Python standard library."""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class Check:
    name: str
    status: str  # PASS, WARN, FAIL
    message: str
    repair: str = ""
    required: bool = True


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def effective_setting(root: Path, *names: str) -> str | None:
    env_values = {key: value for key, value in os.environ.items()}
    file_values = parse_env_file(root / ".env")
    for name in names:
        value = env_values.get(name) or file_values.get(name)
        if value:
            return value
    return None


def _route_sources(root: Path) -> list[Path]:
    app_dir = root / "backend" / "app"
    if not app_dir.is_dir():
        return []
    # Canonical application registration is owned by Account 9. A development shim
    # must not make the canonical application look integrated.
    return [p for p in app_dir.glob("main*.py") if p.name == "main.py"]


def _mounted_router_symbols(source: str) -> set[str]:
    """Return names actually passed into include_router calls, including factory calls."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    mounted: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "include_router" or not node.args:
            continue
        router_arg = node.args[0]
        mounted.add(ast.unparse(router_arg))
        for part in ast.walk(router_arg):
            if isinstance(part, ast.Name):
                mounted.add(part.id)
            elif isinstance(part, ast.Attribute):
                mounted.add(part.attr)
                mounted.add(ast.unparse(part))
            elif isinstance(part, ast.Call):
                if isinstance(part.func, ast.Name):
                    mounted.add(part.func.id)
                elif isinstance(part.func, ast.Attribute):
                    mounted.add(part.func.attr)
    # Handle the core entrypoint's `for router in (health.router, ...): app.include_router(router)`.
    mounted_aliases = set(mounted)
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            target = node.target.id
            if target not in mounted_aliases or not isinstance(node.iter, (ast.Tuple, ast.List, ast.Set)):
                continue
            for item in node.iter.elts:
                mounted_aliases.add(ast.unparse(item))
                for part in ast.walk(item):
                    if isinstance(part, ast.Name): mounted_aliases.add(part.id)
                    elif isinstance(part, ast.Attribute):
                        mounted_aliases.add(part.attr)
                        mounted_aliases.add(ast.unparse(part))
    return mounted_aliases


def route_registration_checks(root: Path) -> list[Check]:
    main = root / "backend" / "app" / "main.py"
    if not main.is_file():
        return [Check("canonical_routes", "FAIL", "backend/app/main.py is missing.", "Restore the canonical FastAPI entry point.")]
    source = main.read_text(encoding="utf-8", errors="replace")
    compact = re.sub(r"\s+", " ", source)
    mounted = _mounted_router_symbols(source)
    checks: list[Check] = []

    core_expected = {"health.router", "buildings.router", "events.router", "ledger.router"}
    core_missing = sorted(core_expected - mounted)
    core_ok = not core_missing
    checks.append(Check(
        "core_route_registration", "PASS" if core_ok else "FAIL",
        "Canonical main.py mounts the core health/buildings/events/ledger routers." if core_ok else f"Canonical main.py is missing core router mounts: {', '.join(core_missing)}.",
        "Register the core Account 2 routers once in backend/app/main.py." if not core_ok else "",
    ))

    route_groups = [
        ("action_and_scenario_routes", {"actions_router", "scenarios_router"}, "Register Account 3 actions and scenarios routers in backend/app/main.py."),
        ("camera_vision_routes", {"vision_router"}, "Construct the Account 4 vision service explicitly and mount its router; keep model-unavailable status non-fatal for the simulated demo."),
        ("copilot_and_reports_routes", {"copilot_router", "reports_router"}, "Register the Account 7 copilot router and reports_router in the canonical app."),
        ("what_if_routes", {"what_if_router"}, "Register the Account 7 What-If router in the canonical app."),
    ]
    for name, tokens, repair in route_groups:
        present = tokens.issubset(mounted)
        if name == "camera_vision_routes":
            present = present and "build_vision_router" in source and "CameraVisionService" in source
        checks.append(Check(
            name, "PASS" if present else "FAIL",
            f"Canonical main.py mounts the required routers for {name.replace('_', ' ')}." if present else f"The Account 9 integration for {name.replace('_', ' ')} is not visible as a router mount in canonical main.py.",
            "" if present else repair,
        ))

    if "include_router" not in compact:
        checks.append(Check("router_mounts", "FAIL", "No include_router call found in canonical main.py.", "Mount application routers using the frozen route contracts."))
    return checks


def _sqlite_target(database_url: str, root: Path) -> tuple[str | None, str | None]:
    if not database_url.startswith("sqlite"):
        return None, "Database URL is not SQLite; use the live `/health` and `/preflight` checks for connection validation."
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        return None, "SQLite in-memory database is configured; it is process-local and not restart-persistent."
    # SQLAlchemy's common forms are sqlite:///relative.db, sqlite:////absolute.db,
    # and sqlite:///:memory:. Strip the driver prefix first so slash counting is explicit.
    match = re.match(r"^sqlite(?:\+[^:]+)?://(.*)$", database_url)
    if not match:
        return None, "Could not safely resolve the configured SQLite URL."
    raw_path = match.group(1).split("?", 1)[0]
    if raw_path.startswith("//"):
        raw_path = raw_path[1:]  # four-slash URL denotes an absolute path
    elif raw_path.startswith("/"):
        raw_path = raw_path[1:]  # three-slash URL denotes a path relative to the process cwd
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    return str(path.resolve()), None


def database_check(root: Path) -> Check:
    url = effective_setting(root, "CAMPUS_TWIN_DATABASE_URL", "DATABASE_URL")
    if not url:
        config_text = (root / "config.yaml").read_text(encoding="utf-8", errors="replace") if (root / "config.yaml").is_file() else ""
        match = re.search(r"(?m)^\s*url:\s*['\"]?(sqlite[^\s'\"]+)", config_text)
        url = match.group(1) if match else None
    if not url:
        return Check("database_configuration", "WARN", "No active database URL found in environment or `.env`; the application default will be used.", "Set CAMPUS_TWIN_DATABASE_URL or DATABASE_URL for reproducible setup.", required=False)
    target, note = _sqlite_target(url, root)
    if target is None:
        if url.startswith("sqlite"):
            return Check("database", "WARN", note or "SQLite database is not a durable file.", "Use a file-backed SQLite URL for persistence across restarts; memory mode is suitable only for tests.", required=False)
        return Check("database", "WARN", note or "Database needs live connectivity validation.", "Run preflight with --base-url against the running app.", required=False)
    path = Path(target)
    if path.exists():
        try:
            # Read-only URI avoids creating/updating a database during preflight.
            with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2.0) as conn:
                result = conn.execute("PRAGMA quick_check").fetchone()
                if not result or result[0] != "ok":
                    return Check("database", "FAIL", "SQLite quick_check reported a problem.", "Back up the file and repair/migrate it explicitly before the demo.")
            return Check("database", "PASS", "Configured SQLite file exists and passes read-only PRAGMA quick_check.")
        except sqlite3.Error as exc:
            return Check("database", "FAIL", f"Could not validate the configured SQLite file ({type(exc).__name__}).", "Check file permissions, URL path and schema migration status.")
    parent = path.parent
    probe = parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.exists() and probe.is_dir() and os.access(probe, os.W_OK):
        return Check("database", "WARN", f"Database file does not exist yet; nearest existing parent `{probe}` is writable.", "Start the backend once (which should create the configured data directory), then rerun preflight to validate the database file.", required=False)
    return Check("database", "FAIL", "Database file does not exist and no writable ancestor directory was found.", "Create the configured data directory and grant write access to the application user.")


def _file_check(root: Path, relative: str, *, required: bool = True, description: str | None = None) -> Check:
    path = root / relative
    exists = path.is_file()
    return Check(
        "file:" + relative,
        "PASS" if exists else ("FAIL" if required else "WARN"),
        f"{description or relative} {'exists' if exists else 'is missing' }.",
        "Restore this file from its owning workstream or update the documented project layout." if not exists else "",
        required=required,
    )


def _live_route_check(base_url: str, root: Path) -> list[Check]:
    base = base_url.rstrip("/")
    prefix = effective_setting(root, "CAMPUS_TWIN_API_PREFIX") or "/api/v1"
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    checks: list[Check] = []
    openapi: dict = {}
    try:
        req = Request(base + "/openapi.json", headers={"Accept": "application/json"})
        with urlopen(req, timeout=4) as response:
            if response.status == 200:
                openapi = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        openapi = {}

    if openapi.get("paths"):
        paths = openapi["paths"]
        endpoints = [
            ("health", "get", f"{prefix}/health", True),
            ("preflight", "get", f"{prefix}/preflight", True),
            ("buildings", "get", f"{prefix}/buildings", True),
            ("events", "get", f"{prefix}/events", True),
            ("ledger", "get", f"{prefix}/ledger", True),
            ("scenarios", "get", f"{prefix}/scenarios", True),
            ("actions", "get", f"{prefix}/actions", True),
            ("camera vision", "get", "/api/vision/health", False),
            ("copilot", "post", "/api/copilot/query", False),
            ("what-if", "post", "/api/what-if/run", False),
            ("reports", "post", "/api/reports", False),
        ]
        for label, method, path, required in endpoints:
            found = path in paths and method in paths[path]
            checks.append(Check(
                "live_route:" + label.replace(" ", "_"),
                "PASS" if found else ("FAIL" if required else "WARN"),
                f"Live OpenAPI exposes {method.upper()} {path}." if found else f"Live OpenAPI does not expose {method.upper()} {path}.",
                "Register the owning router and verify its prefix against docs/CONTRACTS.md." if not found else "",
                required=required,
            ))
        return checks

    # OpenAPI may be intentionally disabled in production; still validate health.
    try:
        req = Request(base + f"{prefix}/health", headers={"Accept": "application/json"})
        with urlopen(req, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
            healthy = response.status == 200 and payload.get("status") == "ok" and payload.get("database") == "healthy"
            checks.append(Check("live_health", "PASS" if healthy else "FAIL", "Live health endpoint is healthy." if healthy else "Live health endpoint reported degraded/unhealthy status.", "Inspect the backend health JSON and database connection." if not healthy else ""))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        checks.append(Check("live_health", "FAIL", f"Could not reach live health endpoint ({type(exc).__name__}).", f"Start the backend and verify {base}{prefix}/health."))
    checks.append(Check("live_route_inventory", "WARN", "OpenAPI route inventory unavailable; only the health endpoint was checked.", "Temporarily enable OpenAPI for the demo environment or use the static registration audit.", required=False))
    return checks


def collect_checks(root: Path, *, base_url: str | None = None) -> list[Check]:
    checks: list[Check] = []
    version_ok = sys.version_info >= (3, 11)
    checks.append(Check("python_version", "PASS" if version_ok else "FAIL", f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} is available.", "Use Python 3.11 or newer for the documented stack." if not version_ok else ""))

    for relative, required in [
        ("backend/app/main.py", True),
        ("backend/app/core/config.py", True),
        ("backend/app/db/session.py", True),
        ("backend/app/routers/scenarios.py", True),
        ("backend/app/routers/actions.py", True),
        ("backend/app/vision/router.py", False),
        ("backend/app/copilot/router.py", False),
        ("backend/app/what_if/router.py", False),
        ("frontend/package.json", True),
        ("frontend/src/main.tsx", True),
        ("docs/CONTRACTS.md", True),
        ("docs/KNOWN_LIMITATIONS.md", True),
        ("docs/ALGORITHMS.md", True),
        (".env.example", True),
        ("config.yaml", True),
    ]:
        checks.append(_file_check(root, relative, required=required))

    for module in ("fastapi", "pydantic", "sqlalchemy", "yaml", "dotenv", "httpx"):
        available = importlib.util.find_spec(module) is not None
        checks.append(Check(
            "python_dependency:" + module,
            "PASS" if available else "FAIL",
            f"Required Python module `{module}` is importable." if available else f"Required Python module `{module}` is not installed.",
            f"Install the project's pinned Python dependencies before the demo (see requirements files)." if not available else "",
        ))

    import shutil
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")
    checks.append(Check("node_toolchain", "PASS" if node_path and npm_path else "FAIL", "Node.js and npm are available." if node_path and npm_path else "Node.js or npm is missing.", "Install the supported Node.js LTS toolchain before building the frontend." if not (node_path and npm_path) else ""))

    package_lock = any((root / "frontend" / name).is_file() for name in ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock"))
    checks.append(Check("frontend_lockfile", "PASS" if package_lock else "WARN", "A frontend package lockfile is present." if package_lock else "No frontend package lockfile is present; clean/offline npm install is not reproducible yet.", "Run npm install, review the generated lockfile, and commit it before release." if not package_lock else "", required=False))

    dist_index = root / "frontend" / "dist" / "index.html"
    checks.append(Check("frontend_build", "PASS" if dist_index.is_file() else "FAIL", "Built frontend entry point exists." if dist_index.is_file() else "Built frontend assets are missing.", "From frontend/, run npm ci and npm run build; do not mark release-ready until build output exists." if not dist_index.is_file() else ""))

    env_example = parse_env_file(root / ".env.example")
    db_check = database_check(root)
    checks.append(db_check)
    multiplier_raw = effective_setting(root, "CAMPUS_TWIN_VIRTUAL_TIME_MULTIPLIER") or env_example.get("CAMPUS_TWIN_VIRTUAL_TIME_MULTIPLIER") or "30"
    try:
        multiplier = float(multiplier_raw)
        good_multiplier = multiplier > 0 and multiplier < float("inf")
    except (TypeError, ValueError):
        good_multiplier = False
    checks.append(Check("virtual_clock", "PASS" if good_multiplier else "FAIL", "Virtual-time multiplier is valid." if good_multiplier else "Virtual-time multiplier must be a finite positive number.", "Set CAMPUS_TWIN_VIRTUAL_TIME_MULTIPLIER to a finite positive value (for example, 30)." if not good_multiplier else ""))

    llm_key = effective_setting(root, "COPILOT_API_KEY", "OPENAI_API_KEY")
    checks.append(Check("llm_provider_key", "PASS" if llm_key else "WARN", "An LLM provider key is configured (value was not displayed)." if llm_key else "No LLM provider key detected; template mode should be used.", "Optional: configure COPILOT_API_BASE_URL, COPILOT_API_KEY and COPILOT_MODEL server-side; no key is required for core demo paths.", required=False))

    model_path = effective_setting(root, "VISION_MODEL_PATH", "YOLO_MODEL_PATH")
    model_exists = bool(model_path and Path(model_path).expanduser().is_file())
    if model_exists:
        vision_status, vision_message = "PASS", "Configured local vision model file exists."
    else:
        vision_status, vision_message = "WARN", "No local vision model file is configured/found; camera inference is unavailable and must remain UNKNOWN/UNAVAILABLE, not be replaced with live-looking sample detections."
    checks.append(Check("vision_model", vision_status, vision_message, "Optional: set VISION_MODEL_PATH to reviewed local weights. Do not auto-download weights at startup; simulated occupancy must remain visibly labelled.", required=False))

    registration_checks = route_registration_checks(root)
    # Static source audit is a required integration gate; individual optional hardware/API keys are not.
    checks.extend(registration_checks)

    offline_lock = package_lock and (root / "backend" / "requirements.txt").is_file()
    checks.append(Check("offline_dependency_inputs", "PASS" if offline_lock else "WARN", "Python requirements and a frontend lockfile are available for offline preparation." if offline_lock else "Offline dependency preparation is not reproducible until a frontend lockfile is committed.", "Resolve/pin dependencies, generate the frontend lockfile, and prepare the wheelhouse before disabling Wi-Fi.", required=False))

    if base_url:
        checks.extend(_live_route_check(base_url, root))
    return checks


def report_payload(root: Path, checks: Iterable[Check]) -> dict:
    rows = [asdict(item) for item in checks]
    counts = {status: sum(1 for item in rows if item["status"] == status) for status in ("PASS", "WARN", "FAIL")}
    return {
        "report_type": "PRELIGHT_CHECK_RESULTS",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "project_root": str(root),
        "status": "FAIL" if counts["FAIL"] else ("WARN" if counts["WARN"] else "PASS"),
        "counts": counts,
        "checks": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Repository root")
    parser.add_argument("--base-url", help="Optional running backend URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--json-out", type=Path, help="Optional JSON output path")
    parser.add_argument("--strict-warnings", action="store_true", help="Exit nonzero on warnings as well as failures")
    args = parser.parse_args()
    root = args.root.resolve()
    checks = collect_checks(root, base_url=args.base_url)
    report = report_payload(root, checks)

    print("CampusTwin AI — Release Preflight")
    print(f"Root: {root}")
    print(f"Status: {report['status']}  |  PASS {report['counts']['PASS']}  WARN {report['counts']['WARN']}  FAIL {report['counts']['FAIL']}")
    for item in report["checks"]:
        print(f"[{item['status']:<4}] {item['name']}: {item['message']}")
        if item["repair"] and item["status"] != "PASS":
            print(f"       Fix: {item['repair']}")
    if args.json_out:
        output = args.json_out if args.json_out.is_absolute() else root / args.json_out
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"JSON report: {output}")
    if report["counts"]["FAIL"] or (args.strict_warnings and report["counts"]["WARN"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
