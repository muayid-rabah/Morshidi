"""Read-only, owner-scoped student and analyst-only aggregate P11 views."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.core.auth import CurrentUser, get_current_user
from app.institutional_intelligence_service import InstitutionalIntelligenceService
from app.p11_intelligence.engine import cohort, compare_cohorts, careers, internships, skills, workload
from app.p11_intelligence.providers import UnavailableP11Provider
from app.rules.models import AttemptOutcome
from app.services.student import StudentService
from app.student.models import PerformanceProvenance, PerformanceVerificationState
from app.student_intelligence.models import StudentIntelligenceContext
from app.student_intelligence.strengths import evaluate_strengths
from app.student_intelligence.difficulty import evaluate_difficulty

student_router = APIRouter(prefix="/api/v1/me", tags=["p11-intelligence"], dependencies=[Depends(get_current_user)])
institutional_router = APIRouter(prefix="/api/v1/institutional", tags=["p11-cohorts"], dependencies=[Depends(get_current_user)])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


def _provider(request: Request):
    return getattr(request.app.state, "p11_provider", UnavailableP11Provider())


@student_router.get("/intelligence")
async def student_intelligence(user: AuthenticatedUser, request: Request, response: Response):
    service: StudentService | None = getattr(request.app.state, "student_service", None)
    if service is None:
        raise HTTPException(503, "Student service unavailable")
    # Never accept owner, university, or plan identity from request parameters.
    profile, university_id = await asyncio.gather(
        service.get_profile(user.user_id), service.resolve_student_university_id(user.user_id),
    )
    provider = _provider(request)
    facts, taxonomy, profiles, criteria, attempts = await asyncio.gather(
        provider.load_facts(university_id, profile.study_plan_id),
        provider.load_taxonomy(university_id, profile.study_plan_id),
        provider.load_profiles(university_id, profile.study_plan_id),
        provider.load_criteria(university_id, profile.study_plan_id),
        service.list_attempts(user.user_id),
    )
    if taxonomy is not None and (taxonomy.university_id, taxonomy.study_plan_id) != (university_id, profile.study_plan_id):
        raise HTTPException(503, "Cross-scope taxonomy provider response")
    trusted = tuple(a for a in attempts if a.performance_verification_state is PerformanceVerificationState.VERIFIED
                    and a.performance_provenance in {PerformanceProvenance.OFFICIAL_VERIFIED,
                                                      PerformanceProvenance.MANUAL_ACADEMIC_REVIEW})
    passed = tuple(a.course_code for a in trusted if a.outcome is AttemptOutcome.PASSED)
    in_progress = tuple(a.course_code for a in trusted if a.outcome is AttemptOutcome.IN_PROGRESS)
    evidence_dates: dict[str, str | None] = {}
    for attempt in trusted:
        if attempt.outcome not in {AttemptOutcome.PASSED, AttemptOutcome.IN_PROGRESS}:
            continue
        date_value = attempt.attempted_on.isoformat() if attempt.attempted_on else None
        previous = evidence_dates.get(attempt.course_code)
        if attempt.course_code not in evidence_dates or (date_value is not None and (previous is None or date_value > previous)):
            evidence_dates[attempt.course_code] = date_value
    graph = skills(taxonomy, passed, in_progress, evidence_dates)
    context = StudentIntelligenceContext(attempts=tuple(attempts))
    strengths = evaluate_strengths(context)
    difficulty = evaluate_difficulty(context)
    def safe_signals(result):
        return {"status": result.status.value, "policy_version": result.policy_version,
                "signals": tuple(asdict(signal) for signal in result.signals),
                "limitations": result.limitations}
    # No private result is cached. No risk signal is exposed to students.
    response.headers["Cache-Control"] = "private, no-store"
    return {"source_type": "SYNTHETIC" if taxonomy is not None else "UNAVAILABLE",
            "validation_status": "NOT_VALIDATED_FOR_REAL_STUDENTS",
            "strength_difficulty": {"strengths": safe_signals(strengths), "difficulty": safe_signals(difficulty)},
            "workload": workload(facts, tuple(dict.fromkeys(passed + in_progress))),
            "skills": graph, "careers": careers(profiles, graph, as_of=date.today()),
            "internships": internships(criteria, graph, as_of=date.today()),
            "risk": "NOT_EXPOSED_TO_STUDENTS", "limitation": "NO_ACADEMIC_DECISION_OVERRIDE"}


@institutional_router.get("/cohorts")
async def institutional_cohort(
    user: AuthenticatedUser, request: Request, response: Response,
    university_id: Annotated[UUID, Query()], study_plan_id: Annotated[UUID, Query()],
    entry_period: Annotated[str, Query(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9-]+$")],
    period: Annotated[str, Query(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9-]+$")],
    comparison_period: Annotated[str | None, Query(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9-]+$")] = None,
    minimum_level: Annotated[int, Query(ge=1, le=8)] = 1,
    maximum_level: Annotated[int, Query(ge=1, le=8)] = 8,
):
    auth: InstitutionalIntelligenceService | None = getattr(request.app.state, "institutional_intelligence_service", None)
    if auth is None:
        raise HTTPException(503, "Institutional service unavailable")
    # Membership authorization precedes provider access, including missing-data paths.
    await auth.authorize_analyst_university(user.user_id, university_id)
    from app.p11_intelligence.models import CohortDefinition
    definition = CohortDefinition(str(university_id), str(study_plan_id), entry_period, period,
                                  minimum_level, maximum_level)
    if minimum_level > maximum_level:
        raise HTTPException(422, "Invalid cohort level range")
    provider = _provider(request)
    snapshot = await provider.load_snapshot(str(university_id), str(study_plan_id))
    if snapshot is not None and (snapshot.university_id, snapshot.study_plan_id) != (str(university_id), str(study_plan_id)):
        raise HTTPException(503, "Cross-scope cohort provider response")
    result = cohort(snapshot, definition, request.app.state.p11_cohort_threshold)
    if comparison_period is not None:
        other = cohort(snapshot, CohortDefinition(str(university_id), str(study_plan_id),
                                                   entry_period, comparison_period,
                                                   minimum_level, maximum_level),
                       request.app.state.p11_cohort_threshold)
        result = {**result, "comparison_period": comparison_period,
                  "comparison": compare_cohorts(result, other)}
    response.headers["Cache-Control"] = "private, no-store"
    return result
