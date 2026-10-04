"""Read-only graph projections behind the exact P7 advisor assignment predicate."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.advisor_persistence.models import AdvisorAccessContext
from app.advisor_service.authorization import AdvisorAuthorizationService
from app.advisor_service.errors import AdvisorAuthorizationError, AdvisorAuthorizationErrorCode
from app.api.routes.student import get_student_service
from app.api.schemas.degree_path import DegreePathRequest
from app.api.schemas.semester_planner import SemesterPlanRequest
from app.core.auth import CurrentUser, get_current_user
from app.explainability_graph import (
    ExplainabilityGraph, GraphMode, build_degree_path_graph, build_eligibility_graph,
    build_recommendation_graph, build_semester_planner_graph,
)
from app.rules.models import CanTakeDecision, Decision
from app.services.student import StudentService


router = APIRouter(prefix="/api/v1/advisor/students", tags=["advisor-explainability-graph"])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]
StudentServiceDependency = Annotated[StudentService, Depends(get_student_service)]


def get_advisor_authorization(request: Request) -> AdvisorAuthorizationService:
    service = getattr(request.app.state, "advisor_authorization_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Advisor authorization unavailable")
    return service


AdvisorAuthorizationDependency = Annotated[AdvisorAuthorizationService, Depends(get_advisor_authorization)]


async def authorized_student(
    student_user_id: UUID, user: AuthenticatedUser,
    authorization: AdvisorAuthorizationDependency,
) -> AdvisorAccessContext:
    try:
        return await authorization.authorize_advisor_for_student(user.user_id, student_user_id)
    except AdvisorAuthorizationError as error:
        if error.code is AdvisorAuthorizationErrorCode.PERSISTENCE_UNAVAILABLE:
            raise HTTPException(status_code=503, detail="Advisor authorization unavailable") from error
        raise HTTPException(status_code=403, detail="Advisor graph access denied") from error


AuthorizedStudent = Annotated[AdvisorAccessContext, Depends(authorized_student)]


@router.get("/{student_user_id}/eligibility/{course_code}/explanation-graph",
            response_model=ExplainabilityGraph)
async def advisor_eligibility_graph(
    course_code: str, context: AuthorizedStudent, service: StudentServiceDependency, request: Request,
    mode: GraphMode = GraphMode.WHY, target: Decision | None = None,
) -> ExplainabilityGraph:
    if set(request.query_params) - {"mode", "target"}:
        raise HTTPException(status_code=422, detail="Unsupported graph query parameter")
    if (mode is GraphMode.WHY and target is not None) or (mode is GraphMode.WHY_NOT and target not in {None, Decision.ELIGIBLE}):
        raise HTTPException(status_code=422, detail="Invalid graph query mode")
    result = await service.evaluate_can_take(str(context.student_user_id), course_code)
    if not isinstance(result, CanTakeDecision):
        raise HTTPException(status_code=404, detail="Scoped academic resource unavailable")
    try:
        return build_eligibility_graph(result, mode=mode,
                                       target_decision=Decision.ELIGIBLE if mode is GraphMode.WHY_NOT else None)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Eligibility evidence cannot be safely graphed") from error


@router.get("/{student_user_id}/course-recommendations/explanation-graph",
            response_model=ExplainabilityGraph)
async def advisor_recommendation_graph(
    context: AuthorizedStudent, service: StudentServiceDependency, request: Request,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    mode: GraphMode = GraphMode.WHY, course_code: str | None = None,
) -> ExplainabilityGraph:
    if set(request.query_params) - {"limit", "mode", "course_code"}:
        raise HTTPException(status_code=422, detail="Unsupported graph query parameter")
    if (mode is GraphMode.WHY and course_code is not None) or (mode is GraphMode.WHY_NOT and course_code is None):
        raise HTTPException(status_code=422, detail="Invalid graph query mode")
    result = await service.get_course_recommendations(str(context.student_user_id), limit=limit)
    try:
        return build_recommendation_graph(result, mode=mode, course_code=course_code)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Recommendation evidence cannot be safely graphed") from error


@router.post("/{student_user_id}/semester-plans/explanation-graph", response_model=ExplainabilityGraph)
async def advisor_semester_graph(
    body: SemesterPlanRequest, context: AuthorizedStudent, service: StudentServiceDependency,
    request: Request,
) -> ExplainabilityGraph:
    if request.query_params:
        raise HTTPException(status_code=422, detail="Unsupported graph query parameter")
    result = await service.get_semester_plans(
        str(context.student_user_id), max_credit_hours=body.max_credit_hours,
        max_courses=body.max_courses, max_options=body.max_options,
    )
    try:
        return build_semester_planner_graph(result)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Planner evidence cannot be safely graphed") from error


@router.post("/{student_user_id}/degree-paths/explanation-graph", response_model=ExplainabilityGraph)
async def advisor_degree_path_graph(
    body: DegreePathRequest, context: AuthorizedStudent, service: StudentServiceDependency,
    request: Request,
) -> ExplainabilityGraph:
    if request.query_params:
        raise HTTPException(status_code=422, detail="Unsupported graph query parameter")
    result = await service.get_degree_paths(
        str(context.student_user_id),
        max_credit_hours_per_semester=body.max_credit_hours_per_semester,
        max_courses_per_semester=body.max_courses_per_semester,
        max_semesters_ahead=body.max_semesters_ahead, max_paths=body.max_paths,
    )
    try:
        return build_degree_path_graph(result)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="Degree-path evidence cannot be safely graphed") from error
