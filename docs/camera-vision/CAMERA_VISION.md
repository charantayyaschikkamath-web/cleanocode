# Camera/Vision Operational Notes

## Camera states

- `AVAILABLE`: a frame passed the local image-quality gate and inference returned a defined person count.
- `UNKNOWN`: a frame could not safely support an occupancy claim (e.g. invalid image, dark/low-variation image, inference error, stale frame).
- `UNAVAILABLE`: the local detector/model/runtime is not ready.
- `PERSON_DETECTED`: a person was detected in current or recent valid frames. This immediately resets the likely-empty timer.
- `NO_PERSON_DETECTED`: valid inference detected no person in the smoothed window. This is not proof of empty occupancy and should be used only as one time-bounded signal when camera coverage is confirmed.

## Smoothing

The detector emits a raw count per accepted frame. The module stores only counts in a bounded in-memory deque and calculates the rolling median over the most recent `VISION_SMOOTHING_WINDOW` frames (default 5). Fractional medians are rounded upward to avoid rounding away a possible person. If the current raw count is positive, `PERSON_DETECTED` is emitted immediately even if the median is zero. Otherwise, a positive rolling median keeps the room signal occupied briefly after a detection. Only the counts/derived metadata are eligible for persistence; no frame is buffered for retry.

## Conservative frame checks

Before inference, image decode must succeed and dimensions must be within configured limits. Very dark or nearly uniform frames return `UNKNOWN`, with an explanatory reason code. These checks can detect some unusable views, but they cannot reliably identify all coverings, reflections, camera misalignment, or blind spots. Coverage is therefore a manual attestation. When in doubt, return unknown.

## Local model setup

Expected adapter: local YOLOv8-style COCO-80 ONNX output where class 0 is person and the first four fields are center-x, center-y, width, height in model-input coordinates. Supported prediction layouts: `[1,84,N]` and `[1,N,84]`. No other class or identity output is used or exposed. Unsupported outputs fail closed.

No model weights are bundled. Before enabling inference, record:

- exact model name/version and publisher/source URL;
- SHA-256 of the exact weight file;
- code and weight license, attribution, redistribution/use rights, and any copyleft/commercial implications;
- export/preprocessing/output-shape assumptions and known limitations;
- evaluation dataset license and test procedure if evaluation is later run.

Don't assume ONNX conversion erases the license of original code or model weights. Avoid adding identity, face-analysis, gender/age/emotion or tracking capabilities.
