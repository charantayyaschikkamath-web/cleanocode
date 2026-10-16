from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.vision.router import build_vision_router
from backend.app.vision.service import CameraVisionService, InMemoryEvidenceSink, VisionSettings


class FakeDetector:
    available = True
    name = "api-test-detector"
    unavailable_reason = ""
    def detect(self, frame):
        return []


def jpeg_frame() -> bytes:
    rng = np.random.default_rng(4)
    frame = rng.integers(35, 220, size=(80, 100, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


def make_client(max_bytes=2_000_000):
    sink = InMemoryEvidenceSink()
    service = CameraVisionService(
        FakeDetector(),
        settings=VisionSettings(max_frame_bytes=max_bytes, model_configured=True, model_license_reviewed=True),
        evidence_sink=sink,
    )
    app = FastAPI()
    app.include_router(build_vision_router(service, max_frame_bytes=max_bytes))
    return TestClient(app), service, sink


def test_health_route_exposes_model_and_sink_status():
    client, _, _ = make_client()
    result = client.get("/api/vision/health")
    assert result.status_code == 200
    assert result.json()["detector_available"] is True
    assert result.json()["persistence_sink_configured"] is True


def test_frame_endpoint_returns_metadata_not_image():
    client, _, sink = make_client()
    result = client.post(
        "/api/vision/frame?room_id=R101&coverage_confirmed=true",
        content=jpeg_frame(),
        headers={"Content-Type": "image/jpeg"},
    )
    assert result.status_code == 200
    data = result.json()
    assert data["room_id"] == "R101"
    assert data["provenance"] == "REAL"
    assert data["signal"] == "NO_PERSON_DETECTED"
    assert "frame_bytes" not in data and "image" not in data
    assert len(sink.records) == 1


def test_endpoint_rejects_wrong_content_type():
    client, _, _ = make_client()
    result = client.post("/api/vision/frame?room_id=R1", content=b"abc", headers={"Content-Type": "application/json"})
    assert result.status_code == 415


def test_endpoint_rejects_oversized_frame():
    client, _, _ = make_client(max_bytes=12)
    result = client.post("/api/vision/frame?room_id=R1", content=b"x" * 20, headers={"Content-Type": "image/jpeg"})
    assert result.status_code == 413


def test_simulation_is_labeled_and_not_empty_timer_eligible():
    client, _, _ = make_client()
    result = client.post("/api/vision/simulated", json={
        "room_id": "R1", "person_count": 0, "coverage_confirmed": True,
    })
    assert result.status_code == 200
    data = result.json()
    assert data["provenance"] == "SIMULATED"
    assert data["eligible_for_empty_timer"] is False


def test_current_empty_room_without_evidence_is_unknown():
    client, _, _ = make_client()
    result = client.get("/api/vision/occupancy/current?room_id=R404")
    assert result.status_code == 200
    data = result.json()
    assert data["status"] == "UNKNOWN"
    assert data["evidence"] is None
