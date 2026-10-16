from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from ..copilot.models import StrictModel, Provenance, CopilotMode, FactsGrounding, FactReference, Recommendation


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Intervention(StrictModel):
    name: str = Field(min_length=2, max_length=100)
    reduction_percent: Decimal = Field(gt=0, le=100, max_digits=6, decimal_places=3)


class WhatIfCompareRequest(StrictModel):
    room_id: str = Field(min_length=1, max_length=120)
    duration_hours: Decimal = Field(gt=0, le=168, max_digits=8, decimal_places=3)
    # Explicitly manual input. When present, this is always treated as a SIMULATED assumption.
    scenario_baseline_watts: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=4)
    interventions: list[Intervention] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def unique_intervention_names(self) -> "WhatIfCompareRequest":
        names = [item.name.strip().casefold() for item in self.interventions]
        if len(names) != len(set(names)):
            raise ValueError("intervention names must be unique")
        return self


class WhatIfRunRequest(StrictModel):
    room_id: str = Field(min_length=1, max_length=120)
    duration_hours: Decimal = Field(gt=0, le=168, max_digits=8, decimal_places=3)
    scenario_baseline_watts: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=4)
    intervention_name: str = Field(default="Proposed reduction", min_length=2, max_length=100)
    reduction_percent: Decimal = Field(gt=0, le=100, max_digits=6, decimal_places=3)


class WhatIfStatus(str, Enum):
    CALCULATED = "CALCULATED"
    UNAVAILABLE = "UNAVAILABLE"


class WhatIfEstimate(StrictModel):
    name: str
    reduction_percent: Decimal
    status: WhatIfStatus
    room_id: str
    duration_hours: Decimal
    baseline_power_watts: Decimal | None = None
    baseline_provenance: Provenance = Provenance.UNKNOWN
    baseline_source_id: str | None = None
    baseline_energy_kwh: Decimal | None = None
    projected_avoided_energy_kwh: Decimal | None = None
    projected_remaining_energy_kwh: Decimal | None = None
    projected_cost_avoided: Decimal | None = None
    cost_currency: str | None = None
    projected_co2_avoided_kg: Decimal | None = None
    energy_tariff_per_kwh: Decimal | None = None
    co2_factor_kg_per_kwh: Decimal | None = None
    assumptions: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    impact_status: Literal["PROJECTED_NOT_VERIFIED"] = "PROJECTED_NOT_VERIFIED"


class WhatIfResponse(StrictModel):
    generated_at: datetime = Field(default_factory=utc_now)
    mode: CopilotMode
    summary: str
    explanation_lines: list[str] = Field(min_length=3, max_length=3)
    comparisons: list[WhatIfEstimate] = Field(min_length=1, max_length=3)
    grounding: FactsGrounding
    fact_references: list[FactReference] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
