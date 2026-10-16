from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.impact import calculate_energy_impact
from app.schemas import EnergyImpactRequest

router = APIRouter(tags=["impact calculations"])


@router.post("/impact/energy")
def energy_impact(payload: EnergyImpactRequest, request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    tariff = payload.tariff_per_kwh if payload.tariff_per_kwh is not None else settings.tariff_per_kwh
    co2_factor = payload.co2_factor_kg_per_kwh if payload.co2_factor_kg_per_kwh is not None else settings.co2_factor_kg_per_kwh
    result = calculate_energy_impact(
        payload.power_watts,
        payload.duration_virtual_seconds,
        tariff_per_kwh=tariff,
        co2_factor_kg_per_kwh=co2_factor,
        calculation_version=settings.impact_calculation_version,
    )
    return result.as_dict()
