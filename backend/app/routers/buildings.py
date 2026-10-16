from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.repositories import create_building, create_room, get_building, list_buildings, list_rooms
from app.schemas import BuildingCreate, BuildingOut, RoomCreate, RoomOut

router = APIRouter(tags=["campus metadata"])


@router.get("/buildings", response_model=list[BuildingOut])
def get_buildings(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    return list_buildings(db, limit=limit)


@router.post("/buildings", response_model=BuildingOut, status_code=201)
def post_building(payload: BuildingCreate, db: Session = Depends(get_db)):
    return create_building(db, payload)


@router.get("/buildings/{building_id}", response_model=BuildingOut)
def building_detail(building_id: str, db: Session = Depends(get_db)):
    return get_building(db, building_id)


@router.get("/rooms", response_model=list[RoomOut])
def get_rooms(
    building_id: str | None = None,
    limit: int = Query(default=250, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return list_rooms(db, building_id=building_id, limit=limit)


@router.post("/rooms", response_model=RoomOut, status_code=201)
def post_room(payload: RoomCreate, db: Session = Depends(get_db)):
    return create_room(db, payload)
