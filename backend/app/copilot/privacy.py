from __future__ import annotations

import re

# This is deliberate minimisation, not a claim of full named-entity recognition. The
# facts adapter must still avoid person fields and camera frames entirely.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE), "[REDACTED_URL]"),
    (re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)"), "[REDACTED_PHONE_OR_NUMBER]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
    (re.compile(r"\b(?:email|e-mail|phone|mobile|contact|student\s*id|employee\s*id)\s*[:=]\s*[^\s,;]+", re.IGNORECASE), "[REDACTED_CONTACT_FIELD]"),
)


def redact_sensitive_text(value: str | None, max_length: int = 1200) -> str | None:
    if value is None:
        return None
    result = value
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result[:max_length]
