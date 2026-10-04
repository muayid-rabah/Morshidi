"""Authenticated P10 routes: owner scope, analyst gate, suppression, and no-write."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.auth import CurrentUser, get_current_user
from app.main import app
from app.mock_registration.models import (
    AggregationScope, CoverageMetadata, DemandAggregationResult, DemandMetric,
    DemandStatus, TargetPeriod, TargetPeriodClass,
)
from app.mock_registration.registries import DemandMetricId
from app.offerings.fake_provider import FAKE_PERIOD, FAKE_UNIVERSITY_ID, FakeUniversityOfferingProvider, fake_snapshot
from app.offerings.provider import OfferingProviderUnavailable
from app.planner.models import PlannerConstraints, PlannedCourseEntry, SemesterPlanOption, SemesterPlannerResult
from app.rules.models import (
    CanTakeDecision, Decision, PrerequisiteLogicStatus, TargetAttemptState,
)

USER = "10000000-0000-0000-0000-000000000001"
OTHER = "f1000000-0000-0000-0000-000000000011"
PERIOD_ID = "f1000000-0000-0000-0000-000000000012"


class StudentStub:
    def __init__(self, tenant=FAKE_UNIVERSITY_ID):
        self.tenant = tenant
        self.owner_calls = []

    async def resolve_student_university_id(self, owner):
        self.owner_calls.append(owner)
        return self.tenant

    async def evaluate_can_take(self, owner, course):
        self.owner_calls.append(owner)
        return CanTakeDecision("CAN_TAKE_DECISION", Decision.ELIGIBLE, "plan", course,
                               PrerequisiteLogicStatus.VERIFIED,
                               TargetAttemptState(False, False), (), (), (), (), None, None)

    async def get_semester_plans(self, owner, *, max_credit_hours, max_courses, max_options):
        self.owner_calls.append(owner)
        courses = tuple(PlannedCourseEntry(code, None, None, Decimal("3"), "CORE", "required",
                                           index + 1, False, index + 1)
                        for index, code in enumerate(("CS101", "MATH101")))
        option = SemesterPlanOption(1, courses, Decimal("6"), 2, 2, 0, Decimal("6"),
                                    (), 0, (), 0, 3, (2, 0, Decimal("6"), 0, Decimal("6"), 3,
                                                    ("CS101", "MATH101")), ())
        return SemesterPlannerResult(
            "10000000-0000-0000-0000-000000000005", "v1", "ACADEMIC_STRUCTURE_ONLY",
            PlannerConstraints(max_credit_hours, max_courses, max_options), 10, 2, 2, 1,
            (option,), (), (), "academic only", (),
        )


class AnalystStub:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    async def authorize_analyst_university(self, subject, university_id):
        self.calls.append((subject, university_id))
        if not self.allowed or str(university_id) != FAKE_UNIVERSITY_ID:
            from app.institutional_intelligence_service.errors import (
                InstitutionalIntelligenceServiceError,
                InstitutionalIntelligenceServiceErrorCode,
            )
            raise InstitutionalIntelligenceServiceError(
                InstitutionalIntelligenceServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED)
        return university_id


class DemandStub:
    def __init__(self, status=DemandStatus.AVAILABLE):
        self.status = status
        self.calls = 0

    async def demand(self, subject, **kwargs):
        self.calls += 1
        metrics = (() if self.status is DemandStatus.SUPPRESSED else
                   (DemandMetric(DemandMetricId.COURSE_INTENT_OWNER_COUNT, 65, course_code="CS101"),))
        result = DemandAggregationResult(
            "1.0", self.status, AggregationScope(FAKE_UNIVERSITY_ID),
            TargetPeriod(FAKE_UNIVERSITY_ID, FAKE_PERIOD, TargetPeriodClass.SYNTHETIC_SANDBOX_PERIOD, "v1"),
            metrics, (), CoverageMetadata(True, None, None, None), (), (), (), (), (),
        )
        return SimpleNamespace(demand=result)


def _client(student=None, analyst=None, demand=None):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(USER)
    client = TestClient(app)
    client.__enter__()
    app.state.student_service = student or StudentStub()
    app.state.institutional_intelligence_service = analyst or AnalystStub()
    app.state.institutional_demand_service = demand or DemandStub()
    app.state.course_offering_provider = FakeUniversityOfferingProvider()
    return client


def _close(client):
    client.__exit__(None, None, None)
    app.dependency_overrides.clear()


def test_student_offerings_are_owner_derived_and_synthetic():
    student = StudentStub()
    client = _client(student=student)
    try:
        response = client.get("/api/v1/me/offerings/CS101", params={"period_key": FAKE_PERIOD})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["academic_decision"] == "ELIGIBLE"
        assert payload["operational_state"] == "SECTION_OPEN"
        assert payload["provenance"] == "SANDBOX / SYNTHETIC DATA"
        assert len(payload["sections"]) == 2
        assert student.owner_calls == [USER, USER]
    finally:
        _close(client)


def test_student_cross_tenant_gets_no_fake_facts():
    client = _client(student=StudentStub(OTHER))
    try:
        response = client.get("/api/v1/me/offerings/CS101", params={"period_key": FAKE_PERIOD})
        assert response.status_code == 200
        assert response.json()["operational_state"] == "PROVIDER_UNAVAILABLE"
        assert response.json()["sections"] == []
    finally:
        _close(client)


def test_provider_outage_does_not_become_course_not_offered():
    class FailedProvider:
        async def load_snapshot(self, university_id, period_key):
            raise OfferingProviderUnavailable("upstream offline")

    client = _client()
    app.state.course_offering_provider = FailedProvider()
    try:
        response = client.get("/api/v1/me/offerings/CS101", params={"period_key": FAKE_PERIOD})
        assert response.status_code == 200
        assert response.json()["operational_state"] == "PROVIDER_UNAVAILABLE"
        assert response.json()["sections"] == []
        assert "upstream offline" not in response.text
    finally:
        _close(client)


def test_institution_only_sections_do_not_leak_to_student():
    class RestrictedProvider:
        async def load_snapshot(self, university_id, period_key):
            snapshot = fake_snapshot()
            return replace(snapshot, sections=tuple(replace(s, student_visible=False)
                                                      for s in snapshot.sections))

    client = _client()
    app.state.course_offering_provider = RestrictedProvider()
    try:
        response = client.get("/api/v1/me/offerings/CS101", params={"period_key": FAKE_PERIOD})
        assert response.status_code == 200
        assert response.json()["sections"] == []
        assert response.json()["coverage_complete"] is False
        assert response.json()["operational_state"] == "OFFERING_COVERAGE_INCOMPLETE"
        assert "SYN-CS101-A" not in response.text
    finally:
        _close(client)


def test_offering_aware_planner_keeps_academic_rank_and_flags_conflict():
    student = StudentStub()
    client = _client(student=student)
    try:
        response = client.post("/api/v1/me/semester-plans/offerings",
                               params={"period_key": FAKE_PERIOD},
                               json={"max_credit_hours": 15, "max_options": 2})
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "private, no-store"
        payload = response.json()
        assert payload["academic_planner"]["planning_scope"] == "ACADEMIC_STRUCTURE_ONLY"
        assert payload["academic_planner"]["plan_options"][0]["rank"] == 1
        overlay = payload["offering_overlay"][0]
        assert overlay["academic_rank"] == 1
        assert overlay["selected_section_ids"] is None
        assert overlay["possible_pair_conflicts"][0]["reason"] == "TIME_OVERLAP"
        assert student.owner_calls == [USER, USER]
    finally:
        _close(client)


def test_institutional_authorization_precedes_demand_and_provider():
    denied, demand = AnalystStub(False), DemandStub()
    client = _client(analyst=denied, demand=demand)
    try:
        response = client.get("/api/v1/institutional/capacity", params={
            "university_id": FAKE_UNIVERSITY_ID, "target_period_id": PERIOD_ID, "course_code": "CS101"})
        assert response.status_code == 403
        assert demand.calls == 0
        assert len(denied.calls) == 1
    finally:
        _close(client)


def test_institutional_capacity_and_suppression():
    client = _client()
    try:
        params = {"university_id": FAKE_UNIVERSITY_ID,
                  "target_period_id": PERIOD_ID, "course_code": "CS101"}
        response = client.get("/api/v1/institutional/capacity", params=params)
        assert response.status_code == 200, response.text
        assert response.json()["seat_gap"] == 5
    finally:
        _close(client)
    client = _client(demand=DemandStub(DemandStatus.SUPPRESSED))
    try:
        response = client.get("/api/v1/institutional/capacity", params=params)
        assert response.status_code == 200
        assert response.json()["seat_gap"] is None
        assert response.json()["observed_intent_demand"] is None
    finally:
        _close(client)


def test_simulation_does_not_mutate_provider_snapshot():
    provider = FakeUniversityOfferingProvider()
    client = _client()
    app.state.course_offering_provider = provider
    try:
        response = client.post("/api/v1/institutional/capacity/simulation", json={
            "university_id": FAKE_UNIVERSITY_ID, "target_period_id": PERIOD_ID,
            "kind": "ADD_SECTION", "section_id": "MODELLED-CS101-C",
            "course_code": "CS101", "capacity": 30,
        })
        assert response.status_code == 200, response.text
        assert response.json()["section_delta"] == 1
        assert response.json()["modeled_course_seat_delta"] == 30
        assert response.json()["base_observed_gap"] == 5
        assert response.json()["modeled_assumed_gap"] == -25
        assert response.json()["label"].startswith("MODELLED")
        assert "winner" not in response.json()
        assert len(__import__("asyncio").run(provider.load_snapshot(FAKE_UNIVERSITY_ID, FAKE_PERIOD)).sections) == 5
    finally:
        _close(client)


def test_sensitivity_is_authorized_bounded_and_privacy_preserving():
    path = "/api/v1/institutional/capacity/sensitivity"
    payload = {"university_id": FAKE_UNIVERSITY_ID, "target_period_id": PERIOD_ID,
               "course_code": "CS101", "kind": "CAPACITY", "section_id": "SYN-CS101-A",
               "start": 30, "stop": 50, "step": 10}
    client = _client()
    try:
        response = client.post(path, json=payload)
        assert response.status_code == 200, response.text
        points = response.json()["points"]
        assert [p["assumption_value"] for p in points] == [30, 40, 50]
        assert [p["modeled_course_supplied_seats"] for p in points] == [60, 70, 80]
        assert [p["modeled_gap"] for p in points] == [5, -5, -15]
        assert response.headers["Cache-Control"] == "private, no-store"
        assert client.post(path, json={**payload, "stop": 140}).status_code == 422
    finally:
        _close(client)
    client = _client(demand=DemandStub(DemandStatus.SUPPRESSED))
    try:
        suppressed = client.post(path, json=payload)
        assert suppressed.status_code == 200
        assert suppressed.json()["base_observed_demand"] is None
        assert all(p["modeled_demand"] is None and p["modeled_gap"] is None
                   for p in suppressed.json()["points"])
    finally:
        _close(client)
    demand_service = DemandStub()
    client = _client(analyst=AnalystStub(False), demand=demand_service)
    try:
        assert client.post(path, json=payload).status_code == 403
        assert demand_service.calls == 0
    finally:
        _close(client)
