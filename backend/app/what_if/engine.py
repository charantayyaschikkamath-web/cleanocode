from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import os

from ..copilot.models import FactsSnapshot, Provenance, ReadingFact, SourceHealth
from .models import Intervention, WhatIfCompareRequest, WhatIfEstimate, WhatIfStatus

_SIX_DP = Decimal("0.000001")
_FOUR_DP = Decimal("0.0001")
_ZERO = Decimal("0")


def _round(value: Decimal, quantum: Decimal = _SIX_DP) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _watts(reading: ReadingFact) -> Decimal | None:
    if reading.value is None or not reading.unit:
        return None
    unit = reading.unit.strip().casefold().replace(" ", "")
    if unit in {"w", "watt", "watts"}:
        return reading.value
    if unit in {"kw", "kilowatt", "kilowatts"}:
        return reading.value * Decimal("1000")
    return None


def _latest_healthy_power(facts: FactsSnapshot, room_id: str) -> ReadingFact | None:
    candidates: list[ReadingFact] = []
    try:
        max_age_seconds = int(os.getenv("WHAT_IF_MAX_READING_AGE_SECONDS", "900"))
    except ValueError:
        max_age_seconds = 900
    max_age_seconds = min(max(max_age_seconds, 30), 86400)
    now = datetime.now(timezone.utc)
    for reading in facts.readings:
        room_matches = reading.room_id == room_id or (reading.location or "").strip().casefold() == room_id.casefold()
        if not room_matches:
            continue
        if reading.source_health != SourceHealth.HEALTHY or reading.observed_at is None or reading.observed_at.tzinfo is None:
            continue
        observed_at = reading.observed_at.astimezone(timezone.utc)
        age_seconds = (now - observed_at).total_seconds()
        # Scenario readings use accelerated virtual timestamps. Their wall-clock age is
        # not meaningful; evaluate their recorded source health/sample freshness instead.
        if reading.time_domain == "VIRTUAL":
            if reading.freshness_seconds is not None and reading.freshness_seconds > max_age_seconds:
                continue
        else:
            if age_seconds < -30 or age_seconds > max_age_seconds:
                continue
            if reading.freshness_seconds is not None and reading.freshness_seconds > max_age_seconds:
                continue
        if _watts(reading) is None or reading.provenance == Provenance.UNKNOWN:
            continue
        type_text = f"{reading.resource_type} {reading.reading_type or ''}".casefold()
        if not any(token in type_text for token in ("power", "electric", "energy")):
            continue
        candidates.append(reading)
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.observed_at.astimezone(timezone.utc))


def _calculate_one(
    request: WhatIfCompareRequest,
    intervention: Intervention,
    facts: FactsSnapshot,
) -> WhatIfEstimate:
    assumptions: list[str] = [
        "Projection assumes the baseline power level would otherwise remain constant for the requested duration.",
        "The requested reduction is a scenario input, not a detected or measured control response.",
        "No savings ledger entry is created by this endpoint.",
    ]
    missing: list[str] = []
    source_id: str | None = None

    if request.scenario_baseline_watts is not None:
        baseline_watts = request.scenario_baseline_watts
        provenance = Provenance.SIMULATED
        assumptions.append("Baseline power was manually entered for this scenario and is labelled SIMULATED.")
    else:
        reading = _latest_healthy_power(facts, request.room_id)
        if reading is None:
            baseline_watts = None
            provenance = Provenance.UNKNOWN
            missing.append("healthy, fresh power reading for the selected room")
        else:
            baseline_watts = _watts(reading)
            provenance = reading.provenance
            source_id = reading.id

    if baseline_watts is None or baseline_watts <= _ZERO:
        return WhatIfEstimate(
            name=intervention.name,
            reduction_percent=intervention.reduction_percent,
            status=WhatIfStatus.UNAVAILABLE,
            room_id=request.room_id,
            duration_hours=request.duration_hours,
            baseline_power_watts=baseline_watts,
            baseline_provenance=provenance,
            baseline_source_id=source_id,
            energy_tariff_per_kwh=facts.energy_tariff_per_kwh,
            co2_factor_kg_per_kwh=facts.co2_factor_kg_per_kwh,
            assumptions=assumptions,
            missing_inputs=missing or ["positive power baseline"],
            source_ids=[source_id] if source_id else [],
        )

    baseline_kwh = baseline_watts / Decimal("1000") * request.duration_hours
    fraction = intervention.reduction_percent / Decimal("100")
    avoided_kwh = baseline_kwh * fraction
    remaining_kwh = baseline_kwh - avoided_kwh
    cost = avoided_kwh * facts.energy_tariff_per_kwh if facts.energy_tariff_per_kwh is not None else None
    co2 = avoided_kwh * facts.co2_factor_kg_per_kwh if facts.co2_factor_kg_per_kwh is not None else None
    if facts.energy_tariff_per_kwh is None:
        missing.append("configured energy tariff; projected cost is unavailable")
    if facts.co2_factor_kg_per_kwh is None:
        missing.append("configured CO₂ factor; projected emissions are unavailable")
    if provenance != Provenance.REAL:
        assumptions.append(f"Baseline provenance is {provenance.value}; treat the result as a scenario projection.")

    return WhatIfEstimate(
        name=intervention.name,
        reduction_percent=intervention.reduction_percent,
        status=WhatIfStatus.CALCULATED,
        room_id=request.room_id,
        duration_hours=request.duration_hours,
        baseline_power_watts=_round(baseline_watts, _FOUR_DP),
        baseline_provenance=provenance,
        baseline_source_id=source_id,
        baseline_energy_kwh=_round(baseline_kwh),
        projected_avoided_energy_kwh=_round(avoided_kwh),
        projected_remaining_energy_kwh=_round(remaining_kwh),
        projected_cost_avoided=_round(cost, _FOUR_DP) if cost is not None else None,
        cost_currency=facts.energy_tariff_currency if cost is not None else None,
        projected_co2_avoided_kg=_round(co2) if co2 is not None else None,
        energy_tariff_per_kwh=facts.energy_tariff_per_kwh,
        co2_factor_kg_per_kwh=facts.co2_factor_kg_per_kwh,
        assumptions=assumptions,
        missing_inputs=missing,
        source_ids=[source_id] if source_id else [],
    )


def calculate_comparison(request: WhatIfCompareRequest, facts: FactsSnapshot) -> list[WhatIfEstimate]:
    """Return deterministic projections only; never mutates action or savings records."""
    return [_calculate_one(request, intervention, facts) for intervention in request.interventions]


def build_single_request(
    *, room_id: str, duration_hours: Decimal, scenario_baseline_watts: Decimal | None,
    intervention_name: str, reduction_percent: Decimal,
) -> WhatIfCompareRequest:
    return WhatIfCompareRequest(
        room_id=room_id,
        duration_hours=duration_hours,
        scenario_baseline_watts=scenario_baseline_watts,
        interventions=[Intervention(name=intervention_name, reduction_percent=reduction_percent)],
    )
