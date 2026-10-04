"""Authenticated, finite-metric WC-039 institutional query endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.core.auth import CurrentUser, get_current_user
from app.institutional_ai_query.models import InstitutionalAIQueryRequest, InstitutionalAIQueryResponse
from app.institutional_ai_query.service import InstitutionalAIQueryService
from app.institutional_intelligence_service import (
    InstitutionalIntelligenceServiceError, InstitutionalIntelligenceServiceErrorCode,
)


router = APIRouter(prefix="/api/v1/institutional/ai-query", tags=["institutional-ai-query"],
                   dependencies=[Depends(get_current_user)])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


class AnalystAccessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    university_ids: tuple[UUID, ...]


def get_query_service(request: Request) -> InstitutionalAIQueryService:
    service = getattr(request.app.state, "institutional_ai_query_service", None)
    if service is None:
        raise InstitutionalIntelligenceServiceError(
            InstitutionalIntelligenceServiceErrorCode.PERSISTENCE_UNAVAILABLE)
    return service


QueryService = Annotated[InstitutionalAIQueryService, Depends(get_query_service)]


@router.get("/access", response_model=AnalystAccessResponse)
async def access(user: AuthenticatedUser, service: QueryService) -> AnalystAccessResponse:
    return AnalystAccessResponse(university_ids=await service.available_analyst_universities(user.user_id))


@router.post("", response_model=InstitutionalAIQueryResponse)
async def evaluate(
    body: InstitutionalAIQueryRequest, user: AuthenticatedUser, service: QueryService,
) -> InstitutionalAIQueryResponse:
    return await service.evaluate(user.user_id, body)
