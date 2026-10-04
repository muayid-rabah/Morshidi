"""Authenticated student Mock Registration routes; no academic logic."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.schemas.mock_registration import (
    StudentIntentResponse, SubmitIntentRequest, WithdrawIntentRequest,
)
from app.core.auth import CurrentUser, get_current_user
from app.mock_registration.models import ValidationStatus
from app.mock_registration_service.mapping import student_response
from app.mock_registration_service.student_service import MockRegistrationStudentService
from app.mock_registration_service.errors import MockRegistrationServiceError, ServiceErrorCode

router = APIRouter(prefix="/api/v1/me/mock-registration", tags=["mock-registration"],
                   dependencies=[Depends(get_current_user)])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


def get_mock_registration_student_service(request: Request) -> MockRegistrationStudentService:
    service = getattr(request.app.state, "mock_registration_student_service", None)
    if service is None:
        raise MockRegistrationServiceError(ServiceErrorCode.PERSISTENCE_UNAVAILABLE)
    return service


StudentService = Annotated[MockRegistrationStudentService,
                           Depends(get_mock_registration_student_service)]


@router.get("/current", response_model=StudentIntentResponse)
async def current_intent(target_period_id: Annotated[UUID, Query()], user: AuthenticatedUser,
                         service: StudentService) -> StudentIntentResponse:
    return student_response(await service.current(user.user_id, target_period_id))


@router.post("/revisions", response_model=StudentIntentResponse,
             status_code=status.HTTP_201_CREATED)
async def submit_intent(body: SubmitIntentRequest, response: Response,
                        user: AuthenticatedUser, service: StudentService) -> StudentIntentResponse:
    result = await service.submit(user.user_id, **body.model_dump())
    if result.submission_validation_status is ValidationStatus.REVIEW_REQUIRED:
        response.status_code = status.HTTP_202_ACCEPTED
    return student_response(result)


@router.post("/withdrawals", response_model=StudentIntentResponse,
             status_code=status.HTTP_201_CREATED)
async def withdraw_intent(body: WithdrawIntentRequest, user: AuthenticatedUser,
                          service: StudentService) -> StudentIntentResponse:
    return student_response(await service.withdraw(user.user_id, **body.model_dump()))
