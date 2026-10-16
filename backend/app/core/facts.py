from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CampusEvent, SavingsLedgerEntry, SensorReading


def _display_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _origin(entries: list[SavingsLedgerEntry]) -> str | None:
    statuses = {entry.status for entry in entries}
    if not statuses:
        return None
    if statuses == {"MEASURED"}:
        return "MEASURED"
    if statuses == {"VERIFIED_SIMULATED"}:
        return "VERIFIED_SIMULATED"
    return "MIXED_VERIFIED_SOURCES"


def _sum_metric(
    entries: list[SavingsLedgerEntry],
    *,
    attribute: str,
    unit: str,
    source_id_attribute: str = "id",
    require_complete: bool = True,
) -> dict[str, Any]:
    if not entries:
        return {
            "value": None,
            "unit": unit,
            "availability": "UNAVAILABLE",
            "provenance": None,
            "source_ids": [],
            "note": "No verified ledger records support this metric yet.",
        }
    values = [getattr(entry, attribute) for entry in entries]
    known = [value for value in values if value is not None]
    if not known or (require_complete and len(known) != len(values)):
        return {
            "value": None,
            "unit": unit,
            "availability": "UNAVAILABLE" if not known else "PARTIAL",
            "provenance": _origin(entries),
            "source_ids": [getattr(entry, source_id_attribute) for entry in entries],
            "note": "One or more verified records lack the inputs required to calculate this aggregate.",
        }
    total = sum((Decimal(value) for value in known), Decimal("0"))
    return {
        "value": _display_decimal(total),
        "unit": unit,
        "availability": "AVAILABLE" if len(known) == len(values) else "PARTIAL",
        "provenance": _origin(entries),
        "source_ids": [getattr(entry, source_id_attribute) for entry in entries],
        "note": "Summed from persisted ledger entries created only after VERIFIED_SUCCESS.",
    }


def assemble_overview_facts(session: Session, as_of: datetime) -> dict[str, Any]:
    open_event_ids = list(
        session.scalars(
            select(CampusEvent.id).where(CampusEvent.status.in_(["OPEN", "ACKNOWLEDGED"]))
        ).all()
    )
    open_events = {
        "value": len(open_event_ids),
        "unit": "events",
        "availability": "AVAILABLE",
        "provenance": "PERSISTED_DATABASE_STATE",
        "source_ids": open_event_ids,
        "note": "Count includes OPEN and ACKNOWLEDGED records; it does not infer missing incidents.",
    }

    resource_types = list(session.scalars(select(SensorReading.resource_type).distinct()).all())
    latest_readings: list[dict[str, Any]] = []
    for resource_type in sorted(resource_types):
        reading = session.scalar(
            select(SensorReading)
            .where(SensorReading.resource_type == resource_type)
            .order_by(SensorReading.observed_at.desc(), SensorReading.created_at.desc())
            .limit(1)
        )
        if reading is None:
            continue
        age_seconds = max(0, int((as_of - reading.observed_at).total_seconds()))
        latest_readings.append({
            "reading_id": reading.id,
            "resource_type": reading.resource_type,
            "value": _display_decimal(Decimal(reading.value)),
            "unit": reading.unit,
            "observed_at": reading.observed_at.isoformat().replace("+00:00", "Z"),
            "observed_age_seconds": age_seconds,
            "source_status": reading.source_status,
            "provenance": reading.provenance,
            "building_id": reading.building_id,
            "room_id": reading.room_id,
            "note": "Latest persisted reading for this resource type; not an aggregate or inferred campus total.",
        })

    entries = list(session.scalars(select(SavingsLedgerEntry).order_by(SavingsLedgerEntry.created_at)).all())
    energy_entries = [entry for entry in entries if entry.resource_type.lower() == "energy"]
    water_entries = [entry for entry in entries if entry.resource_type.lower() == "water"]
    all_energy_entries = energy_entries

    energy = _sum_metric(energy_entries, attribute="energy_kwh", unit="kWh")
    cost = _sum_metric(energy_entries, attribute="cost_amount", unit="configured_currency_amount")
    if cost["availability"] != "UNAVAILABLE" and any(entry.currency for entry in energy_entries):
        currencies = {entry.currency for entry in energy_entries if entry.cost_amount is not None}
        if len(currencies) == 1:
            cost["unit"] = next(iter(currencies)) or "configured_currency_amount"
        elif len(currencies) > 1:
            cost.update({
                "value": None,
                "availability": "UNAVAILABLE",
                "unit": "mixed_currency",
                "note": "Cannot aggregate costs recorded in different currencies.",
            })
    water = _sum_metric(water_entries, attribute="water_liters", unit="L")
    co2 = _sum_metric(all_energy_entries, attribute="co2_kg", unit="kg CO2e")

    return {
        "schema_version": "campustwin-facts-v1",
        "as_of": as_of,
        "open_events": open_events,
        "latest_readings": latest_readings,
        "verified_energy_saved_kwh": energy,
        "verified_cost_saved": cost,
        "verified_water_saved_liters": water,
        "verified_co2_avoided_kg": co2,
    }
