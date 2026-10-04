"""Owner-scoped, read-only modeled P12 transition endpoints."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import CurrentUser, get_current_user
from app.plan_transition.engine import (TransitionIntegrityError, evaluate_transition,
                                        project_major_transfer)
from app.plan_transition.models import CompletedCourse, CreditStatus, PlanVersion
from app.plan_transition.provider import StudentModelingProvider
from app.rules.models import AttemptOutcome
from app.services.student import StudentService
from app.student.models import PerformanceProvenance, PerformanceVerificationState

router = APIRouter(prefix="/api/v1/me/plan-transitions", tags=["plan-transitions"],
                   dependencies=[Depends(get_current_user)])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


class ModeledTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_plan_key: tuple[str, str, str, str, str] = Field(description="Server-allowlisted plan/version identity only")


def _provider(request: Request) -> StudentModelingProvider:
    provider = getattr(request.app.state, "p12_modeling_provider", None)
    if provider is None:
        raise HTTPException(503, "TARGET_PLAN_UNAVAILABLE")
    return provider


def _service(request: Request) -> StudentService:
    service = getattr(request.app.state, "student_service", None)
    if service is None:
        raise HTTPException(503, "TARGET_PLAN_UNAVAILABLE")
    return service


async def _source(user: CurrentUser, request: Request) -> tuple[PlanVersion, StudentService, StudentModelingProvider]:
    service = _service(request)
    provider = _provider(request)
    profile, institution_id = await asyncio.gather(
        service.get_profile(user.user_id), service.resolve_student_university_id(user.user_id))
    source = await provider.source_for(institution_id, profile.study_plan_id)
    if source is None:
        raise HTTPException(503, "TARGET_PLAN_UNAVAILABLE")
    if source.identity.institution_id != institution_id:
        raise HTTPException(409, "VERSION_MISMATCH")
    return source, service, provider


def _summary(plan: PlanVersion) -> dict:
    identity = plan.identity
    return {"plan_key": identity.key, "institution_id": identity.institution_id,
            "program_id": identity.program_id, "major_id": identity.major_id,
            "plan_id": identity.plan_id, "version_id": identity.version_id,
            "effective_from": identity.effective_from.isoformat(),
            "effective_to": identity.effective_to.isoformat() if identity.effective_to else None,
            "source_version": identity.source_version,
            "content_fingerprint": plan.content_fingerprint, "source_fingerprint": plan.source_fingerprint,
            "source": plan.source, "synthetic": plan.synthetic,
            "display_course_codes": {course.identity.course_id: course.identity.code
                                     for course in plan.courses},
            "label": "MODELED_UNOFFICIAL"}


@router.get("")
async def list_modeled_targets(user: AuthenticatedUser, request: Request, response: Response):
    source, _, provider = await _source(user, request)
    targets = await provider.allowed_targets(source.identity)
    if any(t.identity.institution_id != source.identity.institution_id or
           t.identity.key == source.identity.key for t in targets):
        raise HTTPException(409, "VERSION_MISMATCH")
    response.headers["Cache-Control"] = "private, no-store"
    return {"status": "AVAILABLE" if targets else "TARGET_PLAN_UNAVAILABLE",
            "current": _summary(source), "targets": tuple(_summary(t) for t in targets),
            "label": "MODELED_UNOFFICIAL", "write_performed": False}


@router.post("/evaluate")
async def evaluate_modeled_transition(
    body: ModeledTransitionRequest, user: AuthenticatedUser,
    request: Request, response: Response,
):
    source, service, provider = await _source(user, request)
    targets = await provider.allowed_targets(source.identity)
    target = next((t for t in targets if t.identity.key == body.target_plan_key), None)
    if target is None:
        raise HTTPException(404, "TARGET_PLAN_UNAVAILABLE")
    if target.identity.institution_id != source.identity.institution_id:
        raise HTTPException(409, "VERSION_MISMATCH")
    try:
        rules = await provider.rules_for(source.identity, target.identity)
    except NotImplementedError:
        raise HTTPException(503, "RULES_UNAVAILABLE") from None
    records = await service.list_attempts(user.user_id)
    by_code: dict[str, list] = {}
    for course in source.courses:
        by_code.setdefault(course.identity.code, []).append(course)
    completed: list[CompletedCourse] = []
    unmapped: list[str] = []
    for record in records:
        if record.outcome is not AttemptOutcome.PASSED:
            continue
        if record.performance_verification_state is not PerformanceVerificationState.VERIFIED or \
           record.performance_provenance not in {PerformanceProvenance.OFFICIAL_VERIFIED,
                                                  PerformanceProvenance.MANUAL_ACADEMIC_REVIEW}:
            unmapped.append(record.course_code)
            continue
        candidates = by_code.get(record.course_code, [])
        credits = record.attempt_credit_hours
        if len(candidates) != 1 or credits is None or not isinstance(credits, Decimal) or \
           not credits.is_finite() or credits < 0:
            unmapped.append(record.course_code)
            continue
        completed.append(CompletedCourse(candidates[0].identity, credits, source.identity.key))
    evaluated_on = date.today()
    try:
        if source.identity.major_id == target.identity.major_id:
            result = evaluate_transition(source, target, tuple(completed), rules, (), evaluated_on)
            kind = "PLAN_VERSION_TRANSITION"
        else:
            result = project_major_transfer(source, target, tuple(completed), rules, (), evaluated_on)
            kind = "CROSS_MAJOR_PROJECTION"
    except TransitionIntegrityError:
        raise HTTPException(409, "VERSION_MISMATCH") from None
    statuses = {line.status for line in result.lines}
    if CreditStatus.REVIEW_REQUIRED in statuses:
        status = "EQUIVALENCY_CONFLICT" if any(
            line.explanation == "Ambiguous/contested mapping" and line.rule_evidence
            for line in result.lines if line.status is CreditStatus.REVIEW_REQUIRED
        ) else "REVIEW_REQUIRED"
    elif CreditStatus.UNRESOLVED in statuses or unmapped:
        status = "EQUIVALENCY_UNRESOLVED"
    else:
        status = "MODELED"
    response.headers["Cache-Control"] = "private, no-store"
    return {"status": status, "kind": kind, "label": "MODELED_UNOFFICIAL",
            "evaluated_on": evaluated_on.isoformat(),
            "current": _summary(source), "target": _summary(target),
            "projection": jsonable_encoder(asdict(result), custom_encoder={Decimal: str}),
            "unmapped_attempt_codes": tuple(sorted(set(unmapped))),
            "write_performed": False, "limitation": "NOT_OFFICIAL_REGISTRAR_APPROVAL"}
