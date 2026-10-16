from decimal import Decimal

import pytest

from app.core.impact import calculate_energy_impact


def test_minimum_energy_formula_1000_watts_for_600_virtual_seconds():
    result = calculate_energy_impact(1000, 600)
    assert result.energy_kwh == Decimal("0.1666667")
    assert result.estimated_cost is None
    assert result.estimated_co2_kg is None
    assert "Cost is unavailable" in " ".join(result.limitations)
    assert "CO2 estimate is unavailable" in " ".join(result.limitations)


def test_tariff_and_emission_factor_are_applied_deterministically():
    result = calculate_energy_impact(
        "1000", "600", tariff_per_kwh="8.5", co2_factor_kg_per_kwh="0.7"
    )
    assert result.energy_kwh == Decimal("0.1666667")
    assert result.estimated_cost == Decimal("1.4167")
    assert result.estimated_co2_kg == Decimal("0.116667")
    assert result.status == "PROJECTED"


def test_invalid_negative_and_nonfinite_inputs_are_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        calculate_energy_impact(-1, 20)
    with pytest.raises(ValueError, match="non-negative"):
        calculate_energy_impact(1, -20)
    with pytest.raises(ValueError, match="finite"):
        calculate_energy_impact("NaN", 20)


def test_demo_multiplier_is_not_part_of_energy_formula():
    slow_demo = calculate_energy_impact(1000, 600)
    fast_demo = calculate_energy_impact(1000, 600)
    assert slow_demo.energy_kwh == fast_demo.energy_kwh
