from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


class LastGoodNarrativeCache:
    """Tiny atomic cache for validated, facts-only narrative fragments.

    User questions and raw facts are deliberately not cached. The cache is optional; all
    filesystem errors degrade to a deterministic TEMPLATE response.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = RLock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                return None
            item = payload.get(key) if isinstance(payload, dict) else None
            if not isinstance(item, dict) or not isinstance(item.get("narrative"), dict):
                return None
            if not isinstance(item.get("created_at"), str):
                return None
            return item

    def set(self, key: str, narrative: dict[str, Any]) -> None:
        # Keep only schema-owned fields. Never write questions, API credentials, frames or facts.
        allowed = {
            "summary": narrative.get("summary"),
            "lines": narrative.get("lines"),
            "recommendations": narrative.get("recommendations", []),
        }
        payload: dict[str, Any] = {}
        with self._lock:
            try:
                if self.path.exists():
                    existing = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(existing, dict):
                        payload.update(existing)
            except (OSError, ValueError, TypeError):
                payload = {}
            payload[key] = {"created_at": datetime.now(timezone.utc).isoformat(), "narrative": allowed}
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
                    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                    handle.flush()
                    os.fsync(handle.fileno())
                    temporary = Path(handle.name)
                os.replace(temporary, self.path)
            except OSError:
                try:
                    temporary.unlink(missing_ok=True)  # type: ignore[possibly-undefined]
                except (OSError, UnboundLocalError):
                    pass
