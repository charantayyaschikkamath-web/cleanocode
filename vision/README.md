# Model Artifact Policy

This directory intentionally contains no model weights or datasets. Keep model artifacts outside version control unless Account 1/8 has approved their exact source, hash, license, redistribution terms and intended use.

Expected input for the adapter is a single RGB-normalized NCHW tensor produced from a letterboxed browser JPEG. Expected output is one YOLOv8-style COCO-80 tensor of shape `[1, 84, N]` or `[1, N, 84]`, with class index `0` representing `person`. The adapter runs CPU-only via ONNX Runtime and refuses other tensor layouts.

Before enabling a local model, set `VISION_MODEL_PATH`, `VISION_MODEL_SHA256`, and `VISION_MODEL_LICENSE_REVIEWED=true` only after reviewing the exact artifact's license. The app does not auto-download weights. The operator should record the model name/version, upstream URL, export method, SHA-256, license and limitations in the main repository's `docs/THIRD_PARTY_NOTICES.md`.
