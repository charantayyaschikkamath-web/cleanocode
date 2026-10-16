from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.db.base import new_id, utc_now
from app.db.models import ActionRecord, ActionTransition, CampusEvent, SavingsLedgerEntry, SensorReading, VerificationRecord
from app.repositories import create_reading, get_event
from app.schemas import ReadingCreate

D7 = Decimal("0.0000001")
D4 = Decimal("0.0001")
D6 = Decimal("0.000001")


def _median(rows: Iterable[SensorReading]) -> Decimal:
    return Decimal(str(median([float(row.value) for row in rows])))


def generate_post_action_readings(session: Session, *, action: ActionRecord, event: CampusEvent, clock, outcome_mode: str) -> list[SensorReading]:
    """Generate simulated post-command samples; never sends a real device command."""
    baseline = (action.metadata_json or {}).get("baseline_snapshot") or {}
    baseline_value = Decimal(str(baseline.get("median_value", "0")))
    if baseline_value <= 0:
        raise DomainError("BASELINE_NOT_COMPUTABLE", "Cannot generate verification values without a positive baseline.", status_code=409)
    if outcome_mode == "SUCCESS":
        multiplier = Decimal("0.35")
    elif outcome_mode == "ACK_IGNORE":
        # Receiver acknowledges, but the monitored power barely changes.
        multiplier = Decimal("0.97")
    else:
        raise DomainError("INVALID_SIMULATOR_OUTCOME", "Only success and acknowledge-but-ignore outcomes generate post-action readings.", status_code=422)

    window = int((action.metadata_json or {}).get("verification_window_seconds", 300))
    baseline_end = datetime.fromisoformat(str(baseline["window_end"]).replace("Z", "+00:00"))
    start = baseline_end + timedelta(seconds=1)
    offsets = [0, max(1, window // 2), max(1, window)]
    center = baseline_value * multiplier
    values = [center * Decimal("1.01"), center, center * Decimal("0.99")]
    sensor_id = baseline.get("sensor_id")
    rows: list[SensorReading] = []
    for index, (offset, value) in enumerate(zip(offsets, values, strict=True)):
        rows.append(create_reading(
            session,
            ReadingCreate(
                idempotency_key=f"{action.id}:post-verification:{index}",
                sensor_id=sensor_id,
                source_type="POWER_METER",
                resource_type="ENERGY",
                building_id=event.building_id,
                room_id=event.room_id,
                value=str(value.quantize(D4, rounding=ROUND_HALF_UP)),
                unit="W",
                observed_at=start + timedelta(seconds=offset),
                source_status="HEALTHY",
                freshness_seconds=0,
                provenance="SIMULATED",
                metadata={
                    "action_id": action.id,
                    "scenario_run_id": (action.metadata_json or {}).get("scenario_run_id"),
                    "phase": "POST_ACTION_VERIFICATION",
                    "outcome_mode": outcome_mode,
                    "sample_index": index,
                    "time_domain": "VIRTUAL",
                },
            ),
        ))
    return rows


def _transition_row(session: Session, *, action: ActionRecord, new_state: str, actor: str, request_key: str, evidence: dict, note: str, now: datetime) -> ActionTransition:
    prior = session.scalar(select(ActionTransition).where(ActionTransition.request_key == request_key))
    if prior:
        if prior.action_id == action.id and prior.new_state == new_state:
            return prior
        raise ConflictError("TRANSITION_KEY_REUSED", "The verification transition idempotency key has already been used.")
    sequence = session.scalar(select(ActionTransition.sequence_no).where(ActionTransition.action_id == action.id).order_by(ActionTransition.sequence_no.desc()).limit(1)) or 0
    row = ActionTransition(
        action_id=action.id,
        sequence_no=sequence + 1,
        request_key=request_key,
        previous_state=action.state,
        new_state=new_state,
        actor_or_source=actor,
        occurred_at=now,
        evidence=evidence,
        note=note,
    )
    session.add(row)
    return row


def finalize_verification(
    session: Session,
    *, action_id: str, post_rows: list[SensorReading], required_drop_percent: Decimal,
    verification_window_seconds: int, settings, actor: str, request_key: str, now: datetime | None = None,
) -> str:
    """Atomically persist verification, terminal transition, and eligible ledger row.

    Account 2's public repository helpers commit individually. This module owns the
    verification transition and uses one SQLAlchemy transaction so a passing UI status
    cannot be committed without its matching ledger row.
    """
    when = (now or utc_now()).astimezone(timezone.utc)
    session.rollback()  # End any read transaction before opening the all-or-nothing write transaction.
    try:
        with session.begin():
            action = session.get(ActionRecord, action_id)
            if action is None:
                raise NotFoundError("action", action_id)
            if action.state != "VERIFYING":
                existing = session.scalar(select(ActionTransition).where(ActionTransition.request_key == request_key))
                if existing and existing.action_id == action_id and action.state == existing.new_state:
                    return action.state
                raise ConflictError("ACTION_NOT_VERIFYING", "Independent verification can only finalize an action in VERIFYING state.", details={"state": action.state})

            event = session.get(CampusEvent, action.event_id)
            if event is None:
                raise NotFoundError("event", action.event_id)
            baseline_ids = list(action.baseline_reading_ids or [])
            baseline_rows = list(session.scalars(select(SensorReading).where(SensorReading.id.in_(baseline_ids)).order_by(SensorReading.observed_at.asc())).all())
            # Strictly require three compatible and healthy readings on both sides.
            baseline_valid = (
                len(baseline_rows) >= 3
                and all(r.source_status == "HEALTHY" and r.provenance == "SIMULATED" and r.resource_type == "ENERGY" and r.unit == "W" for r in baseline_rows)
                and len({r.sensor_id for r in baseline_rows}) == 1
            )
            post_valid = (
                len(post_rows) >= 3
                and all(r.source_status == "HEALTHY" and r.provenance == "SIMULATED" and r.resource_type == "ENERGY" and r.unit == "W" for r in post_rows)
                and len({r.sensor_id for r in post_rows}) == 1
                and len({r.building_id for r in post_rows}) == 1
                and len({r.room_id for r in post_rows}) == 1
            )

            result_state = "VERIFICATION_TIMEOUT"
            baseline_value = _median(baseline_rows) if baseline_valid else None
            post_value = _median(post_rows) if post_valid else None
            observed_drop: Decimal | None = None
            post_start = min((r.observed_at for r in post_rows), default=None)
            post_end = max((r.observed_at for r in post_rows), default=None)
            if baseline_valid and post_valid and baseline_value and baseline_value > 0 and post_start and post_end:
                if (post_end - post_start).total_seconds() >= verification_window_seconds:
                    observed_drop = ((baseline_value - post_value) / baseline_value) * Decimal("100")
                    result_state = "VERIFIED_SUCCESS" if observed_drop >= required_drop_percent else "VERIFICATION_FAILED"
                else:
                    result_state = "VERIFICATION_TIMEOUT"

            baseline_snapshot = {
                "reading_ids": baseline_ids,
                "median_value": str(baseline_value) if baseline_value is not None else None,
                "unit": "W",
                "resource_type": "ENERGY",
                "sample_count": len(baseline_rows),
                "algorithm_version": "median-baseline-v1",
                "provenance": "SIMULATED",
                "window_start": baseline_rows[0].observed_at.isoformat().replace("+00:00", "Z") if baseline_rows else None,
                "window_end": baseline_rows[-1].observed_at.isoformat().replace("+00:00", "Z") if baseline_rows else None,
            }
            post_snapshot = {
                "reading_ids": [r.id for r in post_rows],
                "median_value": str(post_value) if post_value is not None else None,
                "unit": "W",
                "resource_type": "ENERGY",
                "sample_count": len(post_rows),
                "source_statuses": sorted({r.source_status for r in post_rows}),
                "provenance": "SIMULATED",
                "window_start": post_start.isoformat().replace("+00:00", "Z") if post_start else None,
                "window_end": post_end.isoformat().replace("+00:00", "Z") if post_end else None,
            }
            required_change = {"required_drop_percent": str(required_drop_percent), "metric": "POWER", "unit": "W", "verification_window_seconds": verification_window_seconds}
            observed_change = {
                "observed_drop_percent": str(observed_drop.quantize(D4, rounding=ROUND_HALF_UP)) if observed_drop is not None else None,
                "baseline_w": str(baseline_value) if baseline_value is not None else None,
                "post_action_w": str(post_value) if post_value is not None else None,
                "comparator": "MEDIAN_POWER_DROP_PERCENT_V1",
            }
            verification = VerificationRecord(
                action_id=action_id,
                result=result_state,
                baseline_snapshot=baseline_snapshot,
                post_action_snapshot=post_snapshot,
                required_change=required_change,
                observed_change=observed_change,
                evidence_reading_ids=baseline_ids + [r.id for r in post_rows],
                verification_window_start=post_start,
                verification_window_end=post_end,
                created_at=when,
            )
            session.add(verification)
            transition = _transition_row(
                session, action=action, new_state=result_state, actor=actor,
                request_key=request_key,
                evidence={"verification_result": result_state, "verification_record_pending": True, "evidence_reading_ids": baseline_ids + [r.id for r in post_rows], "required_drop_percent": str(required_drop_percent), "observed_drop_percent": str(observed_drop) if observed_drop is not None else None},
                note=("Healthy post-action evidence met the configured drop threshold." if result_state == "VERIFIED_SUCCESS" else "Independent verification did not establish the configured success condition."),
                now=when,
            )
            action.state = result_state
            action.updated_at = when
            if result_state == "VERIFIED_SUCCESS":
                existing = session.scalar(select(SavingsLedgerEntry).where(SavingsLedgerEntry.action_id == action_id))
                if existing:
                    raise ConflictError("LEDGER_ENTRY_ALREADY_EXISTS", "A ledger row already exists for this action; the verified completion was aborted.")
                # Delta energy is integrated only over the actual verified virtual window.
                assert baseline_value is not None and post_value is not None and post_start is not None and post_end is not None
                delta_w = max(Decimal("0"), baseline_value - post_value)
                duration_seconds = Decimal(str((post_end - post_start).total_seconds()))
                energy_kwh = (delta_w * duration_seconds / Decimal("3600000")).quantize(D7, rounding=ROUND_HALF_UP)
                tariff = getattr(settings, "tariff_per_kwh", None)
                co2_factor = getattr(settings, "co2_factor_kg_per_kwh", None)
                # Cost stays unavailable until both tariff and currency are configured.
                currency = getattr(settings, "currency", None)
                cost_amount = (energy_kwh * Decimal(str(tariff))).quantize(D4, rounding=ROUND_HALF_UP) if tariff is not None and currency else None
                co2_kg = (energy_kwh * Decimal(str(co2_factor))).quantize(D6, rounding=ROUND_HALF_UP) if co2_factor is not None else None
                session.flush()  # Allocate transition/verification IDs inside the same transaction.
                assumptions = [
                    "All readings are simulated; this is not measured campus savings.",
                    "Median of three healthy baseline and post-action samples is used.",
                    "The median power delta is assumed to persist across the stated virtual verification window.",
                ]
                if cost_amount is None:
                    assumptions.append("Cost is unavailable because a tariff and currency identifier are not both configured.")
                if co2_kg is None:
                    assumptions.append("CO2e is unavailable because no emission factor is configured.")
                ledger = SavingsLedgerEntry(
                    action_id=action_id,
                    verification_transition_id=transition.id,
                    status="VERIFIED_SIMULATED",
                    energy_kwh=energy_kwh,
                    cost_amount=cost_amount,
                    currency=str(currency).upper() if cost_amount is not None else None,
                    water_liters=None,
                    co2_kg=co2_kg,
                    resource_type="ENERGY",
                    unit="kWh",
                    observation_start=post_start,
                    observation_end=post_end,
                    source_reading_ids=baseline_ids + [r.id for r in post_rows],
                    calculation_version="verified-energy-delta-v1",
                    calculation_inputs={
                        "baseline_power_w": str(baseline_value),
                        "post_power_w": str(post_value),
                        "delta_power_w": str(delta_w),
                        "duration_virtual_seconds": str(duration_seconds),
                        "tariff_per_kwh": str(tariff) if tariff is not None else None,
                        "currency": str(currency).upper() if currency else None,
                        "co2_factor_kg_per_kwh": str(co2_factor) if co2_factor is not None else None,
                        "formula": "kWh=(baseline_W-post_W)*verified_virtual_seconds/3600000",
                    },
                    assumptions=assumptions,
                    created_at=when,
                )
                session.add(ledger)
                # Resolution is based on independently verified outcome, never the ACK.
                event.status = "RESOLVED"
                event.last_updated_at = when
                event.updated_at = when
            session.flush()
        return result_state
    except Exception:
        session.rollback()
        raise
