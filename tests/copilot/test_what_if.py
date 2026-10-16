from __future__ import annotations

from decimal import Decimal

import pytest

from app.copilot.config import CopilotSettings
from app.copilot.models import CopilotMode, FactsSnapshot, Provenance, ReadingFact, SourceHealth
from app.copilot.service import CopilotService
from app.what_if.engine import build_single_request, calculate_comparison
from app.what_if.models import Intervention, WhatIfCompareRequest, WhatIfStatus


def test_manual_baseline_1000w_two_hours_25_percent(facts):
    request = WhatIfCompareRequest(
        room_id="B1-R101",
        duration_hours=Decimal("2"),
        scenario_baseline_watts=Decimal("1000"),
        interventions=[Intervention(name="Moderate", reduction_percent=Decimal("25"))],
    )
    item = calculate_comparison(request, facts)[0]
    assert item.status == WhatIfStatus.CALCULATED
    assert item.baseline_provenance == Provenance.SIMULATED
    assert item.baseline_energy_kwh == Decimal("2.000000")
    assert item.projected_avoided_energy_kwh == Decimal("0.500000")
    assert item.projected_remaining_energy_kwh == Decimal("1.500000")
    assert item.projected_cost_avoided == Decimal("5.0000")
    assert item.projected_co2_avoided_kg == Decimal("0.400000")
    assert item.impact_status == "PROJECTED_NOT_VERIFIED"


def test_uses_latest_healthy_room_power_reading_when_baseline_is_not_manual(facts):
    request = WhatIfCompareRequest(
        room_id="B1-R101",
        duration_hours=Decimal("2"),
        interventions=[Intervention(name="Moderate", reduction_percent=Decimal("25"))],
    )
    item = calculate_comparison(request, facts)[0]
    assert item.status == WhatIfStatus.CALCULATED
    assert item.baseline_power_watts == Decimal("1000.0000")
    assert item.baseline_source_id == "reading-power-1"
    assert item.baseline_provenance == Provenance.SIMULATED


def test_stale_or_unknown_baseline_does_not_guess(facts):
    facts.readings[0].source_health = SourceHealth.STALE
    request = WhatIfCompareRequest(
        room_id="B1-R101",
        duration_hours=Decimal("2"),
        interventions=[Intervention(name="Moderate", reduction_percent=Decimal("25"))],
    )
    item = calculate_comparison(request, facts)[0]
    assert item.status == WhatIfStatus.UNAVAILABLE
    assert item.projected_avoided_energy_kwh is None
    assert any("healthy" in value for value in item.missing_inputs)


def test_missing_tariff_and_emissions_factor_stays_unavailable(facts):
    facts.energy_tariff_per_kwh = None
    facts.co2_factor_kg_per_kwh = None
    request = WhatIfCompareRequest(
        room_id="B1-R101",
        duration_hours=Decimal("2"),
        scenario_baseline_watts=Decimal("1000"),
        interventions=[Intervention(name="Moderate", reduction_percent=Decimal("25"))],
    )
    item = calculate_comparison(request, facts)[0]
    assert item.projected_avoided_energy_kwh == Decimal("0.500000")
    assert item.projected_cost_avoided is None
    assert item.projected_co2_avoided_kg is None
    assert any("tariff" in value for value in item.missing_inputs)
    assert any("CO₂" in value for value in item.missing_inputs)


@pytest.mark.asyncio
async def test_what_if_narrative_works_without_api_key(facts, tmp_path):
    settings = CopilotSettings(api_base_url=None, api_key=None, model=None, cache_path=str(tmp_path / "cache.json"))
    service = CopilotService(settings=settings)
    result = {
        "room_id": "B1-R101",
        "duration_hours": "2",
        "comparisons": [{"projected_avoided_energy_kwh": "0.500000", "impact_status": "PROJECTED_NOT_VERIFIED"}],
    }
    narrative, mode, _ = await service.explain_what_if(result, facts)
    assert mode == CopilotMode.TEMPLATE
    assert len(narrative.lines) == 3
    assert "projection" in narrative.summary.lower()


def test_healthy_label_does_not_override_wall_clock_staleness(facts):
    from datetime import timedelta
    facts.readings[0].source_health = SourceHealth.HEALTHY
    facts.readings[0].observed_at = facts.readings[0].observed_at - timedelta(days=3)
    request = WhatIfCompareRequest(
        room_id="B1-R101",
        duration_hours=Decimal("2"),
        interventions=[Intervention(name="Moderate", reduction_percent=Decimal("25"))],
    )
    item = calculate_comparison(request, facts)[0]
    assert item.status == WhatIfStatus.UNAVAILABLE
    assert item.baseline_power_watts is None
