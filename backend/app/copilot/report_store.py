from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import ReportArtifactMetadata, ReportFormat

_ID_PATTERN = re.compile(r"^report-[a-f0-9]{32}$")


class ReportNotFoundError(LookupError):
    pass


class ReportStore:
    """Small atomic filesystem store for generated report artifacts and metadata.

    The root is configured by COPILOT_REPORTS_DIR. Public responses expose only an
    API download reference, never the local path. Report IDs are generated here and
    are validated before any path is constructed.
    """

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("COPILOT_REPORTS_DIR", "data/reports")).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _report_dir(self, report_id: str) -> Path:
        if not _ID_PATTERN.fullmatch(report_id):
            raise ReportNotFoundError("Report was not found")
        path = (self.root / report_id).resolve()
        if path.parent != self.root:
            raise ReportNotFoundError("Report was not found")
        return path

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".report-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def create(self, metadata: ReportArtifactMetadata, artifacts: dict[ReportFormat, str]) -> ReportArtifactMetadata:
        report_dir = self._report_dir(metadata.id)
        report_dir.mkdir(parents=True, exist_ok=False)
        suffixes = {ReportFormat.JSON: "json", ReportFormat.CSV: "csv", ReportFormat.HTML: "html"}
        try:
            for fmt, content in artifacts.items():
                self._atomic_write(report_dir / f"report.{suffixes[fmt]}", content)
            self._atomic_write(report_dir / "metadata.json", metadata.model_dump_json(indent=2))
        except Exception:
            # A partially created report should never be returned as successful.
            for child in report_dir.glob("*"):
                try:
                    child.unlink()
                except OSError:
                    pass
            try:
                report_dir.rmdir()
            except OSError:
                pass
            raise
        return metadata

    def get_metadata(self, report_id: str) -> ReportArtifactMetadata:
        report_dir = self._report_dir(report_id)
        metadata_path = report_dir / "metadata.json"
        if not metadata_path.is_file():
            raise ReportNotFoundError("Report was not found")
        try:
            return ReportArtifactMetadata.model_validate_json(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ReportNotFoundError("Report metadata is unavailable") from exc

    def get_artifact(self, report_id: str, fmt: ReportFormat) -> tuple[str, str, str]:
        # Metadata existence gates access and prevents serving arbitrary filesystem paths.
        metadata = self.get_metadata(report_id)
        if fmt not in metadata.available_formats:
            raise ReportNotFoundError("Requested format was not generated")
        suffixes = {ReportFormat.JSON: "json", ReportFormat.CSV: "csv", ReportFormat.HTML: "html"}
        media_types = {
            ReportFormat.JSON: "application/json; charset=utf-8",
            ReportFormat.CSV: "text/csv; charset=utf-8",
            ReportFormat.HTML: "text/html; charset=utf-8",
        }
        path = self._report_dir(report_id) / f"report.{suffixes[fmt]}"
        if not path.is_file():
            raise ReportNotFoundError("Report artifact is unavailable")
        return path.read_text(encoding="utf-8"), media_types[fmt], f"campustwin-{report_id}.{suffixes[fmt]}"


def new_report_id() -> str:
    return f"report-{uuid.uuid4().hex}"


def utc_period(start: datetime | None, end: datetime | None, default_end: datetime | None = None) -> tuple[datetime, datetime]:
    """Resolve a supplied half-open UTC interval, or default to the prior seven days."""
    if start is None and end is None:
        period_end = default_end or datetime.now(timezone.utc)
        if period_end.tzinfo is None:
            raise ValueError("period_end must be timezone-aware")
        period_end = period_end.astimezone(timezone.utc)
        return period_end.replace(microsecond=0) - timedelta(days=7), period_end
    if start is None or end is None:
        raise ValueError("period_start and period_end must be supplied together")
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("report periods must be timezone-aware UTC timestamps")
    period_start = start.astimezone(timezone.utc)
    period_end = end.astimezone(timezone.utc)
    if period_start >= period_end:
        raise ValueError("period_start must be earlier than period_end")
    return period_start, period_end
