from __future__ import annotations

import logging
from datetime import timezone

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.schemas import PreflightCheck, PreflightOut

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    db_state = "healthy"
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        db_state = "unavailable"
        logger.exception("database_health_check_failed", extra={"request_id": getattr(request.state, "request_id", None)})
    clock = request.app.state.clock
    settings = request.app.state.settings
    return {
        "status": "ok" if db_state == "healthy" else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "database": db_state,
        "clock": clock.description(),
    }


@router.get("/preflight", response_model=PreflightOut)
def preflight(request: Request) -> PreflightOut:
    settings = request.app.state.settings
    clock = request.app.state.clock
    checks: list[PreflightCheck] = []

    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks.append(PreflightCheck(name="database", status="PASS", message="Database accepts a simple query."))
    except Exception as exc:
        checks.append(PreflightCheck(name="database", status="FAIL", message="Database connection failed.", details={"error_type": type(exc).__name__}))

    checks.append(PreflightCheck(
        name="configuration",
        status="PASS",
        message="Settings passed validation.",
        details={"database_driver": settings.database_url.split(":", 1)[0], "api_prefix": settings.api_prefix},
    ))
    checks.append(PreflightCheck(
        name="virtual_clock",
        status="PASS" if clock.multiplier > 0 else "FAIL",
        message="Virtual clock is configured; supplied durations are interpreted as virtual seconds.",
        details={"multiplier": clock.multiplier, "wall_time_separate": True},
    ))
    missing_factors = []
    if settings.tariff_per_kwh is None:
        missing_factors.append("tariff_per_kwh")
    if settings.co2_factor_kg_per_kwh is None:
        missing_factors.append("co2_factor_kg_per_kwh")
    checks.append(PreflightCheck(
        name="impact_factors",
        status="WARN" if missing_factors else "PASS",
        message="Optional factors are missing; affected cost or CO2 metrics will remain unavailable." if missing_factors else "Tariff and emission factor are configured.",
        details={"missing": missing_factors},
    ))

    statuses = {check.status for check in checks}
    result = "FAIL" if "FAIL" in statuses else ("WARN" if "WARN" in statuses else "PASS")
    return PreflightOut(
        status=result,
        timestamp=clock.wall_now().astimezone(timezone.utc),
        checks=checks,
    )
