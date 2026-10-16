from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class PersonDetection:
    """Detection metadata only; bounding boxes are intentionally not exposed or stored."""

    confidence: float


class PersonDetector(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def name(self) -> str: ...

    def detect(self, frame_bgr: np.ndarray) -> list[PersonDetection]: ...


class InferenceUnavailable(RuntimeError):
    """Raised when local inference cannot safely run."""


class UnavailableDetector:
    def __init__(self, reason: str = "MODEL_NOT_CONFIGURED") -> None:
        self.reason = reason

    @property
    def available(self) -> bool:
        return False

    @property
    def name(self) -> str:
        return "unavailable"

    def detect(self, frame_bgr: np.ndarray) -> list[PersonDetection]:
        raise InferenceUnavailable(self.reason)


class YoloV8OnnxPersonDetector:
    """Local-only YOLOv8-style COCO ONNX detector; no downloads and no frame persistence.

    Supported output: [1, 4 + class_count, candidate_count] or its transposed form,
    with COCO person at class index 0 and xywh boxes in model-input coordinates.
    The model file and its license must be supplied/reviewed by the operator.
    """

    def __init__(
        self,
        model_path: str | Path,
        *,
        confidence_threshold: float = 0.45,
        nms_threshold: float = 0.45,
        expected_sha256: str | None = None,
        license_reviewed: bool = False,
        model_name: str = "local-onnx-person-detector",
    ) -> None:
        self._model_path = Path(model_path).expanduser()
        self._confidence_threshold = float(confidence_threshold)
        self._nms_threshold = float(nms_threshold)
        self._session = None
        self._input_name: str | None = None
        self._input_height = 640
        self._input_width = 640
        self._reason = "MODEL_NOT_CONFIGURED"
        self._name = model_name

        if not license_reviewed:
            self._reason = "MODEL_LICENSE_NOT_REVIEWED"
            return
        if not self._model_path.is_file():
            self._reason = "MODEL_FILE_MISSING"
            return
        if expected_sha256:
            hasher = hashlib.sha256()
            with self._model_path.open("rb") as model_file:
                for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
            if digest.lower() != expected_sha256.strip().lower():
                self._reason = "MODEL_SHA256_MISMATCH"
                return
        try:
            import onnxruntime as ort  # optional dependency; not imported unless configured

            # Force local CPU inference, disable runtime telemetry where the installed ORT build exposes it,
            # and never download model assets/providers from this module.
            disable_telemetry = getattr(ort, "disable_telemetry_events", None)
            if callable(disable_telemetry):
                disable_telemetry()
            self._session = ort.InferenceSession(
                str(self._model_path), providers=["CPUExecutionProvider"]
            )
            model_inputs = self._session.get_inputs()
            model_outputs = self._session.get_outputs()
            if len(model_inputs) != 1 or len(model_outputs) != 1:
                self._session = None
                self._reason = "UNSUPPORTED_MODEL_IO_COUNT"
                return
            model_input = model_inputs[0]
            self._input_name = model_input.name
            shape = model_input.shape
            if len(shape) != 4:
                self._session = None
                self._reason = "UNSUPPORTED_MODEL_INPUT_SHAPE"
                return
            if isinstance(shape[2], int) and shape[2] > 0:
                self._input_height = shape[2]
            if isinstance(shape[3], int) and shape[3] > 0:
                self._input_width = shape[3]
            output_shape = model_outputs[0].shape
            if len(output_shape) != 3 or (output_shape[1] != 84 and output_shape[2] != 84):
                self._session = None
                self._reason = "UNSUPPORTED_MODEL_OUTPUT_SHAPE_COCO_80_EXPECTED"
                return
            self._reason = ""
        except Exception as exc:  # never log frame bytes or inference tensors
            self._session = None
            self._reason = f"MODEL_LOAD_FAILED:{type(exc).__name__}"

    @property
    def available(self) -> bool:
        return self._session is not None and self._input_name is not None

    @property
    def name(self) -> str:
        return self._name if self.available else "unavailable"

    @property
    def confidence_threshold(self) -> float:
        return self._confidence_threshold

    @property
    def nms_threshold(self) -> float:
        return self._nms_threshold

    @property
    def unavailable_reason(self) -> str:
        return self._reason

    def detect(self, frame_bgr: np.ndarray) -> list[PersonDetection]:
        if not self.available or self._session is None or self._input_name is None:
            raise InferenceUnavailable(self._reason or "INFERENCE_UNAVAILABLE")

        h, w = frame_bgr.shape[:2]
        if h <= 0 or w <= 0:
            raise InferenceUnavailable("INVALID_FRAME_DIMENSIONS")

        target_w, target_h = self._input_width, self._input_height
        scale = min(target_w / w, target_h / h)
        resized_w, resized_h = max(1, round(w * scale)), max(1, round(h * scale))
        resized = cv2.resize(frame_bgr, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
        pad_x = (target_w - resized_w) // 2
        pad_y = (target_h - resized_h) // 2
        canvas[pad_y : pad_y + resized_h, pad_x : pad_x + resized_w] = resized
        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
        tensor = np.transpose(rgb.astype(np.float32) / 255.0, (2, 0, 1))[None, ...]

        outputs = self._session.run(None, {self._input_name: tensor})
        if not outputs:
            raise InferenceUnavailable("MODEL_RETURNED_NO_OUTPUTS")
        pred = np.asarray(outputs[0])
        if pred.ndim != 3 or pred.shape[0] != 1:
            raise InferenceUnavailable("UNSUPPORTED_MODEL_OUTPUT_SHAPE")
        pred = pred[0]
        # YOLOv8 commonly produces [84, candidates]; also accept [candidates, 84].
        # Check the known COCO-80 channel dimension so even small candidate counts work.
        if pred.shape[0] == 84 and pred.shape[1] != 84:
            pred = pred.T
        # This adapter deliberately supports the documented YOLOv8-style COCO-80 output only.
        # Refuse YOLOv5/objectness/custom-class layouts rather than silently miscount people.
        if pred.ndim != 2 or pred.shape[1] != 84:
            raise InferenceUnavailable("UNSUPPORTED_MODEL_OUTPUT_SHAPE_COCO_80_EXPECTED")

        person_scores = pred[:, 4]  # COCO class 0 is person; YOLOv8 has no objectness channel.
        candidate_indices = np.flatnonzero(person_scores >= self._confidence_threshold)
        if candidate_indices.size == 0:
            return []

        boxes: list[list[int]] = []
        scores: list[float] = []
        for idx in candidate_indices.tolist():
            cx, cy, bw, bh = [float(v) for v in pred[idx, :4]]
            x = (cx - bw / 2 - pad_x) / scale
            y = (cy - bh / 2 - pad_y) / scale
            box_w, box_h = bw / scale, bh / scale
            x1 = max(0, min(w - 1, int(round(x))))
            y1 = max(0, min(h - 1, int(round(y))))
            x2 = max(0, min(w, int(round(x + box_w))))
            y2 = max(0, min(h, int(round(y + box_h))))
            if x2 <= x1 or y2 <= y1:
                continue
            boxes.append([x1, y1, x2 - x1, y2 - y1])
            scores.append(float(person_scores[idx]))

        if not boxes:
            return []
        kept = cv2.dnn.NMSBoxes(
            boxes, scores, self._confidence_threshold, self._nms_threshold
        )
        indices = np.asarray(kept).reshape(-1).tolist() if len(kept) else []
        return [PersonDetection(confidence=scores[i]) for i in indices]


def detector_from_environment() -> PersonDetector:
    """Create a detector only from explicit local configuration. Never download weights."""
    model_path = os.getenv("VISION_MODEL_PATH", "").strip()
    reviewed = os.getenv("VISION_MODEL_LICENSE_REVIEWED", "false").lower() == "true"
    if not model_path:
        return UnavailableDetector("MODEL_NOT_CONFIGURED")
    return YoloV8OnnxPersonDetector(
        model_path,
        confidence_threshold=float(os.getenv("VISION_CONFIDENCE_THRESHOLD", "0.45")),
        nms_threshold=float(os.getenv("VISION_NMS_THRESHOLD", "0.45")),
        expected_sha256=os.getenv("VISION_MODEL_SHA256") or None,
        license_reviewed=reviewed,
        model_name=os.getenv("VISION_MODEL_NAME", "local-onnx-person-detector"),
    )
