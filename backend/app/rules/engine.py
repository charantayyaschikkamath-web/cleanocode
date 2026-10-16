from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from statistics import median
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import new_id
from app.db.models import CampusEvent, Room, SensorReading
from app.repositories import create_event, get_building, get_event, get_room
from app.schemas import EventCreate
from app.simulator.schemas import DetectionThresholds

RULE_VERSION = "1.0.0"


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _series(readings: Iterable[SensorReading], resource_type: str, unit: str | None = None) -> list[SensorReading]:
    items = [r for r in readings if r.resource_type.upper() == resource_type.upper() and (unit is None or r.unit.casefold() == unit.casefold())]
    groups: dict[str, list[SensorReading]] = {}
    for item in items:
        # Prefer a single stable source. Combining unlike sensors can manufacture persistence.
        key = item.sensor_id or f"{item.source_type}:{item.resource_type}:{item.unit}:{item.room_id}"
        groups.setdefault(key, []).append(item)
    if not groups:
        return []
    chosen = max(groups.values(), key=lambda rows: max(x.observed_at for x in rows))
    return sorted(chosen, key=lambda x: x.observed_at)


def _healthy(items: list[SensorReading]) -> bool:
    return bool(items) and all(r.source_status == "HEALTHY" for r in items)


def _qualifying_tail(items: list[SensorReading], predicate) -> list[SensorReading]:
    """Return the latest consecutive healthy samples satisfying a predicate."""
    tail: list[SensorReading] = []
    for row in reversed(items):
        if row.source_status != "HEALTHY" or not predicate(_decimal(row.value)):
            break
        tail.append(row)
    return list(reversed(tail))


def _persistent_window(items: list[SensorReading], predicate, persistence_seconds: float) -> list[SensorReading]:
    tail = _qualifying_tail(items, predicate)
    if len(tail) < 3:
        return []
    span = (tail[-1].observed_at - tail[0].observed_at).total_seconds()
    return tail if span >= persistence_seconds else []


def _provenance(items: Iterable[SensorReading]) -> str:
    values = {r.provenance for r in items}
    if "SIMULATED" in values:
        return "SIMULATED"
    if values == {"REAL"}:
        return "DERIVED"
    return "DERIVED"


def _event_snapshot(
    *, rule_id: str, reading_rows: list[SensorReading], inputs: dict[str, Any], thresholds: dict[str, Any],
    explanation: str, unknowns: list[str] | None = None, scenario_run_id: str | None = None,
) -> dict[str, Any]:
    row_ids = [x.id for x in reading_rows]
    created = datetime.now(timezone.utc)
    snapshot: dict[str, Any] = {
        "id": new_id(),
        "created_at": _iso(created),
        "provenance": _provenance(reading_rows),
        "reading_ids": row_ids,
        "rule_id": rule_id,
        "rule_version": RULE_VERSION,
        "rule_inputs": inputs,
        "thresholds": thresholds,
        "explanation": explanation,
        "unknowns": unknowns or [],
        "snapshot_hash": None,
    }
    if scenario_run_id:
        snapshot["scenario_run_id"] = scenario_run_id
    return snapshot


def _existing_for_snapshot(session: Session, *, event_type: str, building_id: str, room_id: str | None, reading_ids: list[str], scenario_run_id: str | None) -> CampusEvent | None:
    current = session.scalars(
        select(CampusEvent).where(
            CampusEvent.event_type == event_type,
            CampusEvent.building_id == building_id,
            CampusEvent.room_id == room_id,
            CampusEvent.status == "OPEN",
        ).order_by(CampusEvent.created_at.desc()).limit(50)
    ).all()
    for event in current:
        snapshot = event.evidence_snapshot or {}
        existing_ids = set(snapshot.get("reading_ids", event.evidence_refs or []))
        if scenario_run_id and snapshot.get("scenario_run_id") == scenario_run_id:
            return event
        if reading_ids and existing_ids == set(reading_ids):
            return event
    return None


