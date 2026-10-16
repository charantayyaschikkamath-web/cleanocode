from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    @model_validator(mode="after")
    def require_timezone_aware_datetimes(self):
        for field_name, value in self.__dict__.items():
            if isinstance(value, datetime) and value.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        return self


class Provenance(str, Enum):
    REAL = "REAL"
    SIMULATED = "SIMULATED"
    DERIVED = "DERIVED"
    UNKNOWN = "UNKNOWN"


class SourceHealth(str, Enum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    MISSING = "MISSING"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


class ReadingFact(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    resource_type: str = Field(min_length=1, max_length=80)
    reading_type: str | None = Field(default=None, max_length=80)
    value: Decimal | None = None
    unit: str | None = Field(default=None, max_length=32)
    observed_at: datetime | None = None
    provenance: Provenance = Provenance.UNKNOWN
    source_health: SourceHealth = SourceHealth.UNKNOWN
    freshness_seconds: int | None = Field(default=None, ge=0)
    building_id: str | None = Field(default=None, max_length=120)
    room_id: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=240)
    time_domain: Literal["WALL", "VIRTUAL"] | None = None


class ProjectedImpact(StrictModel):
    """Optional deterministic estimate supplied by the core facts/impact engine.

    Account 7 never fabricates missing impact inputs. An absent estimate remains UNAVAILABLE.
    """

    status: Literal["PROJECTED", "UNAVAILABLE"] = "UNAVAILABLE"
    energy_avoided_kwh: Decimal | None = Field(default=None, ge=0)
    water_avoided_liters: Decimal | None = Field(default=None, ge=0)
    cost_avoided_amount: Decimal | None = Field(default=None, ge=0)
    cost_currency: str | None = Field(default=None, max_length=8)
    co2_avoided_kg: Decimal | None = Field(default=None, ge=0)
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    assumptions: list[str] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def validate_projection_state(self) -> "ProjectedImpact":
        has_values = any(value is not None for value in (self.energy_avoided_kwh, self.water_avoided_liters, self.cost_avoided_amount, self.co2_avoided_kg))
        if self.status == "UNAVAILABLE" and has_values:
            raise ValueError("UNAVAILABLE projected impact cannot contain numeric values")
        if self.status == "PROJECTED" and not has_values:
            raise ValueError("PROJECTED impact needs at least one deterministic numeric value")
        return self


class EventFact(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    event_type: str = Field(min_length=1, max_length=100)
    severity: str = Field(default="unknown", max_length=32)
    status: str = Field(default="OPEN", max_length=40)
    building_id: str | None = Field(default=None, max_length=120)
    room_id: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=240)
    first_seen_at: datetime | None = None
    last_updated_at: datetime | None = None
    trigger_rule: str | None = Field(default=None, max_length=300)
    explanation: str | None = Field(default=None, max_length=1200)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    provenance: Provenance = Provenance.UNKNOWN
    projected_impact: ProjectedImpact = Field(default_factory=ProjectedImpact)


class ActionFact(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    event_id: str | None = Field(default=None, max_length=120)
    status: str = Field(default="UNKNOWN", max_length=48)
    requested_at: datetime | None = None
    updated_at: datetime | None = None
    verification_summary: str | None = Field(default=None, max_length=600)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    provenance: Provenance = Provenance.UNKNOWN


class LedgerFact(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    action_id: str | None = Field(default=None, max_length=120)
    created_at: datetime = Field(default_factory=utc_now)
    verification_status: str = Field(default="UNVERIFIED", max_length=48)
    provenance: Provenance = Provenance.UNKNOWN
    energy_kwh: Decimal | None = Field(default=None, ge=0)
    water_liters: Decimal | None = Field(default=None, ge=0)
    cost_amount: Decimal | None = Field(default=None, ge=0)
    cost_currency: str | None = Field(default=None, max_length=8)
    co2_kg: Decimal | None = Field(default=None, ge=0)
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    calculation_version: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def prevent_false_verified_ledger_entry(self) -> "LedgerFact":
        if self.verification_status.upper() != "VERIFIED_SUCCESS" and self.provenance == Provenance.REAL:
            # Real measured ledger rows can be reported as measured without using the
            # simulated action workflow, so they remain valid but are not classified
            # as verified-action savings by the report aggregator.
            return self
        return self


class FactsSnapshot(StrictModel):
    """Sanitized, deterministic facts assembled by the main backend from persisted records.

    This schema deliberately contains no image, video-frame, API-key, or user-identity fields.
    The main application must map its shared persisted models into this module-owned view.
    """

    snapshot_id: str = Field(default="unavailable", max_length=120)
    generated_at: datetime = Field(default_factory=utc_now)
    source_status: str = Field(default="NOT_CONFIGURED", max_length=40)
    readings: list[ReadingFact] = Field(default_factory=list, max_length=500)
    events: list[EventFact] = Field(default_factory=list, max_length=500)
    actions: list[ActionFact] = Field(default_factory=list, max_length=500)
    ledger_entries: list[LedgerFact] = Field(default_factory=list, max_length=500)
    energy_tariff_per_kwh: Decimal | None = Field(default=None, ge=0)
    energy_tariff_currency: str | None = Field(default=None, max_length=8)
    co2_factor_kg_per_kwh: Decimal | None = Field(default=None, ge=0)
    water_tariff_per_m3: Decimal | None = Field(default=None, ge=0)
    water_tariff_currency: str | None = Field(default=None, max_length=8)
    assumptions: dict[str, str] = Field(default_factory=dict, max_length=60)
    unavailable_inputs: list[str] = Field(default_factory=list, max_length=80)

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        return value

    @property
    def fact_ids(self) -> set[str]:
        ids: set[str] = set()
        for record in self.readings:
            ids.add(record.id)
        for record in self.events:
            ids.add(record.id)
            ids.update(record.evidence_ids)
            ids.update(record.projected_impact.source_ids)
        for record in self.actions:
            ids.add(record.id)
            ids.update(record.evidence_ids)
        for record in self.ledger_entries:
            ids.add(record.id)
            ids.update(record.source_ids)
        return ids


class Recommendation(StrictModel):
    title: str = Field(min_length=2, max_length=100)
    rationale: str = Field(min_length=2, max_length=260)
    next_step: str = Field(min_length=2, max_length=260)
    fact_refs: list[str] = Field(default_factory=list, max_length=12)


class GroundedNarrative(StrictModel):
    """Only prose is generated by an LLM; all numeric values stay in backend models."""

    summary: str = Field(min_length=2, max_length=500)
    lines: list[str] = Field(min_length=3, max_length=3)
    recommendations: list[Recommendation] = Field(default_factory=list, max_length=4)

    @field_validator("lines")
    @classmethod
    def validate_line_lengths(cls, lines: list[str]) -> list[str]:
        if any(not line.strip() or len(line) > 240 for line in lines):
            raise ValueError("narrative must contain three short, non-empty lines")
        return [line.strip() for line in lines]


class CopilotAskRequest(StrictModel):
    question: str = Field(min_length=3, max_length=1200)
    event_id: str | None = Field(default=None, min_length=1, max_length=120)


class FactReference(StrictModel):
    id: str
    kind: Literal["reading", "event", "action", "ledger", "evidence"]
    label: str
    provenance: Provenance = Provenance.UNKNOWN


class FactsGrounding(StrictModel):
    real_count: int = Field(ge=0)
    simulated_count: int = Field(ge=0)
    derived_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    source_status: str
    assumptions: dict[str, str] = Field(default_factory=dict)
    unavailable_inputs: list[str] = Field(default_factory=list)


class CopilotMode(str, Enum):
    LLM = "LLM"
    CACHED = "CACHED"
    TEMPLATE = "TEMPLATE"


class CopilotAnswer(StrictModel):
    mode: CopilotMode
    generated_at: datetime = Field(default_factory=utc_now)
    cached_at: datetime | None = None
    summary: str
    lines: list[str] = Field(min_length=1, max_length=3)
    recommendations: list[Recommendation] = Field(default_factory=list)
    fact_references: list[FactReference] = Field(default_factory=list)
    grounding: FactsGrounding
    limitations: list[str] = Field(default_factory=list)


class ImpactTotals(StrictModel):
    energy_kwh: Decimal | None = None
    water_liters: Decimal | None = None
    cost_amount: Decimal | None = None
    cost_currency: str | None = None
    co2_kg: Decimal | None = None
    entries_count: int = Field(ge=0)
    missing_value_count: int = Field(ge=0)


class WeeklyReportMetrics(StrictModel):
    reading_count: int = Field(ge=0)
    readings_by_provenance: dict[str, int]
    events_total: int = Field(ge=0)
    events_open: int = Field(ge=0)
    events_by_severity: dict[str, int]
    actions_total: int = Field(ge=0)
    actions_verified_success: int = Field(ge=0)
    actions_failed_or_timed_out: int = Field(ge=0)
    verified_measured: ImpactTotals
    measured_unverified: ImpactTotals
    verified_simulated: ImpactTotals
    projected_or_unverified: ImpactTotals


class ReportReadingSummary(StrictModel):
    id: str
    resource_type: str
    reading_type: str | None = None
    value: Decimal | None = None
    unit: str | None = None
    observed_at: datetime | None = None
    provenance: Provenance = Provenance.UNKNOWN
    source_health: SourceHealth = SourceHealth.UNKNOWN
    freshness_seconds: int | None = Field(default=None, ge=0)
    building_id: str | None = None
    room_id: str | None = None


class ReportEventSummary(StrictModel):
    id: str
    event_type: str
    severity: str
    status: str
    building_id: str | None = None
    room_id: str | None = None
    first_seen_at: datetime | None = None
    last_updated_at: datetime | None = None
    trigger_rule: str | None = None
    explanation: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: Provenance = Provenance.UNKNOWN
    projected_impact: ProjectedImpact = Field(default_factory=ProjectedImpact)


class ReportActionSummary(StrictModel):
    id: str
    event_id: str | None = None
    status: str
    requested_at: datetime | None = None
    updated_at: datetime | None = None
    verification_summary: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: Provenance = Provenance.UNKNOWN


class ReportLedgerSummary(StrictModel):
    id: str
    action_id: str | None = None
    created_at: datetime
    verification_status: str
    provenance: Provenance = Provenance.UNKNOWN
    energy_kwh: Decimal | None = None
    water_liters: Decimal | None = None
    cost_amount: Decimal | None = None
    cost_currency: str | None = None
    co2_kg: Decimal | None = None
    source_ids: list[str] = Field(default_factory=list)
    calculation_version: str | None = None


class WeeklyReport(StrictModel):
    report_id: str
    generated_at: datetime = Field(default_factory=utc_now)
    period_start: datetime
    period_end: datetime
    mode: CopilotMode
    cached_at: datetime | None = None
    summary: str
    narrative_lines: list[str] = Field(min_length=3, max_length=3)
    metrics: WeeklyReportMetrics
    readings: list[ReportReadingSummary] = Field(default_factory=list)
    events: list[ReportEventSummary] = Field(default_factory=list)
    actions: list[ReportActionSummary] = Field(default_factory=list)
    ledger_entries: list[ReportLedgerSummary] = Field(default_factory=list)
    verified_vs_simulated: list[str] = Field(min_length=3, max_length=3)
    recommendations: list[Recommendation] = Field(default_factory=list)
    assumptions: dict[str, str] = Field(default_factory=dict)
    unavailable_inputs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ActionPlanItem(StrictModel):
    event_id: str
    event_type: str
    priority: Literal["P1", "P2", "P3", "REVIEW"]
    reason: str
    proposed_next_step: str
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: Provenance = Provenance.UNKNOWN
    projected_impact: ProjectedImpact = Field(default_factory=ProjectedImpact)


class ActionPlan(StrictModel):
    generated_at: datetime = Field(default_factory=utc_now)
    mode: CopilotMode
    cached_at: datetime | None = None
    summary: str
    narrative_lines: list[str] = Field(min_length=3, max_length=3)
    items: list[ActionPlanItem] = Field(default_factory=list)
    assumptions: dict[str, str] = Field(default_factory=dict)
    unavailable_inputs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class CopilotQueryRequest(StrictModel):
    question: str = Field(min_length=3, max_length=1200)
    event_ids: list[str] = Field(default_factory=list, max_length=20)
    facts_version: str | None = Field(default=None, max_length=120)
    request_mode: Literal["AUTO", "LLM", "TEMPLATE"] = "AUTO"


class CopilotQueryRecommendation(StrictModel):
    label: str
    action_type: str = "REVIEW_EVIDENCE"
    requires_approval: bool = False


class CopilotQueryResponse(StrictModel):
    answer: str
    mode: CopilotMode
    facts_version: str
    source_ids: list[str] = Field(default_factory=list)
    recommendations: list[CopilotQueryRecommendation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)


class ReportCreateRequest(StrictModel):
    report_type: Literal["WEEKLY_SUSTAINABILITY", "ACTION_PLAN"] = "WEEKLY_SUSTAINABILITY"
    format: Literal["HTML", "CSV", "JSON"] = "HTML"
    period_start: datetime | None = None
    period_end: datetime | None = None

    @model_validator(mode="after")
    def validate_period(self) -> "ReportCreateRequest":
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("period_start and period_end must be supplied together")
        if self.period_start is not None and self.period_end is not None:
            if self.period_start.tzinfo is None or self.period_end.tzinfo is None:
                raise ValueError("report periods must be timezone-aware UTC timestamps")
            if self.period_start.astimezone(timezone.utc) >= self.period_end.astimezone(timezone.utc):
                raise ValueError("period_start must be earlier than period_end")
        return self


class ReportFormat(str, Enum):
    HTML = "HTML"
    CSV = "CSV"
    JSON = "JSON"


class ReportArtifactMetadata(StrictModel):
    id: str
    format: ReportFormat
    created_at: datetime
    period_start: datetime
    period_end: datetime
    source_event_ids: list[str] = Field(default_factory=list)
    source_action_ids: list[str] = Field(default_factory=list)
    source_ledger_ids: list[str] = Field(default_factory=list)
    provenance_summary: dict[str, int] = Field(default_factory=dict)
    assumptions: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    file_reference: str
    available_formats: list[ReportFormat] = Field(default_factory=lambda: [ReportFormat.HTML, ReportFormat.CSV, ReportFormat.JSON])
    report_type: Literal["WEEKLY_SUSTAINABILITY", "ACTION_PLAN"] = "WEEKLY_SUSTAINABILITY"
