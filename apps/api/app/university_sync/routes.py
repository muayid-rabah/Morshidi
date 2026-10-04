from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.auth import CurrentUser, get_current_user
from app.offerings.provider import OfferingProviderUnavailable

router = APIRouter(prefix="/api/v1", tags=["university integration"])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


def _contract(request: Request):
    contract = getattr(request.app.state, "university_contract", None)
    if contract is None:
        raise HTTPException(503, detail={"kind": "error", "code": "UNIVERSITY_UNAVAILABLE"})
    return contract


def _student_id(user: CurrentUser) -> str:
    match = re.fullmatch(r"(\d{9})@std\.morshidi\.edu\.jo", (user.email or "").strip().lower())
    if not match:
        raise HTTPException(403, detail={"kind": "error", "code": "STUDENT_SCOPE_REQUIRED"})
    return match.group(1)


@router.get("/me/university-context")
async def own_university_context(user: AuthenticatedUser, request: Request):
    """Read this account's live University profile and record; never accepts a client-supplied student ID."""
    contract = _contract(request)
    try:
        return await contract.load_student(_student_id(user))
    except OfferingProviderUnavailable:
        raise HTTPException(503, detail={"kind": "error", "code": "UNIVERSITY_UNAVAILABLE"}) from None


@router.get("/periods")
async def current_periods(user: AuthenticatedUser, request: Request):
    contract = _contract(request)
    try:
        calendar = await contract.current_term()
        current = calendar["currentTerm"]
        row = await contract.find_period(str(current["code"]))
    except (OfferingProviderUnavailable, KeyError, TypeError):
        raise HTTPException(503, detail={"kind": "error", "code": "PERIOD_MAPPING_UNAVAILABLE"}) from None
    if row is None:
        raise HTTPException(503, detail={"kind": "error", "code": "CURRENT_PERIOD_NOT_MIGRATED"})
    return [{"id": row["id"], "code": row["period_key"], "label": current["label"], "is_current": True}]