def _emit(
    session: Session,
    *, event_type: str, severity: str, building_id: str, room_id: str | None,
    trigger_rule: str, reading_rows: list[SensorReading], snapshot: dict[str, Any],
    scenario_run_id: str | None,
) -> CampusEvent:
    ids = [r.id for r in reading_rows]
    existing = _existing_for_snapshot(
        session, event_type=event_type, building_id=building_id, room_id=room_id,
        reading_ids=ids, scenario_run_id=scenario_run_id,
    )
    if existing:
        return existing
    now = datetime.now(timezone.utc)
    return create_event(
        session,
        EventCreate(
            event_type=event_type,
            severity=severity,
            building_id=building_id,
            room_id=room_id,
            trigger_rule=trigger_rule,
            first_seen_at=max((r.observed_at for r in reading_rows), default=now),
            evidence_refs=ids,
            evidence_snapshot=snapshot,
            provenance=snapshot["provenance"],
        ),
    )


def evaluate_room_rules(
    session: Session,
    *,
    building_id: str,
    room_id: str | None,
    thresholds: DetectionThresholds | None = None,
    reading_ids: list[str] | None = None,
    scenario_run_id: str | None = None,
) -> list[CampusEvent]:
    """Run conservative, threshold-plus-persistence rules against persisted readings.

    This is deterministic rule logic, not a trained ML detector. Only healthy readings
    satisfy positive/normal conditions; missing and stale signals stay unknown.
    """
    thresholds = thresholds or DetectionThresholds()
    get_building(session, building_id)
    room = get_room(session, room_id) if room_id else None
    if room and room.building_id != building_id:
        raise ValueError("room_id does not belong to building_id")

    if reading_ids:
        found = list(session.scalars(select(SensorReading).where(SensorReading.id.in_(reading_ids))).all())
        if len(found) != len(set(reading_ids)):
            # Don't silently evaluate against a partial caller-supplied evidence set.
            missing = set(reading_ids) - {r.id for r in found}
            raise ValueError(f"reading_ids contain unknown records: {sorted(missing)}")
        readings = [r for r in found if r.building_id == building_id and (room_id is None or r.room_id == room_id)]
    else:
        query = select(SensorReading).where(SensorReading.building_id == building_id)
        if room_id:
            query = query.where(SensorReading.room_id == room_id)
        readings = list(session.scalars(query.order_by(SensorReading.observed_at.desc()).limit(300)).all())
        readings.sort(key=lambda x: x.observed_at)

    if not readings:
        snapshot = _event_snapshot(
            rule_id="EVIDENCE_AVAILABLE_V1", reading_rows=[], inputs={"building_id": building_id, "room_id": room_id},
            thresholds={}, explanation="No sensor readings were supplied for this scope; the system cannot infer normal occupancy or a resource incident.",
            unknowns=["No readings available."], scenario_run_id=scenario_run_id,
        )
        return [_emit(
            session, event_type="evidence_insufficient", severity="MEDIUM", building_id=building_id,
            room_id=room_id, trigger_rule="EVIDENCE_AVAILABLE_V1", reading_rows=[], snapshot=snapshot,
            scenario_run_id=scenario_run_id,
        )]

    # Limit the evaluation to the newest contiguous scenario/source slice; this avoids
    # accidentally mixing unrelated runs when a manual evaluation spans historic data.
    raw_energy = _series(readings, "ENERGY", "W")
    raw_occupancy = _series(readings, "OCCUPANCY")
    raw_water = _series(readings, "WATER")
    raw_bins = _series(readings, "WASTE", "%")
    generated: list[CampusEvent] = []

    # Sensor-health decisions are based on each source's latest reading, not every stale
    # record in history. After recovery, only the healthy tail after the last bad sample
    # participates in persistence checks.
    raw_series = [raw_energy, raw_occupancy, raw_water, raw_bins]
    latest_bad = [series[-1] for series in raw_series if series and series[-1].source_status != "HEALTHY"]
    if latest_bad:
        unique_bad = {row.id: row for row in latest_bad}
        relevant_bad = sorted(unique_bad.values(), key=lambda x: x.observed_at)
        snapshot = _event_snapshot(
            rule_id="SOURCE_HEALTH_V1", reading_rows=relevant_bad,
            inputs={"latest_unhealthy_source_count": len(relevant_bad), "statuses": sorted({r.source_status for r in relevant_bad})},
            thresholds={"accepted_status": "HEALTHY"},
            explanation="The latest reading from one or more required sources is stale, missing, or unhealthy. Positive detection is suppressed until healthy evidence returns.",
            unknowns=["The true resource/occupancy state is unknown while a required source is unhealthy."],
            scenario_run_id=scenario_run_id,
        )
        generated.append(_emit(
            session, event_type="sensor_unavailable", severity="HIGH", building_id=building_id,
            room_id=room_id, trigger_rule="SOURCE_HEALTH_V1", reading_rows=relevant_bad,
            snapshot=snapshot, scenario_run_id=scenario_run_id,
        ))
        return generated

    def healthy_tail(series: list[SensorReading]) -> list[SensorReading]:
        last_bad = max((i for i, row in enumerate(series) if row.source_status != "HEALTHY"), default=-1)
        return series[last_bad + 1:]

    energy = healthy_tail(raw_energy)
    occupancy = healthy_tail(raw_occupancy)
    water = healthy_tail(raw_water)
    bins = healthy_tail(raw_bins)

    power_window = _persistent_window(energy, lambda x: x >= Decimal(str(thresholds.min_power_w)), thresholds.energy_persistence_seconds)
    power_sustained = bool(power_window)
    occupancy_empty_window = _persistent_window(occupancy, lambda x: x == 0, thresholds.energy_persistence_seconds)
    if power_sustained and not occupancy:
        power_median = Decimal(str(median([float(r.value) for r in power_window])))
        snapshot = _event_snapshot(
            rule_id="OCCUPANCY_EVIDENCE_REQUIRED_V1", reading_rows=power_window,
            inputs={"median_power_w": str(power_median), "occupancy_state": "UNKNOWN"},
            thresholds={"min_power_w": thresholds.min_power_w, "persistence_seconds": thresholds.energy_persistence_seconds},
            explanation="Power remained above the configured threshold, but no occupancy signal is available. The system refuses to infer an empty room.",
            unknowns=["Occupancy evidence is missing; this is not proof of an empty room."], scenario_run_id=scenario_run_id,
        )
        generated.append(_emit(
            session, event_type="evidence_insufficient", severity="MEDIUM", building_id=building_id,
            room_id=room_id, trigger_rule="OCCUPANCY_EVIDENCE_REQUIRED_V1", reading_rows=power_window, snapshot=snapshot,
            scenario_run_id=scenario_run_id,
        ))
        return generated

    if power_sustained and occupancy_empty_window:
        occ_times = [r.observed_at for r in occupancy_empty_window]
        energy_start, energy_end = power_window[0].observed_at, power_window[-1].observed_at
        aligned = sum(1 for t in occ_times if energy_start <= t <= energy_end) >= 3
        if aligned:
            power_median = Decimal(str(median([float(r.value) for r in power_window])))
            rows = power_window + occupancy_empty_window
            snapshot = _event_snapshot(
                rule_id="ENERGY_EMPTY_HIGH_POWER_V1", reading_rows=rows,
                inputs={"occupancy_state": "LIKELY_EMPTY", "median_power_w": str(power_median), "sample_count": len(power_window), "persistence_seconds": (energy_end-energy_start).total_seconds()},
                thresholds={"min_power_w": thresholds.min_power_w, "persistence_seconds": thresholds.energy_persistence_seconds},
                explanation="Healthy occupancy readings remained at zero while power stayed above the configured threshold for the required persistence interval.",
                unknowns=["A zero count is a detector output, not identity or face-recognition evidence."], scenario_run_id=scenario_run_id,
            )
            generated.append(_emit(
                session, event_type="likely_energy_waste", severity="HIGH", building_id=building_id, room_id=room_id,
                trigger_rule="ENERGY_EMPTY_HIGH_POWER_V1", reading_rows=rows, snapshot=snapshot, scenario_run_id=scenario_run_id,
            ))
            return generated
        snapshot = _event_snapshot(
            rule_id="OCCUPANCY_POWER_ALIGNMENT_V1", reading_rows=power_window + occupancy_empty_window,
            inputs={"power_window_start": _iso(energy_start), "power_window_end": _iso(energy_end), "occupancy_sample_count": len(occupancy_empty_window)},
            thresholds={"persistence_seconds": thresholds.energy_persistence_seconds},
            explanation="Power and empty-occupancy evidence do not sufficiently overlap in virtual time, so the system cannot assert an empty-room waste event.",
            unknowns=["Signals are not time-aligned over the required persistence window."], scenario_run_id=scenario_run_id,
        )
        generated.append(_emit(
            session, event_type="evidence_insufficient", severity="MEDIUM", building_id=building_id, room_id=room_id,
            trigger_rule="OCCUPANCY_POWER_ALIGNMENT_V1", reading_rows=power_window + occupancy_empty_window,
            snapshot=snapshot, scenario_run_id=scenario_run_id,
        ))
        return generated

    occupancy_use_window = _persistent_window(occupancy, lambda x: x > 0, thresholds.energy_persistence_seconds)
    if power_sustained and occupancy_use_window and room:
        capacity_source = "ROOM_METADATA"
        capacity = room.capacity
        if not capacity:
            demo_capacity = next((r.metadata_json.get("capacity_for_rule") for r in occupancy if r.metadata_json.get("capacity_for_rule")), None)
            if demo_capacity:
                capacity = int(demo_capacity)
                capacity_source = "SCENARIO_ASSUMPTION"
        if capacity and capacity > 0:
            occupancy_median = Decimal(str(median([float(r.value) for r in occupancy_use_window])))
            ratio = float(occupancy_median / Decimal(capacity))
            if ratio <= thresholds.low_occupancy_ratio:
                rows = power_window + occupancy_use_window
                snapshot = _event_snapshot(
                    rule_id="ROOM_LOW_USE_HIGH_POWER_V1", reading_rows=rows,
                    inputs={"occupancy_median": str(occupancy_median), "capacity": capacity, "capacity_source": capacity_source, "occupancy_ratio": ratio, "median_power_w": str(median([float(r.value) for r in power_window]))},
                    thresholds={"min_power_w": thresholds.min_power_w, "low_occupancy_ratio": thresholds.low_occupancy_ratio, "persistence_seconds": thresholds.energy_persistence_seconds},
                    explanation="Power remained elevated while healthy occupancy stayed low relative to room capacity.",
                    unknowns=["A scenario capacity assumption is not verified room metadata."] if capacity_source == "SCENARIO_ASSUMPTION" else [],
                    scenario_run_id=scenario_run_id,
                )
                generated.append(_emit(
                    session, event_type="likely_inefficient_room_use", severity="MEDIUM", building_id=building_id,
                    room_id=room_id, trigger_rule="ROOM_LOW_USE_HIGH_POWER_V1", reading_rows=rows, snapshot=snapshot,
                    scenario_run_id=scenario_run_id,
                ))
                return generated

    if power_sustained and occupancy_use_window and room and not room.capacity and not any(r.metadata_json.get("capacity_for_rule") for r in occupancy_use_window):
        rows = power_window + occupancy_use_window
        snapshot = _event_snapshot(
            rule_id="ROOM_CAPACITY_REQUIRED_V1", reading_rows=rows,
            inputs={"occupancy_median": str(Decimal(str(median([float(r.value) for r in occupancy_use_window])))), "median_power_w": str(Decimal(str(median([float(r.value) for r in power_window]))))},
            thresholds={"low_occupancy_ratio": thresholds.low_occupancy_ratio, "min_power_w": thresholds.min_power_w},
            explanation="Power remained elevated, but room capacity is unavailable, so occupancy efficiency cannot be classified.",
            unknowns=["Room capacity is not configured; no occupancy-efficiency claim is made."], scenario_run_id=scenario_run_id,
        )
        generated.append(_emit(
            session, event_type="evidence_insufficient", severity="MEDIUM", building_id=building_id, room_id=room_id,
            trigger_rule="ROOM_CAPACITY_REQUIRED_V1", reading_rows=rows, snapshot=snapshot, scenario_run_id=scenario_run_id,
        ))
        return generated

    if power_sustained and occupancy and not occupancy_empty_window and not occupancy_use_window:
        rows = power_window + occupancy[-min(3, len(occupancy)):]
        snapshot = _event_snapshot(
            rule_id="OCCUPANCY_STABILITY_REQUIRED_V1", reading_rows=rows,
            inputs={"occupancy_sample_count": len(occupancy), "median_power_w": str(Decimal(str(median([float(r.value) for r in power_window]))))},
            thresholds={"persistence_seconds": thresholds.energy_persistence_seconds},
            explanation="Power is persistently high, but occupancy evidence is not stable enough over the same window to classify the room.",
            unknowns=["Occupancy was not consistently empty or occupied for the required virtual interval."], scenario_run_id=scenario_run_id,
        )
        generated.append(_emit(
            session, event_type="evidence_insufficient", severity="MEDIUM", building_id=building_id, room_id=room_id,
            trigger_rule="OCCUPANCY_STABILITY_REQUIRED_V1", reading_rows=rows, snapshot=snapshot, scenario_run_id=scenario_run_id,
        ))
        return generated

    flow_items = _series(water, "WATER", "L/min") or _series(water, "WATER", "LPM")
    flow_window = _persistent_window(flow_items, lambda x: x >= Decimal(str(thresholds.water_flow_lpm)), thresholds.water_persistence_seconds)
    if flow_window and all(bool(r.metadata_json.get("low_use_window")) for r in flow_window):
        rows = flow_window
        snapshot = _event_snapshot(
            rule_id="WATER_LOW_USE_FLOW_V1", reading_rows=rows,
            inputs={"median_flow_lpm": str(Decimal(str(median([float(r.value) for r in rows])))), "low_use_window": True, "sample_count": len(rows)},
            thresholds={"min_flow_lpm": thresholds.water_flow_lpm, "persistence_seconds": thresholds.water_persistence_seconds},
            explanation="Flow remained above the scenario's configured threshold during a declared low-use window.",
            unknowns=["A flow alert alone does not quantify water saved or prove a leak."], scenario_run_id=scenario_run_id,
        )
        generated.append(_emit(
            session, event_type="likely_water_anomaly", severity="HIGH", building_id=building_id, room_id=room_id,
            trigger_rule="WATER_LOW_USE_FLOW_V1", reading_rows=rows, snapshot=snapshot, scenario_run_id=scenario_run_id,
        ))

    bin_window = _persistent_window(bins, lambda x: x >= Decimal(str(thresholds.bin_overflow_percent)), thresholds.bin_persistence_seconds)
    if bin_window:
        rows = bin_window
        snapshot = _event_snapshot(
            rule_id="BIN_LEVEL_OVERFLOW_V1", reading_rows=rows,
            inputs={"median_fill_percent": str(Decimal(str(median([float(r.value) for r in rows])))), "sample_count": len(rows)},
            thresholds={"overflow_percent": thresholds.bin_overflow_percent, "persistence_seconds": thresholds.bin_persistence_seconds},
            explanation="The simulated bin fill level remained at or above the configured overflow threshold for the required interval.",
            unknowns=["The scenario is not a validated real-world bin detector; waste mass and emissions are not inferred."], scenario_run_id=scenario_run_id,
        )
        generated.append(_emit(
            session, event_type="likely_bin_overflow", severity="MEDIUM", building_id=building_id, room_id=room_id,
            trigger_rule="BIN_LEVEL_OVERFLOW_V1", reading_rows=rows, snapshot=snapshot, scenario_run_id=scenario_run_id,
        ))

    return generated
