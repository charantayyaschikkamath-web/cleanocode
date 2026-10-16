from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.facts import assemble_overview_facts
from app.schemas import OverviewFactsOut

router = APIRouter(tags=["facts and KPIs"])


@router.get("/facts/overview", response_model=OverviewFactsOut)
def overview_facts(request: Request, db: Session = Depends(get_db)):
    return assemble_overview_facts(db, request.app.state.clock.wall_now())
