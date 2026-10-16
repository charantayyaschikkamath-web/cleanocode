from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class CopilotSettings:
    """Runtime settings. Secrets are read only on the backend and never serialized."""

    api_base_url: str | None
    api_key: str | None
    model: str | None
    timeout_seconds: float = 8.0
    cache_path: str = "data/copilot_report_cache.json"
    max_context_records: int = 40

    @classmethod
    def from_env(cls) -> "CopilotSettings":
        base_url = os.getenv("COPILOT_API_BASE_URL", "").strip() or None
        api_key = os.getenv("COPILOT_API_KEY", "").strip() or None
        model = os.getenv("COPILOT_MODEL", "").strip() or None
        try:
            timeout = float(os.getenv("COPILOT_TIMEOUT_SECONDS", "8"))
        except ValueError:
            timeout = 8.0
        timeout = min(max(timeout, 1.0), 25.0)
        try:
            max_records = int(os.getenv("COPILOT_MAX_CONTEXT_RECORDS", "40"))
        except ValueError:
            max_records = 40
        max_records = min(max(max_records, 5), 100)
        return cls(
            api_base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout,
            cache_path=os.getenv("COPILOT_CACHE_PATH", "data/copilot_report_cache.json"),
            max_context_records=max_records,
        )

    @property
    def provider_configured(self) -> bool:
        return bool(self.api_base_url and self.api_key and self.model)

    def validated_completion_url(self) -> str:
        if not self.provider_configured:
            raise ValueError("LLM provider is not configured")
        assert self.api_base_url is not None
        parsed = urlsplit(self.api_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("COPILOT_API_BASE_URL must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("provider URL must not contain credentials, query parameters, or fragments")
        base = self.api_base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"
