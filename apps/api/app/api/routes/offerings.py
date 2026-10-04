"""Authenticated, tenant-scoped P10 operational views and no-write scenarios."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
from itertools import combinations
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth import CurrentUser, get_current_user
from app.api.schemas.semester_planner import SemesterPlanRequest, SemesterPlannerResponse
from app.institutional_intelligence_service import InstitutionalIntelligenceService
from app.mock_registration_service.institutional_service import InstitutionalDemandService
from app.offerings.logic import capacity_state, conflict, operational_state, reconcile, select_nonconflicting_sections
from app.offerings.models import Modality
from app.offerings.provider import (
    CourseOfferingProvider, OfferingProviderUnavailable, UnavailableOfferingProvider,
)
from app.offerings.simulation import (
    Assumption, CurriculumAssumptionKind, SensitivityKind, sensitivity, simulate,
)
from app.rules.models import CanTakeDecision, Decision
from app.services.student import StudentService

student_router = APIRouter(prefix="/api/v1/me", tags=["offerings"], dependencies=[Depends(get_current_user)])
institutional_router = APIRouter(prefix="/api/v1/institutional", tags=["capacity"],
                                  dependencies=[Depends(get_current_user)])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


def _provider(request: Request) -> CourseOfferingProvider:
    return getattr(request.app.state, "course_offering_provider", UnavailableOfferingProvider())


async def _snapshot(request: Request, university_id: str, period_key: str):
    try:
        snapshot = await _provider(request).load_snapshot(university_id, period_key)
    except OfferingProviderUnavailable:
        return None
    if snapshot is not None and (snapshot.university_id != university_id or snapshot.period_key != period_key):
        raise HTTPException(503, "Offering provider returned a cross-scope snapshot")
    return snapshot


def _student(request: Request) -> StudentService:
    service = getattr(request.app.state, "student_service", None)
    if service is None:
        raise HTTPException(503, "Student service unavailable")
    return service


def _institutional(request: Request) -> tuple[InstitutionalIntelligenceService, InstitutionalDemandService]:
    auth = getattr(request.app.state, "institutional_intelligence_service", None)
    demand = getattr(request.app.state, "institutional_demand_service", None)
    if auth is None or demand is None:
        raise HTTPException(503, "Institutional service unavailable")
    return auth, demand


def _section_view(section, stale: bool) -> dict:
    view = asdict(section)
    view["capacity_state"] = capacity_state(section, stale=stale).value
    return view


def _student_snapshot(snapshot):
    if snapshot is None:
        return None
    visible = tuple(section for section in snapshot.sections if section.student_visible)
    return replace(snapshot, sections=visible,
                   complete=snapshot.complete and len(visible) == len(snapshot.sections))


def _possible_conflicts(snapshot, codes: tuple[str, ...]) -> tuple[dict, ...]:
    if snapshot is None or len(snapshot.sections) > 200:
        return ()
    sections = tuple(s for s in snapshot.sections if s.course_code in codes and s.status == "OPEN")
    found = []
    for first, second in combinations(sections, 2):
        if first.course_code == second.course_code:
            continue
        found.extend(asdict(item) for item in conflict(first, second))
        if len(found) >= 20:
            break
    return tuple(found[:20])


@student_router.get("/offerings/{course_code}")
async def student_offerings(course_code: str, period_key: Annotated[str, Query(min_length=1, max_length=80)],
                            user: AuthenticatedUser, request: Request, response: Response):
    if not 1 <= len(course_code) <= 50:
        raise HTTPException(422, "Invalid course code")
    service = _student(request)
    # Both academic profile and tenant are resolved from the authenticated owner.
    university_id = await service.resolve_student_university_id(user.user_id)
    decision = await service.evaluate_can_take(user.user_id, course_code)
    if not isinstance(decision, CanTakeDecision):
        raise HTTPException(409, "Academic eligibility cannot be evaluated for this course")
    snapshot = _student_snapshot(await _snapshot(request, university_id, period_key))
    now = datetime.now(timezone.utc)
    eligible = (True if decision.decision is Decision.ELIGIBLE else
                False if decision.decision is Decision.NOT_ELIGIBLE else None)
    sections = tuple(s for s in snapshot.sections if s.course_code == course_code) if snapshot else ()
    response.headers["Cache-Control"] = "private, no-store"
    return {
        "course_code": course_code, "academic_decision": decision.decision.value,
        "operational_state": operational_state(course_code, eligible, snapshot, now).value,
        "source_type": snapshot.source_type.value if snapshot else None,
        "source_version": snapshot.source_version if snapshot else None,
        "fresh_until": snapshot.fresh_until if snapshot else None,
        "coverage_complete": snapshot.complete if snapshot else None,
        "provenance": snapshot.provenance if snapshot else None,
        "sections": tuple(_section_view(s, now > snapshot.fresh_until) for s in sections),
    }


@student_router.post("/semester-plans/offerings")
async def student_offering_aware_plans(body: SemesterPlanRequest,
                                       period_key: Annotated[str, Query(min_length=1, max_length=80)],
                                       user: AuthenticatedUser, request: Request, response: Response):
    """Explicit operational overlay; base academic ranks and decisions are untouched."""
    service = _student(request)
    university_id = await service.resolve_student_university_id(user.user_id)
    planner = await service.get_semester_plans(
        user.user_id, max_credit_hours=body.max_credit_hours,
        max_courses=body.max_courses, max_options=body.max_options,
    )
    snapshot = _student_snapshot(await _snapshot(request, university_id, period_key))
    now = datetime.now(timezone.utc)
    overlay = tuple({
        "academic_rank": option.rank,
        "course_codes": tuple(course.course_code for course in option.courses),
        "selected_section_ids": selection,
        "operational_status": ("CONFIRMED_KNOWN_OPEN_NONCONFLICTING_SET" if selection is not None
                               else "NO_CONFIRMED_SET_OR_INCOMPLETE_DATA"),
        "possible_pair_conflicts": _possible_conflicts(
            snapshot, tuple(course.course_code for course in option.courses)),
    } for option in planner.plan_options
      for selection in (select_nonconflicting_sections(
          snapshot, tuple(course.course_code for course in option.courses), now),))
    response.headers["Cache-Control"] = "private, no-store"
    return {
        "academic_planner": SemesterPlannerResponse.model_validate(planner, from_attributes=True),
        "offering_overlay": overlay,
        "source_type": snapshot.source_type.value if snapshot else None,
        "source_version": snapshot.source_version if snapshot else None,
        "provenance": snapshot.provenance if snapshot else None,
        "fresh_until": snapshot.fresh_until if snapshot else None,
        "planning_scope": "ACADEMIC_RESULT_PLUS_EXPLICIT_OPERATIONAL_OVERLAY",
    }


@institutional_router.get("/capacity")
async def institutional_capacity(user: AuthenticatedUser, request: Request, response: Response,
                                 university_id: Annotated[UUID, Query()],
                                 target_period_id: Annotated[UUID, Query()],
                                 course_code: Annotated[str, Query(min_length=1, max_length=50)]):
    auth, demand_service = _institutional(request)
    await auth.authorize_analyst_university(user.user_id, university_id)
    result = await demand_service.demand(user.user_id, university_id=university_id,
                                         target_period_id=target_period_id)
    snapshot = await _snapshot(request, str(university_id), result.demand.target_period.period_key)
    response.headers["Cache-Control"] = "private, no-store"
    return asdict(reconcile(result.demand, snapshot, course_code, datetime.now(timezone.utc)))


class ScenarioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    university_id: UUID
    target_period_id: UUID
    kind: str = Field(max_length=50)
    section_id: str = Field(max_length=80)
    course_code: str = Field(min_length=1, max_length=50)
    capacity: int | None = None
    demand_delta: int = 0
    day: int | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    modality: Modality | None = None
    campus: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=80)


@institutional_router.post("/capacity/simulation")
async def institutional_simulation(input: ScenarioInput, user: AuthenticatedUser,
                                   request: Request, response: Response):
    auth, demand_service = _institutional(request)
    await auth.authorize_analyst_university(user.user_id, input.university_id)
    result = await demand_service.demand(user.user_id, university_id=input.university_id,
                                         target_period_id=input.target_period_id)
    snapshot = await _snapshot(request, str(input.university_id), result.demand.target_period.period_key)
    if snapshot is None:
        raise HTTPException(409, "Offering snapshot unavailable; simulation not possible")
    if input.kind not in ("ADD_SECTION", "CHANGE_DEMAND", *(kind.value for kind in CurriculumAssumptionKind)) and not any(
        s.section_id == input.section_id and s.course_code == input.course_code for s in snapshot.sections
    ):
        raise HTTPException(422, "Section does not belong to the requested course")
    try:
        from datetime import time
        assumption = Assumption(input.kind, input.section_id, input.course_code,
                                input.capacity, input.demand_delta, input.day,
                                time.fromisoformat(input.starts_at) if input.starts_at else None,
                                time.fromisoformat(input.ends_at) if input.ends_at else None,
                                input.modality, input.campus, input.location)
        comparison = simulate(snapshot, (assumption,))
    except ValueError as error:
        raise HTTPException(422, "Invalid bounded scenario assumption") from error
    base = reconcile(result.demand, snapshot, input.course_code, datetime.now(timezone.utc))
    modeled = reconcile(result.demand, comparison.modeled_snapshot, input.course_code, datetime.now(timezone.utc))
    modeled_demand = (modeled.observed_intent_demand + comparison.modeled_demand_delta
                      if modeled.observed_intent_demand is not None else None)
    if modeled_demand is not None and modeled_demand < 0:
        raise HTTPException(422, "Modeled demand cannot be negative")
    modeled_gap = (modeled_demand - modeled.supplied_section_capacity
                   if modeled_demand is not None and modeled.supplied_section_capacity is not None else None)
    response.headers["Cache-Control"] = "private, no-store"
    return {
        "base_fingerprint": comparison.base_fingerprint,
        "scenario_fingerprint": comparison.scenario_fingerprint,
        "assumptions": (asdict(assumption),),
        "base_supplied_seats": comparison.base_supplied_seats,
        "modeled_supplied_seats": comparison.modeled_supplied_seats,
        "seat_delta": comparison.seat_delta,
        "modeled_demand_delta": comparison.modeled_demand_delta,
        "section_delta": comparison.section_delta,
        "base_course_supplied_seats": base.supplied_section_capacity,
        "modeled_course_supplied_seats": modeled.supplied_section_capacity,
        "modeled_course_seat_delta": (
            modeled.supplied_section_capacity - base.supplied_section_capacity
            if modeled.supplied_section_capacity is not None and base.supplied_section_capacity is not None
            else None
        ),
        "base_observed_gap": base.seat_gap,
        "modeled_assumed_gap": modeled_gap,
        "label": comparison.label,
        "source_type": snapshot.source_type.value,
        "source_version": snapshot.source_version,
        "provenance": snapshot.provenance,
        "freshness_status": "STALE" if datetime.now(timezone.utc) > snapshot.fresh_until else "FRESH",
        "fresh_until": snapshot.fresh_until,
        "coverage_complete": snapshot.complete,
        "demand_status": result.demand.status.value,
        "observed_only": result.demand.coverage.observed_intents_only,
        # No modeled snapshot is persisted and no individual demand records are returned.
    }


class SensitivityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    university_id: UUID
    target_period_id: UUID
    kind: SensitivityKind
    course_code: str = Field(min_length=1, max_length=50)
    section_id: str = Field(default="", max_length=80)
    start: int
    stop: int
    step: int
    section_capacity: int | None = None


@institutional_router.post("/capacity/sensitivity")
async def institutional_sensitivity(input: SensitivityInput, user: AuthenticatedUser,
                                    request: Request, response: Response):
    auth, demand_service = _institutional(request)
    await auth.authorize_analyst_university(user.user_id, input.university_id)
    result = await demand_service.demand(user.user_id, university_id=input.university_id,
                                         target_period_id=input.target_period_id)
    snapshot = await _snapshot(request, str(input.university_id), result.demand.target_period.period_key)
    if snapshot is None:
        raise HTTPException(409, "Offering snapshot unavailable; sensitivity not possible")
    try:
        points = sensitivity(snapshot, kind=input.kind, course_code=input.course_code,
                             section_id=input.section_id, start=input.start, stop=input.stop,
                             step=input.step, section_capacity=input.section_capacity)
    except ValueError as error:
        raise HTTPException(422, "Invalid bounded sensitivity range") from error
    now = datetime.now(timezone.utc)
    base = reconcile(result.demand, snapshot, input.course_code, now)
    views = []
    for point in points:
        modeled = reconcile(result.demand, point.comparison.modeled_snapshot, input.course_code, now)
        demand = (modeled.observed_intent_demand + point.comparison.modeled_demand_delta
                  if modeled.observed_intent_demand is not None else None)
        if demand is not None and demand < 0:
            raise HTTPException(422, "Modeled demand cannot be negative")
        views.append({
            "assumption_value": point.value,
            "scenario_fingerprint": point.comparison.scenario_fingerprint,
            "modeled_course_supplied_seats": modeled.supplied_section_capacity,
            "modeled_demand": demand,
            "modeled_gap": (demand - modeled.supplied_section_capacity
                            if demand is not None and modeled.supplied_section_capacity is not None else None),
            "supply_status": modeled.status,
        })
    response.headers["Cache-Control"] = "private, no-store"
    return {
        "base_fingerprint": points[0].comparison.base_fingerprint,
        "kind": input.kind.value,
        "base_course_supplied_seats": base.supplied_section_capacity,
        "base_observed_demand": base.observed_intent_demand,
        "points": views,
        "source_type": snapshot.source_type.value,
        "provenance": snapshot.provenance,
        "freshness_status": "STALE" if now > snapshot.fresh_until else "FRESH",
        "demand_status": result.demand.status.value,
        "label": "MODELLED SENSITIVITY ONLY — NO OPERATIONAL WRITE OR RECOMMENDATION",
    }
