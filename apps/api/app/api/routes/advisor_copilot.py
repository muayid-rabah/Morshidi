"""Authenticated read-only Advisor Copilot execution route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.advisor_copilot import (
    AdvisorCopilotService,
    AdvisorCopilotServiceError,
    AdvisorCopilotServiceErrorCode,
    AdvisorToolExecutionRequest,
    AdvisorToolExecutionResponse,
)
from app.core.auth import CurrentUser, get_current_user

router = APIRouter(
    prefix="/api/v1/advisor/tools",
    tags=["advisor-copilot"],
    dependencies=[Depends(get_current_user)],
)
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


def get_advisor_copilot_service(request: Request) -> AdvisorCopilotService:
    service = getattr(request.app.state, "advisor_copilot_service", None)
    if service is None:
        raise AdvisorCopilotServiceError(
            code=AdvisorCopilotServiceErrorCode.PERSISTENCE_UNAVAILABLE,
            detail="Advisor Copilot service is not configured",
            status_code=503,
        )
    return service


CopilotServiceDependency = Annotated[AdvisorCopilotService, Depends(get_advisor_copilot_service)]


@router.post(
    "/execute",
    response_model=AdvisorToolExecutionResponse,
    responses={
        200: {"description": "Tool executed successfully"},
        401: {"description": "Authentication is required"},
        403: {"description": "Advisor access denied; explicit assignment and role required"},
        404: {"description": "Scoped student academic resource is unavailable"},
        422: {"description": "Tool input parameters or tool identifier are invalid"},
        503: {"description": "Storage or upstream service is unavailable"},
        504: {"description": "Academic computation timed out"},
    },
)
async def execute_advisor_tool(
    body: AdvisorToolExecutionRequest,
    user: AuthenticatedUser,
    service: CopilotServiceDependency,
) -> AdvisorToolExecutionResponse:
    """Executes a closed, deterministic Advisor Copilot tool under strict P7.4 advisor authorization."""
    return await service.execute_tool(user.user_id, body)
