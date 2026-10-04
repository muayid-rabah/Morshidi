"""Authenticated read-only Institutional Intelligence route."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.core.auth import CurrentUser, get_current_user
from app.institutional_intelligence_service import (
    InstitutionalIntelligenceResponse,
    InstitutionalIntelligenceService,
    InstitutionalIntelligenceServiceError,
    InstitutionalIntelligenceServiceErrorCode,
)

router = APIRouter(
    prefix="/api/v1/institutional",
    tags=["institutional-intelligence"],
    dependencies=[Depends(get_current_user)],
)
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


def get_institutional_intelligence_service(request: Request) -> InstitutionalIntelligenceService:
    service = getattr(request.app.state, "institutional_intelligence_service", None)
    if service is None:
        raise InstitutionalIntelligenceServiceError(
            InstitutionalIntelligenceServiceErrorCode.PERSISTENCE_UNAVAILABLE
        )
    return service


IntelligenceService = Annotated[
    InstitutionalIntelligenceService, Depends(get_institutional_intelligence_service)
]


@router.get(
    "/intelligence",
    response_model=InstitutionalIntelligenceResponse,
    responses={
        200: {"description": "Institutional Intelligence evaluated successfully"},
        401: {"description": "Authentication is required"},
        403: {"description": "Institutional analyst access is denied"},
        404: {"description": "Target period, study plan, or course is unavailable"},
        422: {"description": "Scope parameters are invalid"},
        503: {"description": "Storage or upstream service is unavailable"},
    },
)
async def get_institutional_intelligence(
    user: AuthenticatedUser,
    service: IntelligenceService,
    target_period_id: Annotated[UUID, Query(description="Target planning period ID")],
    study_plan_id: Annotated[UUID, Query(description="Authoritative study plan ID")],
    course_code: Annotated[str, Query(min_length=1, max_length=50, description="Course code to evaluate")],
    university_id: Annotated[UUID | None, Query(description="Optional explicit university context; validated against active membership")] = None,
) -> InstitutionalIntelligenceResponse:
    """Evaluates 13 signals and 6 alerts for a course under authoritative analyst authorization."""
    return await service.evaluate(
        subject=user.user_id,
        target_period_id=target_period_id,
        study_plan_id=study_plan_id,
        course_code=course_code,
        university_id=university_id,
    )

