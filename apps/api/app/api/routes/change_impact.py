"""Authenticated, bounded WC-046 analysis endpoints; no mutation endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict

from app.change_impact.models import ChangeDelta, ChangeImpactReport
from app.change_impact.service import ChangeImpactService, ImpactServiceCode, ImpactServiceError
from app.core.auth import CurrentUser, get_current_user
from app.catalog.display import CourseDisplayIdentity


institutional_router = APIRouter(prefix="/api/v1/institutional/change-impact",
                                 tags=["change-impact"], dependencies=[Depends(get_current_user)])
advisor_router = APIRouter(prefix="/api/v1/advisor/students",
                           tags=["change-impact"], dependencies=[Depends(get_current_user)])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


class InstitutionalImpactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    university_id: UUID | None = None
    delta: ChangeDelta


class AdvisorImpactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    delta: ChangeDelta


class AnalystAccessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    university_ids: tuple[UUID, ...]


def get_change_impact_service(request: Request) -> ChangeImpactService:
    service = getattr(request.app.state, "change_impact_service", None)
    if service is None:
        raise ImpactServiceError(ImpactServiceCode.IMPACT_SERVICE_UNAVAILABLE)
    return service


ImpactService = Annotated[ChangeImpactService, Depends(get_change_impact_service)]


@institutional_router.get("/access", response_model=AnalystAccessResponse)
async def institutional_change_access(
    user: AuthenticatedUser, service: ImpactService,
) -> AnalystAccessResponse:
    return AnalystAccessResponse(
        university_ids=await service.available_analyst_universities(user.user_id))


@institutional_router.get("/course-identities", response_model=list[CourseDisplayIdentity])
async def institutional_course_identities(
    university_id: UUID, user: AuthenticatedUser, service: ImpactService, response: Response,
):
    response.headers["Cache-Control"] = "private, no-store"
    return await service.course_identities(user.user_id, university_id)


@institutional_router.post("/evaluate", response_model=ChangeImpactReport)
async def evaluate_institutional_change(
    body: InstitutionalImpactRequest, user: AuthenticatedUser, service: ImpactService,
) -> ChangeImpactReport:
    return await service.evaluate_institutional(user.user_id, body.delta,
                                                university_id=body.university_id)


@advisor_router.post("/{student_user_id}/change-impact/evaluate", response_model=ChangeImpactReport)
async def evaluate_assigned_student_change(
    student_user_id: UUID, body: AdvisorImpactRequest,
    user: AuthenticatedUser, service: ImpactService,
) -> ChangeImpactReport:
    return await service.evaluate_advisor(user.user_id, student_user_id, body.delta)
