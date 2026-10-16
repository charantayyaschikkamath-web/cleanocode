from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.repositories import create_reading, list_readings
from app.schemas import ReadingCreate, ReadingOut

router = APIRouter(tags=["sensor readings"])


@router.post("/readings", response_model=ReadingOut, status_code=201)
def post_reading(payload: ReadingCreate, db: Session = Depends(get_db)):
    return create_reading(db, payload)


@router.get("/readings", response_model=list[ReadingOut])
def get_readings(
    building_id: str | None = None,
    room_id: str | None = None,
    resource_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return list_readings(db, building_id=building_id, room_id=room_id, resource_type=resource_type, limit=limit)
