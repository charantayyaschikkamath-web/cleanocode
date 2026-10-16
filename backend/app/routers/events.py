from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.errors import DomainError
from app.db.models import CampusEvent, SensorReading
from app.repositories import create_event, create_feedback, get_event, list_events
from app.schemas import EventCreate, EventOut, FeedbackCreate, FeedbackOut
from app.rules.engine import evaluate_room_rules
from app.simulator.schemas import EventEvaluateRequest, EventFeedbackRequest

router = APIRouter(tags=["events and feedback"])


@router.post("/events", response_model=EventOut, status_code=201)
def post_event(payload: EventCreate, db: Session = Depends(get_db)):
    """Persist an explicitly supplied evidence-backed event. Detection rules live in Account 3."""
    return create_event(db, payload)


@router.post("/events/evaluate")
def evaluate_events(payload: EventEvaluateRequest, db: Session = Depends(get_db)):
    """Evaluate persisted inputs using transparent deterministic rules; never fabricates missing evidence."""
    try:
        events = evaluate_room_rules(
            db,
            building_id=payload.building_id,
            room_id=payload.room_id,
            reading_ids=payload.reading_ids,
            thresholds=payload.thresholds,
        )
    except ValueError as exc:
        raise DomainError("INVALID_EVIDENCE_SCOPE", str(exc), status_code=422) from exc
    return {"events": [EventOut.model_validate(event).model_dump(mode="json") for event in events], "count": len(events)}


@router.get("/events", response_model=list[EventOut])
def get_events(
    status: str | None = None,
    severity: str | None = None,
    event_type: str | None = None,
    building_id: str | None = None,
    room_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # Preserve Account 2's repository contract, then apply feature-specific filters.
    query = select(CampusEvent).order_by(CampusEvent.first_seen_at.desc()).limit(limit)
    if status:
        query = query.where(CampusEvent.status == status)
    if severity:
        query = query.where(CampusEvent.severity == severity)
    if event_type:
        query = query.where(CampusEvent.event_type == event_type)
    if building_id:
        query = query.where(CampusEvent.building_id == building_id)
    if room_id:
        query = query.where(CampusEvent.room_id == room_id)
    return list(db.scalars(query).all())


@router.get("/events/{event_id}", response_model=EventOut)
def event_detail(event_id: str, db: Session = Depends(get_db)):
    return get_event(db, event_id)


@router.get("/events/{event_id}/evidence")
def event_evidence(event_id: str, db: Session = Depends(get_db)):
    event = get_event(db, event_id)
    ids = list((event.evidence_snapshot or {}).get("reading_ids") or event.evidence_refs or [])
    readings = list(db.scalars(select(SensorReading).where(SensorReading.id.in_(ids))).all()) if ids else []
    by_id = {row.id: row for row in readings}
    ordered = [by_id[item_id] for item_id in ids if item_id in by_id]
    return {
        "event": EventOut.model_validate(event).model_dump(mode="json"),
        "evidence_snapshot": event.evidence_snapshot,
        "reading_ids": ids,
        "readings": [
            {
                "id": row.id,
                "sensor_id": row.sensor_id,
                "source_type": row.source_type,
                "resource_type": row.resource_type,
                "value": str(row.value),
                "unit": row.unit,
                "observed_at": row.observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_status": row.source_status,
                "freshness_seconds": row.freshness_seconds,
                "provenance": row.provenance,
                "metadata": row.metadata_json,
            }
            for row in ordered
        ],
        "evidence_missing_ids": [item_id for item_id in ids if item_id not in by_id],
    }


def _store_feedback(db: Session, *, event_id: str, label: str, reason: str | None, actor: str):
    event = get_event(db, event_id)
    item = create_feedback(db, FeedbackCreate(event_id=event_id, feedback_type=label, comment=reason, actor=actor))
    # Feedback is append-only. Event evidence/snapshot are intentionally untouched.
    if label == "FALSE_POSITIVE":
        event.status = "FALSE_POSITIVE"
    elif label == "CONFIRMED":
        event.status = "ACKNOWLEDGED"
    event.last_updated_at = item.created_at
    event.updated_at = item.created_at
    db.commit()
    db.refresh(event)
    return item


@router.post("/events/{event_id}/feedback", response_model=FeedbackOut, status_code=201)
def post_event_feedback(
    event_id: str,
    payload: EventFeedbackRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=160),
    db: Session = Depends(get_db),
):
    # The Account 2 feedback schema has no idempotency-key column; accept the header for
    # forward compatibility but do not falsely claim de-duplication until the shared schema changes.
    return _store_feedback(db, event_id=event_id, label=payload.label, reason=payload.reason, actor=payload.actor)


# Account 2 route retained for backward compatibility with its current frontend/tests.
@router.post("/feedback", response_model=FeedbackOut, status_code=201)
def post_feedback(
    payload: FeedbackCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=160),
    db: Session = Depends(get_db),
):
    return _store_feedback(db, event_id=payload.event_id, label=payload.feedback_type, reason=payload.comment, actor=payload.actor)
