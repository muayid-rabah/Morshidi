"""Authenticated aggregate-only institutional demand route."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.schemas.mock_registration import InstitutionalDemandResponse
from app.core.auth import CurrentUser, get_current_user
from app.mock_registration_service.institutional_service import InstitutionalDemandService
from app.mock_registration_service.mapping import institutional_response
from app.mock_registration_service.errors import MockRegistrationServiceError, ServiceErrorCode

router = APIRouter(prefix="/api/v1/institutional", tags=["institutional-demand"],
                   dependencies=[Depends(get_current_user)])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


def get_institutional_demand_service(request: Request) -> InstitutionalDemandService:
    service = getattr(request.app.state, "institutional_demand_service", None)
    if service is None:
        raise MockRegistrationServiceError(ServiceErrorCode.PERSISTENCE_UNAVAILABLE)
    return service


DemandService = Annotated[InstitutionalDemandService, Depends(get_institutional_demand_service)]


@router.get("/demand", response_model=InstitutionalDemandResponse)
async def institutional_demand(
    user: AuthenticatedUser, service: DemandService,
    university_id: Annotated[UUID, Query()], target_period_id: Annotated[UUID, Query()],
    study_plan_id: Annotated[UUID | None, Query()] = None,
    course_code: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
) -> InstitutionalDemandResponse:
    return institutional_response(await service.demand(
        user.user_id, university_id=university_id, target_period_id=target_period_id,
        study_plan_id=study_plan_id, course_code=course_code))
