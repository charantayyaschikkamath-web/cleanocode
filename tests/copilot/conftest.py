from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.copilot.config import CopilotSettings
from app.copilot.models import (
    ActionFact,
    EventFact,
    FactsSnapshot,
    LedgerFact,
    Provenance,
    ReadingFact,
    SourceHealth,
)
from app.copilot.service import CopilotService
from app.copilot.cache import LastGoodNarrativeCache


@pytest.fixture
def facts() -> FactsSnapshot:
    now = datetime.now(timezone.utc)
    return FactsSnapshot(
        snapshot_id="snap-test",
        generated_at=now,
        source_status="HEALTHY",
        readings=[
            ReadingFact(
                id="reading-power-1",
                resource_type="power",
                reading_type="power",
                value=Decimal("1000"),
                unit="W",
                observed_at=now,
                provenance=Provenance.SIMULATED,
                source_health=SourceHealth.HEALTHY,
                freshness_seconds=1,
                building_id="B1",
                room_id="B1-R101",
                location="B1-R101",
            ),
        ],
        events=[
            EventFact(
                id="event-energy-1",
                event_type="likely_energy_waste",
                severity="high",
                status="OPEN",
                building_id="B1",
                room_id="B1-R101",
                location="Building one / Room 101",
                first_seen_at=now,
                last_updated_at=now,
                trigger_rule="occupancy likely empty while power remains above threshold",
                explanation="Power remained above the configured threshold while occupancy evidence suggested the room may be empty.",
                evidence_ids=["reading-power-1"],
                provenance=Provenance.SIMULATED,
            ),
        ],
        actions=[
            ActionFact(
                id="action-failed-1",
                event_id="event-energy-1",
                status="VERIFICATION_FAILED",
                requested_at=now,
                updated_at=now,
                verification_summary="Post-action reading did not satisfy the required change.",
                evidence_ids=["reading-power-1"],
                provenance=Provenance.SIMULATED,
            ),
        ],
        ledger_entries=[
            LedgerFact(
                id="ledger-verified-1",
                action_id="action-success-1",
                created_at=now,
                verification_status="VERIFIED_SUCCESS",
                provenance=Provenance.SIMULATED,
                energy_kwh=Decimal("0.500000"),
                water_liters=None,
                cost_amount=Decimal("5.00"),
                cost_currency="INR",
                co2_kg=Decimal("0.400000"),
                source_ids=["reading-power-1"],
                calculation_version="impact-v1",
            ),
            LedgerFact(
                id="ledger-failed-1",
                action_id="action-failed-1",
                created_at=now,
                verification_status="VERIFICATION_FAILED",
                provenance=Provenance.SIMULATED,
                energy_kwh=Decimal("99"),
                cost_amount=Decimal("999"),
                cost_currency="INR",
                source_ids=["reading-power-1"],
                calculation_version="impact-v1",
            ),
        ],
        energy_tariff_per_kwh=Decimal("10"),
        energy_tariff_currency="INR",
        co2_factor_kg_per_kwh=Decimal("0.8"),
        assumptions={"tariff_source": "configured-test-factor", "demo_time": "accelerated"},
        unavailable_inputs=["measured campus validation"],
    )


@pytest.fixture
def template_service(tmp_path) -> CopilotService:
    settings = CopilotSettings(
        api_base_url=None,
        api_key=None,
        model=None,
        cache_path=str(tmp_path / "copilot-cache.json"),
    )
    return CopilotService(settings=settings, cache=LastGoodNarrativeCache(settings.cache_path))
