# Third-Party / Model License Review Notes

This module intentionally ships no detection model, training dataset, or model weights. The operator must review the exact model artifact and its origin before enabling real inference.

- OpenCV 4.5.0 and newer are licensed under Apache 2.0 according to the [official OpenCV license page](https://opencv.org/license/).
- ONNX Runtime is licensed under MIT according to the [official ONNX Runtime repository](https://github.com/microsoft/onnxruntime). Its official documentation also describes platform-specific telemetry controls; this adapter calls `onnxruntime.disable_telemetry_events()` when the installed build exposes it, but the final pinned runtime/platform still needs verification against the [official Python API index](https://onnxruntime.ai/docs/api/python/genindex.html).
- Ultralytics' official licensing page describes AGPL-3.0 and Enterprise licensing options for its code/models and states that proprietary/commercial/private uses can require the Enterprise license. This project therefore does not import the Ultralytics Python package or bundle Ultralytics weights. If a YOLO-derived model is selected, review the exact weight/model license and obtain legal review where appropriate: [Ultralytics licensing](https://www.ultralytics.com/license).

Using ONNX Runtime to execute a converted model does not automatically change the original model's licensing obligations. Add model URL, exact version/hash, license text/reference, attribution and intended use to the main project's `docs/THIRD_PARTY_NOTICES.md` before committing or distributing any model artifact.
