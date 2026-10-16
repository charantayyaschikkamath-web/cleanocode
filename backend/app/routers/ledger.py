from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.repositories import list_savings_ledger
from app.schemas import LedgerEntryOut

router = APIRouter(tags=["verified impact ledger"])


@router.get("/ledger", response_model=list[LedgerEntryOut])
def get_ledger(
    resource_type: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Read-only list of savings created by the guarded verified-action service."""
    return list_savings_ledger(db, resource_type=resource_type, status=status, limit=limit)
