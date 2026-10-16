from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import VirtualClock
from app.core.errors import DomainError
from app.db.base import new_id, utc_now
from app.db.models import CampusEvent, Room, ScenarioRun, SensorReading
from app.repositories import create_reading, get_building, get_room
from app.schemas import ReadingCreate
from app.rules.engine import evaluate_room_rules
from app.simulator.schemas import ActionProposalRequest, ScenarioRunRequest
from app.services.actions import create_action_proposal

SCENARIOS: list[dict[str, Any]] = [
    {"scenario_type": "EMPTY_ROOM_HIGH_POWER", "label": "Empty room + high power", "requires_room": True, "event_expected": "likely_energy_waste"},
    {"scenario_type": "NIGHT_WATER_FLOW", "label": "Low-use water-flow anomaly", "requires_room": False, "event_expected": "likely_water_anomaly"},
    {"scenario_type": "BIN_OVERFLOW", "label": "Bin overflow", "requires_room": False, "event_expected": "likely_bin_overflow"},
    {"scenario_type": "INEFFICIENT_ROOM_USE", "label": "Inefficient room use", "requires_room": True, "event_expected": "likely_inefficient_room_use"},
    {"scenario_type": "NORMAL_OPERATION", "label": "Normal operation", "requires_room": False, "event_expected": None},
    {"scenario_type": "SENSOR_MISSING", "label": "Missing occupancy evidence", "requires_room": True, "event_expected": "evidence_insufficient"},
    {"scenario_type": "SENSOR_STALE", "label": "Stale sensor evidence", "requires_room": False, "event_expected": "sensor_unavailable"},
    {"scenario_type": "COMMAND_DROPPED", "label": "Command dropped", "requires_room": True, "event_expected": "likely_energy_waste"},
    {"scenario_type": "ACKNOWLEDGED_IGNORED", "label": "Command acknowledged but ignored", "requires_room": True, "event_expected": "likely_energy_waste"},
    {"scenario_type": "VERIFIED_RESPONSE", "label": "Successful independently verified response", "requires_room": True, "event_expected": "likely_energy_waste"},
]


def _latest_virtual_start(session: Session, clock: VirtualClock, building_id: str, room_id: str | None) -> datetime:
    query = select(SensorReading.observed_at).where(SensorReading.building_id == building_id)
    if room_id:
        query = query.where(SensorReading.room_id == room_id)
    latest = session.scalar(query.order_by(SensorReading.observed_at.desc()).limit(1))
    current = clock.virtual_now()
    if latest and latest >= current:
        return latest + timedelta(seconds=1)
    return current


def _reading(
    session: Session,
    *, run_id: str, building_id: str, room_id: str | None, sensor_id: str,
    source_type: str, resource_type: str, value: float, unit: str,
    observed_at: datetime, source_status: str = "HEALTHY", freshness_seconds: int = 0,
    metadata: dict[str, Any] | None = None,
) -> SensorReading:
    idempotency_key = f"{run_id}:{sensor_id}:{int(observed_at.timestamp())}:{resource_type}"
    return create_reading(
        session,
        ReadingCreate(
            idempotency_key=idempotency_key,
            sensor_id=sensor_id,
            source_type=source_type,
            resource_type=resource_type,
            building_id=building_id,
            room_id=room_id,
            value=str(value),
            unit=unit,
            observed_at=observed_at,
            source_status=source_status,  # type: ignore[arg-type]
            freshness_seconds=freshness_seconds,
            provenance="SIMULATED",
            metadata={"scenario_run_id": run_id, "time_domain": "VIRTUAL", **(metadata or {})},
        ),
    )


