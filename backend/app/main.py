from __future__ import annotations

import logging
import re
import uuid
from contextlib import asynccontextmanager
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import Engine

from app.core.clock import VirtualClock
from app.core.config import Settings
from app.core.errors import DomainError
from app.core.logging import configure_logging, redact
from app.db.session import get_session_factory, make_session_factory, initialize_database, make_engine
from app.routers import buildings, events, facts, health, impact, ledger, readings
from app.routers.actions import router as actions_router
from app.routers.scenarios import router as scenarios_router
from app.routers.ui import router as ui_router
from app.copilot.config import CopilotSettings
from app.copilot.facts import get_facts_snapshot
from app.copilot.router import router as copilot_router, reports_router
from app.integration.facts_adapter import build_facts_snapshot
from app.vision.router import build_vision_router
from app.vision.unavailable import UnavailableCameraVisionService
from app.what_if.router import router as what_if_router

logger = logging.getLogger(__name__)
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def _error_body(request: Request, code: str, message: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
            "details": redact(dict(details or {})),
        }
    }


def create_app(
    settings: Settings | None = None,
    *,
    clock: VirtualClock | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)

    if engine is None:
        engine, session_factory = get_session_factory(settings)
    else:
        initialize_database(engine)
        session_factory = make_session_factory(engine)

    clock = clock or VirtualClock(multiplier=settings.virtual_time_multiplier)
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Integrated CampusTwin AI: persisted campus data, deterministic scenarios, verified-action workflow, local camera evidence, grounded copilot and what-if projections.",
        docs_url="/docs" if settings.environment.lower() != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.clock = clock
    app.state.ui_settings = {
        "tariffPerKwh": float(settings.tariff_per_kwh) if settings.tariff_per_kwh is not None else None,
        "co2KgPerKwh": float(settings.co2_factor_kg_per_kwh) if settings.co2_factor_kg_per_kwh is not None else None,
        "energyWasteWatts": 500,
        "waterNightFlowLitresPerMinute": 2.0,
        "persistenceMinutes": 5,
        "verificationDropPercent": 30,
        "verificationWindowSeconds": 300,
        "scenarioClockMultiplier": clock.multiplier,
    }
    copilot_settings = CopilotSettings.from_env()
    app.state.copilot_configured = copilot_settings.provider_configured
    app.state.vision_service = UnavailableCameraVisionService()

    def persisted_facts_dependency(request: Request):
        session = request.app.state.session_factory()
        try:
            return build_facts_snapshot(session, request.app.state.settings)
        finally:
            session.close()

    # Account 7 uses this explicit seam for both copilot and what-if endpoints.
    app.dependency_overrides[get_facts_snapshot] = persisted_facts_dependency

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if _REQUEST_ID_RE.fullmatch(supplied) else str(uuid.uuid4())
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled_request_error", extra={"request_id": request_id, "method": request.method, "path": request.url.path})
            response = JSONResponse(
                status_code=500,
                content=_error_body(request, "INTERNAL_ERROR", "An unexpected server error occurred."),
            )
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request_completed",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path, "status_code": response.status_code},
        )
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(request, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        safe_errors = []
        for error in exc.errors():
            safe_errors.append({"field": ".".join(str(part) for part in error.get("loc", ())), "message": error.get("msg", "Invalid value")})
        return JSONResponse(
            status_code=422,
            content=_error_body(request, "VALIDATION_ERROR", "Request validation failed.", {"issues": safe_errors}),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        logger.exception("request_failed", extra={"request_id": getattr(request.state, "request_id", None), "error_type": type(exc).__name__})
        return JSONResponse(
            status_code=500,
            content=_error_body(request, "INTERNAL_ERROR", "An unexpected server error occurred."),
        )

    for router in (health.router, buildings.router, readings.router, events.router, impact.router, facts.router, ledger.router):
        app.include_router(router, prefix=settings.api_prefix)
    for feature_router in (actions_router, scenarios_router):
        app.include_router(feature_router, prefix=settings.api_prefix)
    app.include_router(ui_router)
    vision_router = build_vision_router(app.state.vision_service)
    app.include_router(vision_router)
    app.include_router(copilot_router)
    app.include_router(reports_router)
    app.include_router(what_if_router)

    @app.get("/demo", include_in_schema=False)
    def no_build_demo():
        """Serve a dependency-free local UI when npm/React assets are unavailable.

        This is an explicitly separate fallback, not a fabricated React/Vite build.
        The standard React application remains under `frontend/` for normal builds.
        """
        demo_file = Path(__file__).resolve().parents[2] / "frontend-lite" / "index.html"
        if not demo_file.is_file():
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "DEMO_UI_UNAVAILABLE", "message": "The no-build demo page is missing from this checkout."}},
            )
        return FileResponse(demo_file, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": settings.app_name, "health": f"{settings.api_prefix}/health", "docs": "/docs" if settings.environment.lower() != "production" else "disabled", "local_demo": "/demo"}

    return app


app = create_app()
