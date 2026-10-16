from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

KWH_QUANTUM = Decimal("0.0000001")
MONEY_QUANTUM = Decimal("0.0001")
KG_QUANTUM = Decimal("0.000001")
ZERO = Decimal("0")


def _decimal(value: Decimal | int | float | str, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} must be a valid decimal number") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _quantize(value: Decimal, quantum: Decimal) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class EnergyImpact:
    power_watts: Decimal
    duration_virtual_seconds: Decimal
    duration_hours: Decimal
    energy_kwh: Decimal
    tariff_per_kwh: Decimal | None
    estimated_cost: Decimal | None
    co2_factor_kg_per_kwh: Decimal | None
    estimated_co2_kg: Decimal | None
    calculation_version: str
    status: str
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        def string(value: Decimal | None) -> str | None:
            return format(value, "f") if value is not None else None

        return {
            "power_watts": string(self.power_watts),
            "duration_virtual_seconds": string(self.duration_virtual_seconds),
            "duration_hours": string(self.duration_hours),
            "energy_kwh": string(self.energy_kwh),
            "tariff_per_kwh": string(self.tariff_per_kwh),
            "estimated_cost": string(self.estimated_cost),
            "co2_factor_kg_per_kwh": string(self.co2_factor_kg_per_kwh),
            "estimated_co2_kg": string(self.estimated_co2_kg),
            "calculation_version": self.calculation_version,
            "status": self.status,
            "limitations": list(self.limitations),
            "unit_convention": "W × virtual seconds; 1 kWh = 1000 W × 3600 seconds",
        }


def calculate_energy_impact(
    power_watts: Decimal | int | float | str,
    duration_virtual_seconds: Decimal | int | float | str,
    *,
    tariff_per_kwh: Decimal | int | float | str | None = None,
    co2_factor_kg_per_kwh: Decimal | int | float | str | None = None,
    calculation_version: str = "energy-impact-v1",
) -> EnergyImpact:
    """Calculate energy from power and virtual duration without applying demo speed twice.

    kWh = (power_watts / 1000) × (duration_virtual_seconds / 3600).
    Cost and CO₂ are unavailable unless their respective factors are supplied.
    """
    power = _decimal(power_watts, "power_watts")
    seconds = _decimal(duration_virtual_seconds, "duration_virtual_seconds")
    if power < ZERO:
        raise ValueError("power_watts must be non-negative")
    if seconds < ZERO:
        raise ValueError("duration_virtual_seconds must be non-negative")

    tariff = _decimal(tariff_per_kwh, "tariff_per_kwh") if tariff_per_kwh is not None else None
    co2_factor = (
        _decimal(co2_factor_kg_per_kwh, "co2_factor_kg_per_kwh")
        if co2_factor_kg_per_kwh is not None
        else None
    )
    if tariff is not None and tariff < ZERO:
        raise ValueError("tariff_per_kwh must be non-negative")
    if co2_factor is not None and co2_factor < ZERO:
        raise ValueError("co2_factor_kg_per_kwh must be non-negative")

    hours = seconds / Decimal("3600")
    raw_energy = (power / Decimal("1000")) * hours
    energy = _quantize(raw_energy, KWH_QUANTUM)
    # Round each output only at its own display/storage precision; don't propagate
    # energy-display rounding into cost or CO2 calculations.
    cost = _quantize(raw_energy * tariff, MONEY_QUANTUM) if tariff is not None else None
    co2 = _quantize(raw_energy * co2_factor, KG_QUANTUM) if co2_factor is not None else None

    limitations: list[str] = [
        "Energy is calculated from supplied power and virtual duration; it is not a real meter observation.",
        "Results are projections unless separately supported by a valid measurement and verification method.",
    ]
    if tariff is None:
        limitations.append("Cost is unavailable because no tariff per kWh was supplied or configured.")
    if co2_factor is None:
        limitations.append("CO2 estimate is unavailable because no emission factor was supplied or configured.")

    status = "PROJECTED" if tariff is not None or co2_factor is not None else "ENERGY_ONLY_PROJECTION"
    return EnergyImpact(
        power_watts=power,
        duration_virtual_seconds=seconds,
        duration_hours=hours,
        energy_kwh=energy,
        tariff_per_kwh=tariff,
        estimated_cost=cost,
        co2_factor_kg_per_kwh=co2_factor,
        estimated_co2_kg=co2,
        calculation_version=calculation_version,
        status=status,
        limitations=tuple(limitations),
    )
