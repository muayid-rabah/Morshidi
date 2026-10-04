"""Authenticated, read-only owner projection of immutable decision traces."""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.schemas.decision_history import (
    StudentDecisionHistoryDetailResponse, StudentDecisionHistoryItemResponse,
)
from app.core.auth import CurrentUser, get_current_user
from app.decision_trace_persistence import DecisionTraceService


router = APIRouter(prefix="/api/v1/me/decision-history", tags=["decision-history"])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]
_SAFE_ENTRY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def get_decision_trace_service(request: Request) -> DecisionTraceService:
    service = getattr(request.app.state, "decision_trace_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Decision History is unavailable")
    return service


HistoryService = Annotated[DecisionTraceService, Depends(get_decision_trace_service)]


@router.get("", response_model=list[StudentDecisionHistoryItemResponse])
async def list_decision_history(
    user: AuthenticatedUser,
    service: HistoryService,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before_created_at: datetime | None = None,
    before_entry_id: str | None = None,
) -> list[StudentDecisionHistoryItemResponse]:
    if (before_created_at is None) != (before_entry_id is None):
        raise HTTPException(status_code=422, detail="Both history cursor fields are required")
    if before_entry_id is not None and _SAFE_ENTRY_ID.fullmatch(before_entry_id) is None:
        raise HTTPException(status_code=422, detail="Invalid history cursor")
    if before_created_at is not None and (before_created_at.tzinfo is None or before_created_at.utcoffset() is None):
        raise HTTPException(status_code=422, detail="Invalid history cursor")
    items = await service.list_student_history(
        user, limit=limit, before_created_at=before_created_at, before_entry_id=before_entry_id,
    )
    return [StudentDecisionHistoryItemResponse.model_validate(asdict(item)) for item in items]


@router.get("/{ledger_entry_id}", response_model=StudentDecisionHistoryDetailResponse)
async def get_decision_history_detail(
    ledger_entry_id: str, user: AuthenticatedUser, service: HistoryService,
) -> StudentDecisionHistoryDetailResponse:
    if _SAFE_ENTRY_ID.fullmatch(ledger_entry_id) is None:
        raise HTTPException(status_code=404, detail="Decision record was not found")
    detail = await service.get_student_history_detail(user, ledger_entry_id)
    return StudentDecisionHistoryDetailResponse.model_validate(asdict(detail))
