"""Authenticated self-service profile, attempt, and eligibility routes."""

import asyncio
from contextlib import suppress
from threading import Event
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.api.routes.eligibility import _decision_response
from app.api.schemas.eligibility import CanTakeDecisionResponse
from app.api.schemas.student import (
    AcademicProfileResponse, AttemptCreateRequest, AttemptUpdateRequest,
    CourseAttemptResponse, ProfileCreateRequest, ProfileUpdateRequest,
)
from app.api.schemas.progress import AcademicProgressResponse
from app.api.schemas.roadmap import AcademicRoadmapResponse
from app.api.schemas.academic_report import ModeledAcademicReportResponse
from app.api.schemas.recommendations import RecommendationResponse
from app.api.schemas.adaptive_courses import AdaptiveCourseResponse
from app.api.schemas.semester_planner import (
    SemesterPlanRequest,
    SemesterPlannerResponse,
)
from app.api.schemas.degree_path import (
    DegreePathRequest,
    DegreePathResponse,
)
from app.core.auth import CurrentUser, get_current_user
from app.catalog.display import CourseDisplayIdentity
from app.rules.models import CanTakeDecision, Decision
from app.explainability_graph import (
    ExplainabilityGraph, GraphMode, build_eligibility_graph,
    build_recommendation_graph, build_semester_planner_graph, build_degree_path_graph,
)
from app.api.schemas.credit_timeline import (CreditTimelineRequest, CreditTimelineResponse,
                                             CreditComparisonRequest, CreditComparisonResponse)
from app.services.student import StudentConfigurationError, StudentService
from app.student.models import StudentAcademicState, StudentCourseAttemptRecord
from app.progress.models import AcademicProgress
from app.recommendations.models import RecommendationResult
from app.planner.models import SemesterPlannerResult
from app.degree_path.models import DegreePathResult

router = APIRouter(prefix="/api/v1/me", tags=["student"], dependencies=[Depends(get_current_user)])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


def get_student_service(request: Request) -> StudentService:
    service = getattr(request.app.state, "student_service", None)
    if service is None:
        raise StudentConfigurationError("Student service is not configured")
    return service


StudentServiceDependency = Annotated[StudentService, Depends(get_student_service)]


@router.get("/course-identities", response_model=list[CourseDisplayIdentity])
async def course_identities(user: AuthenticatedUser, service: StudentServiceDependency,
                            response: Response):
    response.headers["Cache-Control"] = "private, no-store"
    return await service.get_course_identities(user.user_id)


async def _watch_degree_path_disconnect(request: Request, cancelled: Event) -> None:
    """Signal the pure search loop when a client leaves after request parsing."""
    while True:
        # Request.is_disconnected() uses an immediately-cancelled AnyIO scope,
        # which can swallow cancellation from our cleanup on some ASGI receives.
        message = await request.receive()
        if message["type"] == "http.disconnect":
            cancelled.set()
            return


async def _request_degree_path(
    request: DegreePathRequest,
    user: CurrentUser,
    service: StudentService,
    http_request: Request,
) -> DegreePathResult:
    cancelled = Event()
    watcher = asyncio.create_task(
        _watch_degree_path_disconnect(http_request, cancelled), name="degree-path-disconnect",
    )
    try:
        return await service.get_degree_paths(
            user.user_id,
            max_credit_hours_per_semester=request.max_credit_hours_per_semester,
            max_courses_per_semester=request.max_courses_per_semester,
            max_semesters_ahead=request.max_semesters_ahead,
            max_paths=request.max_paths,
            cancel_event=cancelled,
        )
    finally:
        watcher.cancel()
        with suppress(asyncio.CancelledError):
            await watcher


@router.get("/academic-profile", response_model=AcademicProfileResponse)
async def get_profile(user: AuthenticatedUser, service: StudentServiceDependency) -> AcademicProfileResponse:
    return _profile_response(await service.get_profile(user.user_id))


@router.get("/academic-progress", response_model=AcademicProgressResponse)
async def get_academic_progress(
    user: AuthenticatedUser,
    service: StudentServiceDependency,
) -> AcademicProgressResponse:
    return _progress_response(await service.get_academic_progress(user.user_id))


