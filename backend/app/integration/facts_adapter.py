"""Bridge persisted Account 2/3 records into Account 7's privacy-minimised facts schema.

Only structured values/IDs/units/timestamps and provenance cross this boundary. Camera
frames, video bytes, API keys and identity data are not representable in FactsSnapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.copilot.models import (
    ActionFact, EventFact, FactsSnapshot, LedgerFact, ProjectedImpact,
    Provenance, ReadingFact, SourceHealth,
)
from app.db.models import ActionRecord, Building, CampusEvent, Room, SavingsLedgerEntry, SensorReading


def _provenance(value: str | None) -> Provenance:
    try:
        return Provenance(value or "UNKNOWN")
    except ValueError:
        return Provenance.UNKNOWN


def build_facts_snapshot(session: Session, settings, *, now: datetime | None = None) -> FactsSnapshot:
    now = now or datetime.now(timezone.utc)
    readings_db = list(session.scalars(select(SensorReading).order_by(SensorReading.observed_at.desc()).limit(500)).all())
    events_db = list(session.scalars(select(CampusEvent).order_by(CampusEvent.last_updated_at.desc()).limit(500)).all())
    actions_db = list(session.scalars(select(ActionRecord).order_by(ActionRecord.updated_at.desc()).limit(500)).all())
    ledger_db = list(session.scalars(select(SavingsLedgerEntry).order_by(SavingsLedgerEntry.created_at.desc()).limit(500)).all())
    buildings = {b.id: b for b in session.scalars(select(Building)).all()}
    rooms = {r.id: r for r in session.scalars(select(Room)).all()}
    readings: list[ReadingFact] = []
    for row in readings_db:
        meta = row.metadata_json or {}
        # SENSOR freshness remains based on wall-clock at ingestion. For simulator data the
        # virtual time domain is disclosed as an assumption instead of being mistaken for a
        # current physical measurement.
        age = max(0, int((now - row.observed_at.astimezone(timezone.utc)).total_seconds()))
        source = (row.source_status or "UNKNOWN").upper()
        health_map = {"HEALTHY": SourceHealth.HEALTHY, "STALE": SourceHealth.STALE,
                      "UNAVAILABLE": SourceHealth.UNHEALTHY, "UNKNOWN": SourceHealth.UNKNOWN}
        if row.freshness_seconds is not None and row.freshness_seconds > 900:
            source_health = SourceHealth.STALE
        else:
            source_health = health_map.get(source, SourceHealth.UNKNOWN)
        # For SIMULATED readings, freshness_seconds is the scenario's explicit sample-age
        # contract and `observed_at` can be virtual time. We keep source status truthful.
        readings.append(ReadingFact(
            id=row.id, resource_type=row.resource_type,
            reading_type=row.source_type, value=Decimal(row.value), unit=row.unit,
            observed_at=row.observed_at, provenance=_provenance(row.provenance),
            source_health=source_health, freshness_seconds=row.freshness_seconds if row.freshness_seconds is not None else age,
            building_id=row.building_id, room_id=row.room_id,
            location=rooms.get(row.room_id).name if row.room_id in rooms else buildings.get(row.building_id).name if row.building_id in buildings else None,
            time_domain="VIRTUAL" if meta.get("time_domain") == "VIRTUAL" else "WALL",
        ))
    events: list[EventFact] = []
    for row in events_db:
        snapshot = row.evidence_snapshot or {}
        reading_ids = list(snapshot.get("reading_ids") or row.evidence_refs or [])
        building = buildings.get(row.building_id)
        room = rooms.get(row.room_id) if row.room_id else None
        projected = ProjectedImpact(
            status="UNAVAILABLE", assumptions=["No independent projected-impact estimate was attached to this event."],
        )
        events.append(EventFact(
            id=row.id, event_type=row.event_type, severity=row.severity, status=row.status,
            building_id=row.building_id, room_id=row.room_id,
            location=f"{building.name if building else row.building_id}{' / ' + room.name if room else ''}",
            first_seen_at=row.first_seen_at, last_updated_at=row.last_updated_at,
            trigger_rule=row.trigger_rule,
            explanation=str(snapshot.get("explanation") or snapshot.get("reason") or "Rule triggered from the stored evidence snapshot."),
            evidence_ids=reading_ids, provenance=_provenance(row.provenance), projected_impact=projected,
        ))
    actions: list[ActionFact] = []
    for row in actions_db:
        verification = session.scalar(select(__import__('app.db.models', fromlist=['VerificationRecord']).VerificationRecord).where(
            __import__('app.db.models', fromlist=['VerificationRecord']).VerificationRecord.action_id == row.id
        ).order_by(__import__('app.db.models', fromlist=['VerificationRecord']).VerificationRecord.created_at.desc()).limit(1))
        evidence_ids = list(row.baseline_reading_ids or [])
        if verification:
            evidence_ids.extend(verification.evidence_reading_ids or [])
        actions.append(ActionFact(
            id=row.id, event_id=row.event_id, status=row.state,
            requested_at=row.created_at, updated_at=row.updated_at,
            verification_summary=(verification.result if verification else "Awaiting independent verification"),
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            provenance=_provenance((row.metadata_json or {}).get("provenance", "SIMULATED")),
        ))
    ledger: list[LedgerFact] = []
    for row in ledger_db:
        ledger.append(LedgerFact(
            id=row.id, action_id=row.action_id, created_at=row.created_at,
            verification_status="VERIFIED_SUCCESS" if row.status == "VERIFIED_SIMULATED" else row.status,
            provenance=Provenance.SIMULATED if row.status == "VERIFIED_SIMULATED" else Provenance.REAL,
            energy_kwh=row.energy_kwh, water_liters=row.water_liters,
            cost_amount=row.cost_amount, cost_currency=row.currency, co2_kg=row.co2_kg,
            source_ids=list(row.source_reading_ids or []), calculation_version=row.calculation_version,
        ))
    unavailable: list[str] = []
    if settings.tariff_per_kwh is None:
        unavailable.append("configured electricity tariff")
    if settings.co2_factor_kg_per_kwh is None:
        unavailable.append("configured CO₂ emission factor")
    return FactsSnapshot(
        snapshot_id=f"persisted-{now.strftime('%Y%m%dT%H%M%S%fZ')}", generated_at=now,
        source_status="HEALTHY" if readings_db or events_db or actions_db or ledger_db else "EMPTY",
        readings=readings, events=events, actions=actions, ledger_entries=ledger,
        energy_tariff_per_kwh=settings.tariff_per_kwh, energy_tariff_currency="INR" if settings.tariff_per_kwh is not None else None,
        co2_factor_kg_per_kwh=settings.co2_factor_kg_per_kwh,
        assumptions={
            "data_source": "Persisted CampusTwin SQLite records",
            "simulated_time": "Scenario-generated timestamps may use accelerated virtual time; such records remain SIMULATED.",
            "camera_privacy": "Only derived camera count/status metadata may be persisted; raw frames and videos are not included.",
        }, unavailable_inputs=unavailable,
    )
