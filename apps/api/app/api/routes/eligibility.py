"""FastAPI transport adapter for the deterministic CAN TAKE service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.schemas.eligibility import (
    ApiErrorResponse,
    AcademicRuleTraceResponse,
    CanTakeDecisionResponse,
    CanTakeRequestBody,
    DependencyGroupEvidenceResponse,
    TargetAttemptStateResponse,
)
from app.rules.models import CanTakeDecision, CanTakeError, StudentCourseAttempt
from app.services.eligibility import EligibilityConfigurationError, EligibilityService

router = APIRouter(prefix="/api/v1/eligibility", tags=["eligibility"])


def get_eligibility_service(request: Request) -> EligibilityService:
    """Return the lifespan-wired service, never constructing a client per request."""

    service = getattr(request.app.state, "eligibility_service", None)
    if service is None:
        raise EligibilityConfigurationError("Catalog service is not configured")
    return service


@router.post(
    "/can-take",
    response_model=CanTakeDecisionResponse | ApiErrorResponse,
    responses={
        400: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
        500: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
    },
)
async def can_take(
    body: CanTakeRequestBody,
    service: EligibilityService = Depends(get_eligibility_service),
) -> CanTakeDecisionResponse | ApiErrorResponse:
    """Evaluate verified prerequisites for request-provided attempt history."""

    result = await service.evaluate_can_take(
        body.study_plan_id,
        body.target_course_code,
        tuple(
            StudentCourseAttempt(course_code=item.course_code, outcome=item.outcome)
            for item in body.attempts
        ),
    )
    if isinstance(result, CanTakeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "kind": "error",
                "error_code": result.error_code.value,
                "detail": "Invalid eligibility request",
            },
        )
    return _decision_response(result)


def _decision_response(result: CanTakeDecision) -> CanTakeDecisionResponse:
    """Map explicit pure-engine evidence to the deliberate public response shape."""

    return CanTakeDecisionResponse(
        decision=result.decision,
        study_plan_id=result.study_plan_id,
        target_course_code=result.target_course_code,
        prerequisite_logic_status=result.prerequisite_logic_status,
        target_attempt_state=TargetAttemptStateResponse(
            has_passed_target=result.target_attempt_state.has_passed_target,
            has_in_progress_target=result.target_attempt_state.has_in_progress_target,
        ),
        satisfied_dependency_groups=[_group_response(group) for group in result.satisfied_dependency_groups],
        missing_dependency_groups=[_group_response(group) for group in result.missing_dependency_groups],
        reasons=list(result.reasons),
        review_reasons=list(result.review_reasons),
        raw_prerequisite_text=result.raw_prerequisite_text,
        target_name_ar=result.target_name_ar,
        target_name_en=result.target_name_en,
        academic_rule_traces=[AcademicRuleTraceResponse.model_validate(item, from_attributes=True)
                              for item in result.academic_rule_traces],
    )


def _group_response(group) -> DependencyGroupEvidenceResponse:
    return DependencyGroupEvidenceResponse(
        group_number=group.group_number,
        dependency_type=group.dependency_type,
        option_course_codes=list(group.option_course_codes),
        passed_option_course_codes=list(group.passed_option_course_codes),
        non_passed_option_course_codes=list(group.non_passed_option_course_codes),
    )
