"""Optional standalone app for local module testing. Main app integration belongs to Account 9."""
from fastapi import FastAPI

from backend.app.vision import CameraVisionService, build_vision_router


def create_standalone_app() -> FastAPI:
    service = CameraVisionService()
    app = FastAPI(title="CampusTwin Account 4 Camera Vision (Standalone)", version="0.1.0")
    app.include_router(build_vision_router(service))
    return app


app = create_standalone_app()
