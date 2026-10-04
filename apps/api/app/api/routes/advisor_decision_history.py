"""Authenticated, read-only Decision History for an exactly assigned advisor."""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.routes.decision_history import get_decision_trace_service
from app.api.schemas.decision_history import (
    StudentDecisionHistoryDetailResponse, StudentDecisionHistoryItemResponse,
)
from app.core.auth import CurrentUser, get_current_user
from app.decision_trace_persistence import DecisionTraceService


router = APIRouter(prefix="/api/v1/advisor/students", tags=["advisor-decision-history"])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]
HistoryService = Annotated[DecisionTraceService, Depends(get_decision_trace_service)]
_SAFE_ENTRY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


@router.get("/{student_user_id}/decision-history", response_model=list[StudentDecisionHistoryItemResponse])
async def list_advisor_decision_history(
    student_user_id: UUID, user: AuthenticatedUser, service: HistoryService,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    before_created_at: datetime | None = None, before_entry_id: str | None = None,
) -> list[StudentDecisionHistoryItemResponse]:
    if (before_created_at is None) != (before_entry_id is None):
        raise HTTPException(status_code=422, detail="Both history cursor fields are required")
    if before_entry_id is not None and _SAFE_ENTRY_ID.fullmatch(before_entry_id) is None:
        raise HTTPException(status_code=422, detail="Invalid history cursor")
    if before_created_at is not None and (before_created_at.tzinfo is None or before_created_at.utcoffset() is None):
        raise HTTPException(status_code=422, detail="Invalid history cursor")
    items = await service.list_advisor_history(
        user, student_user_id, limit=limit,
        before_created_at=before_created_at, before_entry_id=before_entry_id,
    )
    return [StudentDecisionHistoryItemResponse.model_validate(asdict(item)) for item in items]


@router.get("/{student_user_id}/decision-history/{ledger_entry_id}",
            response_model=StudentDecisionHistoryDetailResponse)
async def get_advisor_decision_history_detail(
    student_user_id: UUID, ledger_entry_id: str, user: AuthenticatedUser, service: HistoryService,
) -> StudentDecisionHistoryDetailResponse:
    if _SAFE_ENTRY_ID.fullmatch(ledger_entry_id) is None:
        raise HTTPException(status_code=404, detail="Decision record was not found")
    detail = await service.get_advisor_history_detail(user, student_user_id, ledger_entry_id)
    return StudentDecisionHistoryDetailResponse.model_validate(asdict(detail))
