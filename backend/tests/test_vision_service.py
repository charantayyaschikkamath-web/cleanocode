from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import cv2
import numpy as np
import pytest

from backend.app.vision.inference import InferenceUnavailable
from backend.app.vision.schemas import (
    EvidenceStatus,
    OccupancySignal,
    PersistenceStatus,
    Provenance,
    SimulatedOccupancyRequest,
)
from backend.app.vision.service import CameraVisionService, InMemoryEvidenceSink, VisionSettings


@dataclass
class FakeDetection:
    confidence: float = 0.9


class FakeDetector:
    available = True
    name = "test-person-detector"
    unavailable_reason = ""

    def __init__(self, counts: list[int] | None = None, error: Exception | None = None):
        self.counts = list(counts or [0])
        self.error = error
        self.calls = 0

    def detect(self, frame_bgr):
        self.calls += 1
        if self.error:
            raise self.error
        index = min(self.calls - 1, len(self.counts) - 1)
        return [FakeDetection() for _ in range(self.counts[index])]


def jpeg_frame(*, kind: str = "varied") -> bytes:
    if kind == "dark":
        frame = np.zeros((90, 120, 3), dtype=np.uint8)
    elif kind == "flat":
        frame = np.full((90, 120, 3), 110, dtype=np.uint8)
    else:
        rng = np.random.default_rng(7)
        frame = rng.integers(35, 220, size=(90, 120, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return encoded.tobytes()


def make_service(detector=None, sink=None, **setting_overrides):
    settings = VisionSettings(**setting_overrides)
    return CameraVisionService(detector or FakeDetector(), settings=settings, evidence_sink=sink)


def test_person_detected_resets_empty_timer_even_when_smoothed_count_would_be_zero():
    detector = FakeDetector([0, 1, 0, 0, 0])
    service = make_service(detector)
    frame = jpeg_frame()
    first = service.analyze_jpeg("B1-R101", frame, coverage_confirmed=True)
    assert first.signal == OccupancySignal.NO_PERSON_DETECTED
    person = service.analyze_jpeg("B1-R101", frame, coverage_confirmed=True)
    assert person.signal == OccupancySignal.PERSON_DETECTED
    assert person.raw_person_count == 1
    assert person.eligible_for_empty_timer is False


def test_valid_no_person_only_eligible_when_coverage_is_manually_confirmed():
    service = make_service(FakeDetector([0]))
    without_attestation = service.analyze_jpeg("R1", jpeg_frame(), coverage_confirmed=False)
    with_attestation = service.analyze_jpeg("R2", jpeg_frame(), coverage_confirmed=True)
    assert without_attestation.signal == OccupancySignal.NO_PERSON_DETECTED
    assert not without_attestation.eligible_for_empty_timer
    assert with_attestation.signal == OccupancySignal.NO_PERSON_DETECTED
    assert with_attestation.eligible_for_empty_timer
    assert "one signal only" in with_attestation.explanation


def test_missing_model_is_unavailable_never_empty():
    from backend.app.vision.inference import UnavailableDetector
    service = make_service(UnavailableDetector("MODEL_NOT_CONFIGURED"))
    result = service.analyze_jpeg("R1", jpeg_frame(), coverage_confirmed=True)
    assert result.status == EvidenceStatus.UNAVAILABLE
    assert result.signal == OccupancySignal.UNKNOWN
    assert result.eligible_for_empty_timer is False


def test_dark_or_flat_frame_returns_unknown_without_running_detector():
    detector = FakeDetector([0])
    service = make_service(detector)
    dark = service.analyze_jpeg("R1", jpeg_frame(kind="dark"), coverage_confirmed=True)
    flat = service.analyze_jpeg("R2", jpeg_frame(kind="flat"), coverage_confirmed=True)
    assert dark.status == EvidenceStatus.UNKNOWN
    assert dark.signal == OccupancySignal.UNKNOWN
    assert flat.status == EvidenceStatus.UNKNOWN
    assert detector.calls == 0


def test_invalid_image_and_inference_error_fail_closed():
    service = make_service(FakeDetector())
    invalid = service.analyze_jpeg("R1", b"not a jpeg", coverage_confirmed=True)
    assert invalid.status == EvidenceStatus.UNKNOWN
    assert invalid.signal == OccupancySignal.UNKNOWN
    broken = make_service(FakeDetector(error=InferenceUnavailable("runtime error")))
    failed = broken.analyze_jpeg("R2", jpeg_frame(), coverage_confirmed=True)
    assert failed.status == EvidenceStatus.UNAVAILABLE
    assert failed.signal == OccupancySignal.UNKNOWN
    assert not failed.eligible_for_empty_timer


def test_simulated_input_is_explicit_and_never_eligible_for_real_empty_timer():
    sink = InMemoryEvidenceSink()
    service = make_service(FakeDetector(), sink)
    result = service.record_simulated(SimulatedOccupancyRequest(room_id="R1", person_count=0, coverage_confirmed=True))
    assert result.provenance == Provenance.SIMULATED
    assert result.signal == OccupancySignal.NO_PERSON_DETECTED
    assert not result.eligible_for_empty_timer
    assert result.persistence_status == PersistenceStatus.RECORDED
    assert len(sink.records) == 1
    assert not hasattr(sink.records[0], "frame_bytes")


def test_persistence_sink_receives_only_derived_metadata():
    sink = InMemoryEvidenceSink()
    service = make_service(FakeDetector([1]), sink)
    result = service.analyze_jpeg("R1", jpeg_frame(), coverage_confirmed=True)
    assert result.persistence_status == PersistenceStatus.RECORDED
    record = sink.records[0].model_dump()
    assert "frame" not in record
    assert "frame_bytes" not in record
    assert record["raw_person_count"] == 1


def test_freshness_becomes_unknown_after_timeout(monkeypatch):
    # Use a deliberately tiny freshness window and age the service's monotonic timestamp.
    service = make_service(FakeDetector([0]), max_frame_age_ms=10)
    service.analyze_jpeg("R1", jpeg_frame(), coverage_confirmed=True)
    with service._lock:
        service._rooms["R1"].latest_monotonic -= 0.05
    evidence, age_ms, _ = service.current("R1")
    assert age_ms is not None and age_ms > 10
    assert evidence is not None
    assert evidence.status == EvidenceStatus.UNKNOWN
    assert evidence.signal == OccupancySignal.UNKNOWN
    assert evidence.reason_code == "STALE_FRAME"
    assert not evidence.eligible_for_empty_timer


def test_oversized_frame_is_not_inferred():
    detector = FakeDetector([0])
    service = make_service(detector, max_frame_bytes=10)
    result = service.analyze_jpeg("R1", jpeg_frame(), coverage_confirmed=True)
    assert result.reason_code == "FRAME_TOO_LARGE"
    assert result.status == EvidenceStatus.UNKNOWN
    assert detector.calls == 0


def test_health_reports_missing_persistence_sink_truthfully():
    service = make_service(FakeDetector())
    health = service.health()
    assert health.detector_available is True
    assert health.persistence_sink_configured is False
    assert health.privacy == "TRANSIENT_FRAMES_DERIVED_EVIDENCE_ONLY"


def test_local_onnx_adapter_detects_only_person_class_and_refuses_other_output_layouts(tmp_path, monkeypatch):
    import sys
    import types

    from backend.app.vision.inference import InferenceUnavailable, YoloV8OnnxPersonDetector

    model_path = tmp_path / "approved.onnx"
    model_path.write_bytes(b"test-model-placeholder")

    # Output layout mimics a YOLOv8-style COCO-80 tensor: [1, 84, candidates].
    class FakeInput:
        name = "images"
        shape = [1, 3, 64, 64]

    class FakeOutput:
        shape = [1, 84, 2]

    class FakeSession:
        output = None
        def __init__(self, model_path, providers):
            assert providers == ["CPUExecutionProvider"]
        def get_inputs(self):
            return [FakeInput()]
        def get_outputs(self):
            return [FakeOutput()]
        def run(self, outputs, inputs):
            assert list(inputs) == ["images"]
            return [self.output]

    fake_session = FakeSession("ignored", ["CPUExecutionProvider"])
    ort_module = types.SimpleNamespace(
        InferenceSession=lambda path, providers: fake_session
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", ort_module)

    detector = YoloV8OnnxPersonDetector(model_path, license_reviewed=True)
    assert detector.available
    output = np.zeros((1, 84, 2), dtype=np.float32)
    output[0, 0:4, 0] = [32, 32, 20, 20]
    output[0, 4, 0] = 0.91  # COCO person
    output[0, 4, 1] = 0.10
    output[0, 5, 1] = 0.99  # high bicycle confidence must not count as a person
    fake_session.output = output
    detections = detector.detect(np.full((64, 64, 3), 120, dtype=np.uint8))
    assert len(detections) == 1
    assert detections[0].confidence == pytest.approx(0.91)

    unsupported = np.zeros((1, 85, 2), dtype=np.float32)
    fake_session.output = unsupported
    with pytest.raises(InferenceUnavailable, match="COCO_80_EXPECTED"):
        detector.detect(np.full((64, 64, 3), 120, dtype=np.uint8))


def test_dimensions_are_rejected_before_person_inference():
    detector = FakeDetector([0])
    service = make_service(detector, max_frame_width=100, max_frame_height=100)
    result = service.analyze_jpeg("R1", jpeg_frame(), coverage_confirmed=True)
    assert result.reason_code == "FRAME_DIMENSIONS_EXCEEDED"
    assert result.status == EvidenceStatus.UNKNOWN
    assert detector.calls == 0


def test_even_window_median_rounds_up_to_avoid_missing_a_possible_person():
    detector = FakeDetector([0, 1, 0, 1, 0])
    service = make_service(detector, smoothing_window=4)
    frame = jpeg_frame()
    for _ in range(4):
        service.analyze_jpeg("R1", frame, coverage_confirmed=True)
    fifth = service.analyze_jpeg("R1", frame, coverage_confirmed=True)
    # The last 4 raw counts are [1, 0, 1, 0], so median=0.5; ceiling keeps the output conservatively occupied.
    assert fifth.smoothed_person_count == 1
    assert fifth.signal == OccupancySignal.PERSON_DETECTED
