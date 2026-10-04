"""Authenticated student-facing institutional policy routes (WC-038).

AI EXPLAINS — DETERMINISTIC RULES DECIDE.
Read-only surface for students to access verified university regulations and institutional policies.
Enforces:
- Strict university-level tenant isolation (derived from authenticated student profile).
- Reading only VERIFIED policy versions.
- Preserving exact citations, version tags, and passage locators.
- Zero client-controlled tenant bypass.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi import Query

from app.api.schemas.policy import (
    StudentPolicyAnswerRequest,
    StudentPolicyAnswerResponse,
    StudentPolicyDocumentDetail,
    StudentPolicyDocumentSummary,
    StudentPolicySearchResult,
)
from app.core.auth import CurrentUser, get_current_user
from app.institutional_policy.errors import PolicyRetrievalError
from app.institutional_policy.embeddings import PolicyEmbeddingError
from app.institutional_policy.service import StudentPolicyService
from app.institutional_policy.answering import PolicyAnswerService
from app.services.student import StudentConfigurationError, StudentService
from app.student.errors import StudentProfileNotFound

router = APIRouter(prefix="/api/v1/me/policies", tags=["policies"], dependencies=[Depends(get_current_user)])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


def get_policy_service(request: Request) -> StudentPolicyService:
    service = getattr(request.app.state, "policy_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Policy service is not configured",
        )
    return service


def get_policy_answer_service(request: Request) -> PolicyAnswerService:
    service = getattr(request.app.state, "policy_answer_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Policy answer service is not configured",
        )
    return service


def get_student_service(request: Request) -> StudentService:
    service = getattr(request.app.state, "student_service", None)
    if service is None:
        raise StudentConfigurationError("Student service is not configured")
    return service


PolicyServiceDependency = Annotated[StudentPolicyService, Depends(get_policy_service)]
StudentServiceDependency = Annotated[StudentService, Depends(get_student_service)]
PolicyAnswerServiceDependency = Annotated[PolicyAnswerService, Depends(get_policy_answer_service)]


@router.post("/answer", response_model=StudentPolicyAnswerResponse)
async def answer_student_policy_question(
    request: StudentPolicyAnswerRequest,
    user: AuthenticatedUser,
    policy_answer_service: PolicyAnswerServiceDependency,
    student_service: StudentServiceDependency,
) -> StudentPolicyAnswerResponse:
    """Answer only from the authenticated student's verified university evidence."""
    try:
        university_id = await student_service.resolve_student_university_id(user.user_id)
    except StudentProfileNotFound as exc:
        raise HTTPException(status_code=404, detail="Student profile not found") from exc
    result = await policy_answer_service.answer(str(university_id), request.question, request.limit)
    return StudentPolicyAnswerResponse.model_validate(asdict(result))


@router.get("", response_model=list[StudentPolicyDocumentSummary])
async def list_student_policies(
    user: AuthenticatedUser,
    policy_service: PolicyServiceDependency,
    student_service: StudentServiceDependency,
) -> list[StudentPolicyDocumentSummary]:
    """List verified institutional policy documents for the student's university."""
    try:
        university_id = await student_service.resolve_student_university_id(user.user_id)
    except StudentProfileNotFound:
        return []

    docs = await policy_service.list_policies_for_student(university_id)
    return [StudentPolicyDocumentSummary.model_validate(d) for d in docs]


@router.get("/search", response_model=list[StudentPolicySearchResult])
async def search_student_policies(
    q: str = Query(min_length=1, max_length=240),
    limit: int = Query(default=10, ge=1, le=20),
    category: str | None = None,
    document_id: str | None = None,
    mode: Literal["lexical", "semantic", "hybrid"] = "lexical",
    user: AuthenticatedUser = None,
    policy_service: PolicyServiceDependency = None,
    student_service: StudentServiceDependency = None,
) -> list[StudentPolicySearchResult]:
    query = " ".join(q.split())
    if not query:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Query cannot be blank")
    try:
        university_id = await student_service.resolve_student_university_id(user.user_id)
    except StudentProfileNotFound:
        return []
    try:
        rows = await policy_service.search_policies_for_student(university_id, query, limit, category, document_id, mode)
    except PolicyEmbeddingError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Semantic policy search is temporarily unavailable") from exc
    return [StudentPolicySearchResult.model_validate(row) for row in rows]


@router.get("/{document_id}", response_model=StudentPolicyDocumentDetail)
async def get_student_policy_detail(
    document_id: str,
    user: AuthenticatedUser,
    policy_service: PolicyServiceDependency,
    student_service: StudentServiceDependency,
) -> StudentPolicyDocumentDetail:
    """Get full detail of a verified institutional policy document with passages."""
    try:
        university_id = await student_service.resolve_student_university_id(user.user_id)
    except StudentProfileNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile not found",
        )

    try:
        detail = await policy_service.get_policy_detail_for_student(university_id, document_id)
    except PolicyRetrievalError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.detail,
        ) from exc

    return StudentPolicyDocumentDetail.model_validate(detail)