@router.get("/academic-roadmap", response_model=AcademicRoadmapResponse)
async def get_academic_roadmap(
    user: AuthenticatedUser, service: StudentServiceDependency,
) -> AcademicRoadmapResponse:
    return AcademicRoadmapResponse.model_validate(
        await service.get_academic_roadmap(user.user_id), from_attributes=True,
    )


@router.get("/academic-report", response_model=ModeledAcademicReportResponse)
async def get_academic_report(
    user: AuthenticatedUser, service: StudentServiceDependency, response: Response,
) -> ModeledAcademicReportResponse:
    response.headers["Cache-Control"] = "private, no-store"
    return ModeledAcademicReportResponse.model_validate(
        await service.get_academic_report(user.user_id), from_attributes=True,
    )


@router.post("/academic-roadmap/modeled-path", response_model=AcademicRoadmapResponse)
async def generate_modeled_roadmap(
    body: DegreePathRequest, user: AuthenticatedUser,
    service: StudentServiceDependency, http_request: Request,
) -> AcademicRoadmapResponse:
    """Bounded path search runs only after an explicit authenticated request."""
    cancelled = Event()
    watcher = asyncio.create_task(
        _watch_degree_path_disconnect(http_request, cancelled), name="roadmap-path-disconnect",
    )
    try:
        modeled = await service.get_modeled_roadmap(
            user.user_id,
            max_credit_hours_per_semester=body.max_credit_hours_per_semester,
            max_courses_per_semester=body.max_courses_per_semester,
            max_semesters_ahead=body.max_semesters_ahead,
            max_paths=body.max_paths,
            cancel_event=cancelled,
        )
        return AcademicRoadmapResponse.model_validate(modeled, from_attributes=True)
    finally:
        watcher.cancel()
        with suppress(asyncio.CancelledError):
            await watcher


