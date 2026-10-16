from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.errors import DomainError
from app.db.base import utc_now
from app.db.models import ActionRecord, ActionTransition, CampusEvent, ScenarioRun
from app.repositories import append_action_transition
from app.simulator.runner import SCENARIOS, run_scenario
from app.simulator.schemas import DemoResetRequest, ScenarioRunOut, ScenarioRunRequest

router = APIRouter(tags=["deterministic simulator"])


@router.get("/scenarios")
def get_scenarios():
    return {
        "provenance": "SIMULATED",
        "threshold_policy": "Configurable demonstration defaults; not campus-validated production limits.",
        "outcome_modes": ["SUCCESS", "DROP_COMMAND", "ACK_IGNORE", "NOT_APPLICABLE"],
        "scenarios": SCENARIOS,
    }


@router.post("/scenarios/run", response_model=ScenarioRunOut, status_code=201)
def run_scenario_route(payload: ScenarioRunRequest, request: Request, db: Session = Depends(get_db)):
    result = run_scenario(
        db,
        request=payload,
        clock=request.app.state.clock,
        settings=request.app.state.settings,
    )
    return result


@router.get("/scenarios/runs")
def scenario_runs(limit: int = 50, db: Session = Depends(get_db)):
    if limit < 1 or limit > 100:
        raise DomainError("INVALID_LIMIT", "limit must be between 1 and 100.", status_code=422)
    rows = db.scalars(select(ScenarioRun).order_by(ScenarioRun.wall_started_at.desc()).limit(limit)).all()
    return [
        {
            "scenario_run_id": row.id,
            "scenario_type": row.scenario_name,
            "status": row.status,
            "provenance": row.provenance,
            "virtual_started_at": row.virtual_started_at.isoformat().replace("+00:00", "Z") if row.virtual_started_at else None,
            "virtual_ended_at": row.virtual_ended_at.isoformat().replace("+00:00", "Z") if row.virtual_ended_at else None,
            "wall_started_at": row.wall_started_at.isoformat().replace("+00:00", "Z"),
            "wall_ended_at": row.wall_ended_at.isoformat().replace("+00:00", "Z") if row.wall_ended_at else None,
            "request": row.request_payload,
            "result": row.result_payload,
            "error_type": row.error_message,
        }
        for row in rows
    ]


@router.post("/scenarios/reset-demo")
def reset_demo(payload: DemoResetRequest, request: Request, db: Session = Depends(get_db)):
    if not payload.confirm:
        raise DomainError("RESET_CONFIRMATION_REQUIRED", "Set confirm=true to archive active simulated demo incidents.", status_code=422)
    now = request.app.state.clock.virtual_now()
    # Preserve append-only action history and verified ledger. Reset is therefore a safe
    # logical reset of active demo incidents, not destructive deletion of auditable evidence.
    simulated_events = list(db.scalars(select(CampusEvent).where(CampusEvent.provenance == "SIMULATED", CampusEvent.status.in_(["OPEN", "ACKNOWLEDGED"]))).all())
    event_ids = {item.id for item in simulated_events}
    closed_ids: list[str] = []
    for event in simulated_events:
        event.status = "CLOSED"
        event.last_updated_at = now
        event.updated_at = now
        closed_ids.append(event.id)

    rejected_actions: list[str] = []
    if event_ids:
        pending = list(db.scalars(select(ActionRecord).where(ActionRecord.event_id.in_(event_ids), ActionRecord.state == "PENDING_APPROVAL")).all())
        # Append transitions after committing event state to avoid nested commits rolling them back.
        db.commit()
        for action in pending:
            append_action_transition(
                db,
                action_id=action.id,
                new_state="REJECTED",
                actor_or_source=payload.actor,
                evidence={"reason": payload.reason, "reset": True},
                note=f"Demo reset: {payload.reason}",
                request_key=f"demo-reset:{action.id}:{int(now.timestamp())}",
                now=now,
            )
            rejected_actions.append(action.id)
    else:
        db.commit()

    from app.db.base import new_id
    reset_run = ScenarioRun(
        id=new_id(),
        scenario_name="DEMO_RESET",
        provenance="SIMULATED",
        status="COMPLETED",
        virtual_started_at=now,
        virtual_ended_at=now,
        wall_started_at=utc_now(),
        wall_ended_at=utc_now(),
        request_payload={"confirm": True, "actor": payload.actor, "reason": payload.reason},
        result_payload={"closed_event_ids": closed_ids, "rejected_action_ids": rejected_actions, "audit_history_preserved": True},
    )
    db.add(reset_run)
    db.commit()
    return {
        "status": "COMPLETED",
        "reset_run_id": reset_run.id,
        "closed_event_ids": closed_ids,
        "rejected_action_ids": rejected_actions,
        "audit_history_preserved": True,
        "retained": ["sensor readings", "action transition history", "verification records", "verified impact ledger"],
        "message": "Active simulated incidents were archived. Auditable history was preserved; real-source records were not modified.",
    }
