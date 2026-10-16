from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from typing import TYPE_CHECKING

from .schemas import OccupancyCurrentResponse, SimulatedOccupancyRequest
if TYPE_CHECKING:
    from .service import CameraVisionService


def build_vision_router(
    service: CameraVisionService,
    *,
    prefix: str = "/api/vision",
    max_frame_bytes: int | None = None,
) -> APIRouter:
    """Build router around Account 2's injected persistence adapter; no app entrypoint ownership."""
    router = APIRouter(prefix=prefix, tags=["camera-vision"])
    limit = max_frame_bytes or service.settings.max_frame_bytes

    @router.get("/health")
    def vision_health():
        return service.health()

    @router.post("/frame")
    async def analyze_frame(
        request: Request,
        room_id: str = Query(min_length=1, max_length=120),
        coverage_confirmed: bool = False,
        camera_label: str | None = Query(default=None, max_length=120),
    ):
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"image/jpeg", "image/jpg"}:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail={
                "code": "UNSUPPORTED_FRAME_TYPE", "message": "Send one JPEG frame as image/jpeg."
            })
        try:
            length = request.headers.get("content-length")
            if length and int(length) > limit:
                raise HTTPException(status_code=413, detail={
                    "code": "FRAME_TOO_LARGE", "message": f"Frame exceeds the {limit}-byte limit."
                })
        except ValueError:
            raise HTTPException(status_code=400, detail={"code": "INVALID_CONTENT_LENGTH", "message": "Invalid Content-Length."})

        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > limit:
                body.clear()
                raise HTTPException(status_code=413, detail={
                    "code": "FRAME_TOO_LARGE", "message": f"Frame exceeds the {limit}-byte limit."
                })
        # Do not log `body`; it exists only for this request and is not persisted.
        evidence = await run_in_threadpool(
            service.analyze_jpeg,
            room_id,
            bytes(body),
            coverage_confirmed=coverage_confirmed,
            camera_label=camera_label,
        )
        body.clear()
        return evidence

    @router.post("/simulated")
    def simulated_occupancy(payload: SimulatedOccupancyRequest):
        """Manual demo fallback. Provenance remains SIMULATED and it can never qualify for empty timer."""
        return service.record_simulated(payload)

    @router.get("/occupancy/current", response_model=OccupancyCurrentResponse)
    def current_occupancy(room_id: str = Query(min_length=1, max_length=120)):
        evidence, age_ms, message = service.current(room_id)
        if evidence is None:
            return OccupancyCurrentResponse(status="UNKNOWN", evidence=None, age_ms=None, message=message)
        return OccupancyCurrentResponse(status=evidence.status, evidence=evidence, age_ms=age_ms, message=message)

    return router