@router.post("/academic-profile", response_model=AcademicProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(body: ProfileCreateRequest, user: AuthenticatedUser, service: StudentServiceDependency) -> AcademicProfileResponse:
    return _profile_response(await service.create_profile(user.user_id, **body.model_dump()))


@router.patch("/academic-profile", response_model=AcademicProfileResponse)
async def update_profile(body: ProfileUpdateRequest, user: AuthenticatedUser, service: StudentServiceDependency) -> AcademicProfileResponse:
    return _profile_response(await service.update_profile(user.user_id, body.model_dump(exclude_unset=True)))


@router.delete("/academic-profile", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(user: AuthenticatedUser, service: StudentServiceDependency) -> Response:
    await service.delete_profile(user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/academic-profile/attempts", response_model=list[CourseAttemptResponse])
async def list_attempts(user: AuthenticatedUser, service: StudentServiceDependency) -> list[CourseAttemptResponse]:
    return [_attempt_response(row) for row in await service.list_attempts(user.user_id)]


@router.post("/academic-profile/attempts", response_model=CourseAttemptResponse, status_code=status.HTTP_201_CREATED)
async def create_attempt(body: AttemptCreateRequest, user: AuthenticatedUser, service: StudentServiceDependency) -> CourseAttemptResponse:
    values = body.model_dump()
    code, attempt_status = values.pop("course_code"), values.pop("status")
    values["reported_grade_text"] = values.pop("raw_grade_text")
    return _attempt_response(await service.create_attempt(user.user_id, code, attempt_status, **values))


@router.patch("/academic-profile/attempts/{attempt_id}", response_model=CourseAttemptResponse)
async def update_attempt(attempt_id: UUID, body: AttemptUpdateRequest, user: AuthenticatedUser, service: StudentServiceDependency) -> CourseAttemptResponse:
    return _attempt_response(await service.update_attempt(user.user_id, attempt_id, body.model_dump(exclude_unset=True)))


@router.delete("/academic-profile/attempts/{attempt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attempt(attempt_id: UUID, user: AuthenticatedUser, service: StudentServiceDependency) -> Response:
    await service.delete_attempt(user.user_id, attempt_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/eligibility/{target_course_code}", response_model=CanTakeDecisionResponse)
async def profile_can_take(target_course_code: str, user: AuthenticatedUser, service: StudentServiceDependency) -> CanTakeDecisionResponse:
    result = await service.evaluate_can_take(user.user_id, target_course_code)
    if not isinstance(result, CanTakeDecision):
        raise RuntimeError("Validated profile eligibility produced a request error")
    return _decision_response(result)


@router.get("/eligibility/{target_course_code}/explanation-graph", response_model=ExplainabilityGraph)
async def profile_can_take_explanation_graph(
    target_course_code: str, user: AuthenticatedUser, service: StudentServiceDependency,
    request: Request,
    mode: GraphMode = GraphMode.WHY, target: Decision | None = None,
) -> ExplainabilityGraph:
    if set(request.query_params) - {"mode", "target"}:
        raise HTTPException(status_code=422, detail="Unsupported graph query parameter")
    if mode is GraphMode.WHY and target is not None:
        raise HTTPException(status_code=422, detail="WHY does not accept a target decision")
    if mode is GraphMode.WHY_NOT and target not in {None, Decision.ELIGIBLE}:
        raise HTTPException(status_code=422, detail="Unsupported alternative decision")
    result = await service.evaluate_can_take(user.user_id, target_course_code)
    if not isinstance(result, CanTakeDecision):
        raise RuntimeError("Validated profile eligibility produced a request error")
    if mode is GraphMode.WHY_NOT and result.decision is Decision.ELIGIBLE:
        raise HTTPException(status_code=422, detail="The requested alternative is already current")
    try:
        return build_eligibility_graph(
            result, mode=mode,
            target_decision=Decision.ELIGIBLE if mode is GraphMode.WHY_NOT else None,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Eligibility evidence cannot be safely graphed") from error


def _profile_response(state: StudentAcademicState) -> AcademicProfileResponse:
    return AcademicProfileResponse(id=state.profile_id, study_plan_id=state.study_plan_id,
        reported_cumulative_gpa=state.reported_cumulative_gpa,
        reported_gpa_scale=state.reported_gpa_scale,
        reported_earned_credit_hours=state.reported_earned_credit_hours,
        created_at=state.created_at, updated_at=state.updated_at)


def _attempt_response(row: StudentCourseAttemptRecord) -> CourseAttemptResponse:
    return CourseAttemptResponse(id=row.attempt_id, course_code=row.course_code, status=row.outcome,
        course_name_ar=row.course_name_ar, course_name_en=row.course_name_en,
        attempt_sequence=row.attempt_sequence, term_label=row.term_label, attempted_on=row.attempted_on,
        raw_grade_text=row.reported_grade_text, record_source=row.record_source,
        created_at=row.created_at, updated_at=row.updated_at)


def _progress_response(progress: AcademicProgress) -> AcademicProgressResponse:
    return AcademicProgressResponse.model_validate(progress, from_attributes=True)


@router.get("/course-recommendations", response_model=RecommendationResponse)
async def get_course_recommendations(
    user: AuthenticatedUser,
    service: StudentServiceDependency,
    limit: Annotated[
        int | None,
        Query(
            ge=1,
            le=100,
            description="Optional maximum number of ranked recommendations to return.",
        ),
    ] = None,
) -> RecommendationResponse:
    result = await service.get_course_recommendations(user.user_id, limit=limit)
    return _recommendation_response(result)


@router.get("/adaptive-course-intelligence", response_model=AdaptiveCourseResponse)
async def get_adaptive_course_intelligence(
    user: AuthenticatedUser, service: StudentServiceDependency, response: Response, request: Request,
) -> AdaptiveCourseResponse:
    if request.query_params:
        raise HTTPException(status_code=422, detail="Unsupported query parameters")
    response.headers["Cache-Control"] = "private, no-store"
    return AdaptiveCourseResponse.model_validate(
        await service.get_adaptive_course_intelligence(user.user_id), from_attributes=True,
    )


def _recommendation_response(result: RecommendationResult) -> RecommendationResponse:
    return RecommendationResponse.model_validate(result, from_attributes=True)


@router.get("/course-recommendations/explanation-graph", response_model=ExplainabilityGraph)
async def get_course_recommendations_explanation_graph(
    user: AuthenticatedUser, service: StudentServiceDependency, request: Request,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    mode: GraphMode = GraphMode.WHY, course_code: str | None = None,
) -> ExplainabilityGraph:
    if set(request.query_params) - {"limit", "mode", "course_code"}:
        raise HTTPException(status_code=422, detail="Unsupported graph query parameter")
    if (mode is GraphMode.WHY and course_code is not None) or (mode is GraphMode.WHY_NOT and course_code is None):
        raise HTTPException(status_code=422, detail="Invalid graph query mode")
    result = await service.get_course_recommendations(user.user_id, limit=limit)
    try:
        return build_recommendation_graph(result, mode=mode, course_code=course_code)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Recommendation evidence cannot be safely graphed") from error


@router.post("/semester-plans", response_model=SemesterPlannerResponse)
async def create_semester_plans(
    request: SemesterPlanRequest,
    user: AuthenticatedUser,
    service: StudentServiceDependency,
) -> SemesterPlannerResponse:
    balance_options = ({"accept_heavy_balance": True}
                       if request.accept_heavy_balance else {})
    result = await service.get_semester_plans(
        user.user_id,
        max_credit_hours=request.max_credit_hours,
        max_courses=request.max_courses,
        max_options=request.max_options,
        **balance_options,
    )
    return _planner_response(result)


def _planner_response(result: SemesterPlannerResult) -> SemesterPlannerResponse:
    return SemesterPlannerResponse.model_validate(result, from_attributes=True)


@router.post("/semester-plans/explanation-graph", response_model=ExplainabilityGraph)
async def create_semester_plans_explanation_graph(
    request: SemesterPlanRequest, user: AuthenticatedUser, service: StudentServiceDependency,
    http_request: Request,
) -> ExplainabilityGraph:
    if http_request.query_params:
        raise HTTPException(status_code=422, detail="Unsupported graph query parameter")
    result = await service.get_semester_plans(
        user.user_id, max_credit_hours=request.max_credit_hours,
        max_courses=request.max_courses, max_options=request.max_options,
    )
    try:
        return build_semester_planner_graph(result)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Planner evidence cannot be safely graphed") from error


@router.post("/degree-paths", response_model=DegreePathResponse)
async def create_degree_paths(
    request: DegreePathRequest,
    user: AuthenticatedUser,
    service: StudentServiceDependency,
    http_request: Request,
) -> DegreePathResponse:
    from time import perf_counter
    import logging

    started = perf_counter()
    result = await _request_degree_path(request, user, service, http_request)
    service_ms = (perf_counter() - started) * 1000
    response = _degree_path_response(result)
    logging.getLogger(__name__).info(
        "degree_path_timing auth_ms=%s service_ms=%.1f serialization_ms=%.1f post_auth_ms=%.1f",
        getattr(http_request.state, "auth_ms", None), service_ms,
        (perf_counter() - started) * 1000 - service_ms,
        (perf_counter() - started) * 1000,
    )
    return response


@router.post("/degree-paths/credit-timeline", response_model=CreditTimelineResponse)
async def create_credit_timeline(
    body: CreditTimelineRequest, user: AuthenticatedUser, service: StudentServiceDependency,
) -> CreditTimelineResponse:
    try:
        result = await service.get_credit_timeline(
            user.user_id, regular_load=body.regular_load,
            summer_enabled=body.summer_enabled, summer_load=body.summer_load,
            start_year=body.start_year, start_term=body.start_term,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid credit planning assumptions") from error
    return CreditTimelineResponse.model_validate(result)


@router.post("/degree-paths/credit-comparison", response_model=CreditComparisonResponse)
async def create_credit_comparison(
    body: CreditComparisonRequest, user: AuthenticatedUser, service: StudentServiceDependency,
) -> CreditComparisonResponse:
    try:
        result = await service.compare_credit_timelines(
            user.user_id, start_year=body.start_year, start_term=body.start_term,
            preferred_regular_load=body.preferred_regular_load,
            preferred_summer_enabled=body.preferred_summer_enabled,
            preferred_summer_load=body.preferred_summer_load,
            graduation_pace=body.graduation_pace,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid credit comparison assumptions") from error
    return CreditComparisonResponse.model_validate(result)


def _degree_path_response(result: DegreePathResult) -> DegreePathResponse:
    return DegreePathResponse.model_validate(result, from_attributes=True)


@router.post("/degree-paths/explanation-graph", response_model=ExplainabilityGraph)
async def create_degree_paths_explanation_graph(
    request: DegreePathRequest, user: AuthenticatedUser, service: StudentServiceDependency,
    http_request: Request,
) -> ExplainabilityGraph:
    if http_request.query_params:
        raise HTTPException(status_code=422, detail="Unsupported graph query parameter")
    result = await _request_degree_path(request, user, service, http_request)
    try:
        return build_degree_path_graph(result)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Degree-path evidence cannot be safely graphed") from error