def _add_series(
    session: Session,
    *, run_id: str, request: ScenarioRunRequest, room_id: str | None,
    resource_type: str, unit: str, values: list[float], source_type: str,
    start: datetime, duration: int, status: str = "HEALTHY", metadata: dict[str, Any] | None = None,
    sensor_suffix: str,
) -> list[SensorReading]:
    # Three samples are the minimum accepted by the independent verifier/rules.
    offsets = [0, duration // 2, duration]
    rows: list[SensorReading] = []
    for index, offset in enumerate(offsets):
        rows.append(_reading(
            session,
            run_id=run_id,
            building_id=request.building_id,
            room_id=room_id,
            sensor_id=f"SIM-{sensor_suffix}-{room_id or request.building_id}",
            source_type=source_type,
            resource_type=resource_type,
            value=values[index],
            unit=unit,
            observed_at=start + timedelta(seconds=offset),
            source_status=status,
            freshness_seconds=0 if status == "HEALTHY" else int(max(1, duration * 2)),
            metadata={"sample_index": index, "virtual_elapsed_seconds": offset, **(metadata or {})},
        ))
    return rows


def run_scenario(session: Session, *, request: ScenarioRunRequest, clock: VirtualClock, settings) -> dict[str, Any]:
    """Persist a deterministic scenario, then run the real rules against those records."""
    building = get_building(session, request.building_id)
    room = get_room(session, request.room_id) if request.room_id else None
    if room and room.building_id != building.id:
        raise DomainError("ROOM_BUILDING_MISMATCH", "The room does not belong to the specified building.", status_code=422)
    scenario = request.scenario_type
    if next(x for x in SCENARIOS if x["scenario_type"] == scenario)["requires_room"] and room is None:
        raise DomainError("ROOM_REQUIRED", f"Scenario {scenario} requires room_id.", status_code=422)

    run_id = new_id()
    wall_started = utc_now()
    virtual_started = _latest_virtual_start(session, clock, request.building_id, request.room_id)
    run = ScenarioRun(
        id=run_id,
        scenario_name=scenario,
        provenance="SIMULATED",
        status="RUNNING",
        virtual_started_at=virtual_started,
        wall_started_at=wall_started,
        request_payload=request.model_dump(mode="json"),
        result_payload={},
    )
    session.add(run)
    session.commit()

    readings: list[SensorReading] = []
    try:
        n = request.duration_virtual_seconds
        t = request.thresholds
        meta = {"scenario_type": scenario, "scenario_seed": request.seed, "threshold_profile": "SIMULATION_DEFAULTS", "limits": ["All readings in this scenario are simulated."]}
        rng = random.Random(request.seed)

        # Some event types intentionally provide only partial evidence, proving that the
        # engine does not mistake unavailable occupancy for an empty room.
        if scenario in {"EMPTY_ROOM_HIGH_POWER", "COMMAND_DROPPED", "ACKNOWLEDGED_IGNORED", "VERIFIED_RESPONSE", "SENSOR_MISSING", "SENSOR_STALE", "INEFFICIENT_ROOM_USE", "NORMAL_OPERATION"}:
            base_power = max(t.min_power_w + 320.0, t.min_power_w * 1.5)
            normal = scenario == "NORMAL_OPERATION"
            if normal:
                safe_power = min(120.0, t.min_power_w * 0.25)
                power_values = [safe_power, max(0.01, safe_power - 2.0), safe_power + 1.0]
            else:
                power_values = [base_power + rng.uniform(-3.0, 3.0) for _ in range(3)]
            sensor_status = "STALE" if scenario == "SENSOR_STALE" else "HEALTHY"
            readings += _add_series(
                session, run_id=run_id, request=request, room_id=request.room_id,
                resource_type="ENERGY", unit="W", values=power_values, source_type="POWER_METER",
                start=virtual_started, duration=n, status=sensor_status,
                metadata={**meta, "scenario_run_id": run_id}, sensor_suffix="POWER",
            )
            if scenario != "SENSOR_MISSING":
                if scenario == "NORMAL_OPERATION":
                    normal_capacity = room.capacity if room and room.capacity else 40
                    occupied_value = max(3.0, normal_capacity * 0.75)
                    occupancy_values = [occupied_value, occupied_value, occupied_value]
                elif scenario == "INEFFICIENT_ROOM_USE":
                    occupancy_values = [2.0, 2.0, 2.0]
                else:
                    occupancy_values = [0.0, 0.0, 0.0]
                room_capacity = room.capacity if room and room.capacity else 40
                occupancy_metadata = {**meta, "capacity_for_rule": room_capacity}
                readings += _add_series(
                    session, run_id=run_id, request=request, room_id=request.room_id,
                    resource_type="OCCUPANCY", unit="person", values=occupancy_values,
                    source_type="SIMULATOR", start=virtual_started, duration=n,
                    status=sensor_status, metadata=occupancy_metadata, sensor_suffix="OCCUPANCY",
                )
            if normal:
                readings += _add_series(
                    session, run_id=run_id, request=request, room_id=request.room_id,
                    resource_type="WATER", unit="L/min", values=[0.1, 0.1, 0.1],
                    source_type="FLOW_METER", start=virtual_started, duration=n,
                    metadata={**meta, "low_use_window": False}, sensor_suffix="FLOW",
                )
                readings += _add_series(
                    session, run_id=run_id, request=request, room_id=request.room_id,
                    resource_type="WASTE", unit="%", values=[30.0, 35.0, 32.0],
                    source_type="BIN_SENSOR", start=virtual_started, duration=n,
                    metadata=meta, sensor_suffix="BIN",
                )

        elif scenario == "NIGHT_WATER_FLOW":
            flow = max(t.water_flow_lpm + 4.0, t.water_flow_lpm * 2.0)
            readings += _add_series(
                session, run_id=run_id, request=request, room_id=request.room_id,
                resource_type="WATER", unit="L/min", values=[flow + rng.uniform(0.0, 0.2) for _ in range(3)],
                source_type="FLOW_METER", start=virtual_started, duration=n,
                metadata={**meta, "low_use_window": True, "scenario_pattern": "NIGHT_WATER_FLOW"}, sensor_suffix="FLOW",
            )
        elif scenario == "BIN_OVERFLOW":
            readings += _add_series(
                session, run_id=run_id, request=request, room_id=request.room_id,
                resource_type="WASTE", unit="%", values=[min(100.0, max(t.bin_overflow_percent, 95.0) + bump) for bump in (0.0, 1.0, 0.5)],
                source_type="BIN_SENSOR", start=virtual_started, duration=n,
                metadata={**meta, "scenario_pattern": "BIN_OVERFLOW"}, sensor_suffix="BIN",
            )

        session.commit()
        created_events = evaluate_room_rules(
            session,
            building_id=request.building_id,
            room_id=request.room_id,
            thresholds=t,
            reading_ids=[r.id for r in readings],
            scenario_run_id=run_id,
        )
        event_ids = [event.id for event in created_events]
        action_ids: list[str] = []
        action_outcome = request.outcome_mode
        if scenario == "COMMAND_DROPPED":
            action_outcome = "DROP_COMMAND"
        elif scenario == "ACKNOWLEDGED_IGNORED":
            action_outcome = "ACK_IGNORE"
        elif scenario == "VERIFIED_RESPONSE":
            action_outcome = "SUCCESS"

        energy_event = next((event for event in created_events if event.event_type == "likely_energy_waste"), None)
        if energy_event and action_outcome != "NOT_APPLICABLE":
            action = create_action_proposal(
                session,
                ActionProposalRequest(
                    event_id=energy_event.id,
                    action_type="SIMULATED_REDUCE_POWER",
                    idempotency_key=f"scenario:{run_id}:action:{energy_event.id}",
                    actor="system_recommendation",
                    outcome_mode=action_outcome,
                    required_drop_percent=t.required_drop_percent,
                    verification_window_seconds=int(t.verification_window_seconds),
                ),
                scenario_run_id=run_id,
            )
            action_ids.append(action.id)

        completed = utc_now()
        result = {
            "scenario_run_id": run_id,
            "status": "COMPLETED",
            "scenario_type": scenario,
            "provenance": "SIMULATED",
            "virtual_clock_multiplier": clock.multiplier,
            "reading_ids": [x.id for x in readings],
            "event_ids": event_ids,
            "action_ids": action_ids,
            "ledger_entry_ids": [],
            "started_at": virtual_started.isoformat().replace("+00:00", "Z"),
            "completed_at": completed.isoformat().replace("+00:00", "Z"),
            "warnings": ["All sensor values in this scenario are simulated.", "Thresholds are configurable demo defaults, not campus-validated safety limits."],
            "detection_summary": [{"event_id": e.id, "event_type": e.event_type, "trigger_rule": e.trigger_rule, "severity": e.severity} for e in created_events],
        }
        if not event_ids:
            result["warnings"].append("No event rule qualified for the supplied readings and persistence window.")
        run = session.get(ScenarioRun, run_id)
        run.status = "COMPLETED"
        run.virtual_ended_at = virtual_started + timedelta(seconds=n)
        run.wall_ended_at = completed
        run.result_payload = result
        session.commit()
        return result
    except Exception as exc:
        session.rollback()
        failed = session.get(ScenarioRun, run_id)
        if failed:
            failed.status = "FAILED"
            failed.wall_ended_at = utc_now()
            failed.error_message = type(exc).__name__
            failed.result_payload = {"scenario_run_id": run_id, "status": "FAILED", "error_type": type(exc).__name__}
            session.commit()
        raise
