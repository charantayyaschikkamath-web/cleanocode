from __future__ import annotations

from datetime import timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.errors import DomainError
from app.db.models import SavingsLedgerEntry
from app.repositories import get_event
from app.schemas import EventOut
from app.services.actions import (
    approve_action, create_action_proposal, get_action, latest_verification,
    list_action_transitions, list_actions, reject_action,
)
from app.simulator.schemas import ActionProposalRequest, ActionRejectRequest, VerificationSummary

router = APIRouter(tags=["actions and independent verification"])


def _action_out(action) -> dict[str, Any]:
    metadata = action.metadata_json or {}
    return {
        "id": action.id,
        "event_id": action.event_id,
        "action_type": action.action_type,
        "status": action.state,
        "provenance": metadata.get("provenance", "SIMULATED"),
        "idempotency_key": action.idempotency_key,
        "actor": action.actor,
        "created_at": action.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": action.updated_at.isoformat().replace("+00:00", "Z"),
        "baseline_reading_ids": list(action.baseline_reading_ids or []),
        "baseline_snapshot": metadata.get("baseline_snapshot"),
        "outcome_mode": action.command_payload.get("outcome_mode", "SUCCESS"),
        "required_drop_percent": metadata.get("required_drop_percent"),
        "verification_window_seconds": metadata.get("verification_window_seconds"),
        "scenario_run_id": metadata.get("scenario_run_id"),
    }


def _verification_out(record) -> dict[str, Any] | None:
    if not record:
        return None
    return {
        "id": record.id,
        "result": record.result,
        "baseline_snapshot": record.baseline_snapshot,
        "post_action_snapshot": record.post_action_snapshot,
        "required_change": record.required_change,
        "observed_change": record.observed_change,
        "evidence_reading_ids": record.evidence_reading_ids,
        "verification_window_start": record.verification_window_start.isoformat().replace("+00:00", "Z") if record.verification_window_start else None,
        "verification_window_end": record.verification_window_end.isoformat().replace("+00:00", "Z") if record.verification_window_end else None,
    }


def _ledger_for_action(db: Session, action_id: str) -> dict[str, Any] | None:
    item = db.scalar(select(SavingsLedgerEntry).where(SavingsLedgerEntry.action_id == action_id))
    if not item:
        return None
    return {
        "id": item.id,
        "status": item.status,
        "energy_kwh": str(item.energy_kwh) if item.energy_kwh is not None else None,
        "cost_amount": str(item.cost_amount) if item.cost_amount is not None else None,
        "currency": item.currency,
        "water_liters": str(item.water_liters) if item.water_liters is not None else None,
        "co2_kg": str(item.co2_kg) if item.co2_kg is not None else None,
        "unit": item.unit,
        "calculation_version": item.calculation_version,
        "source_reading_ids": item.source_reading_ids,
        "assumptions": item.assumptions,
    }


@router.post("/actions/proposals", status_code=201)
def post_action_proposal(
    payload: ActionProposalRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=160),
    db: Session = Depends(get_db),
):
    if idempotency_key and idempotency_key != payload.idempotency_key:
        payload = payload.model_copy(update={"idempotency_key": idempotency_key})
    action = create_action_proposal(db, payload)
    return _action_out(action)


@router.get("/actions")
def get_actions(
    status: str | None = None,
    event_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return [_action_out(item) for item in list_actions(db, status=status, event_id=event_id, limit=limit)]


@router.get("/actions/{action_id}")
def action_detail(action_id: str, db: Session = Depends(get_db)):
    action = get_action(db, action_id)
    return {**_action_out(action), "verification": _verification_out(latest_verification(db, action_id)), "ledger_entry": _ledger_for_action(db, action_id)}


@router.post("/actions/{action_id}/approve")
def approve_action_route(
    action_id: str,
    request: Request,
    actor: str = Query(default="operator", min_length=1, max_length=120),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=160),
    db: Session = Depends(get_db),
):
    action = approve_action(
        db,
        action_id=action_id,
        actor=actor,
        request_key=idempotency_key,
        settings=request.app.state.settings,
        clock=request.app.state.clock,
    )
    verification = latest_verification(db, action_id)
    return {
        **_action_out(action),
        "verification": _verification_out(verification),
        "ledger_entry": _ledger_for_action(db, action_id),
        "acknowledgement_is_success": False,
        "message": "The action outcome is determined by persisted verification evidence, not by acknowledgement.",
    }


@router.post("/actions/{action_id}/reject")
def reject_action_route(
    action_id: str,
    payload: ActionRejectRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=160),
    db: Session = Depends(get_db),
):
    action = reject_action(session=db, action_id=action_id, actor=payload.actor, reason=payload.reason, request_key=idempotency_key)
    return _action_out(action)


@router.get("/actions/{action_id}/transitions")
def action_transitions(action_id: str, db: Session = Depends(get_db)):
    return [
        {
            "id": row.id,
            "action_id": row.action_id,
            "sequence_no": row.sequence_no,
            "previous_state": row.previous_state,
            "new_state": row.new_state,
            "actor_or_source": row.actor_or_source,
            "occurred_at": row.occurred_at.isoformat().replace("+00:00", "Z"),
            "evidence": row.evidence,
            "note": row.note,
            "request_key": row.request_key,
        }
        for row in list_action_transitions(db, action_id)
    ]


@router.get("/actions/{action_id}/verification", response_model=VerificationSummary)
def action_verification(action_id: str, db: Session = Depends(get_db)):
    record = latest_verification(db, action_id)
    return _verification_out(record) or {"id": None, "result": None, "evidence_reading_ids": []}
