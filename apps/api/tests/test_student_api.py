"""Authenticated student self-service API tests with dependency overrides."""

from collections.abc import Iterator
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.routes.student import get_student_service
from app.core.auth import CurrentUser, get_current_user
from app.main import app
from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    AttemptOutcome, CanTakeCatalog, CanTakeRequest, CourseCatalogStatus,
    CourseIdentity, DependencyGroup, DependencyType, PlanCourseRule,
    PrerequisiteLogicStatus,
)
from app.student.errors import (
    StudentAttemptNotFound, StudentCourseNotFound, StudentCourseUniversityMismatch,
    StudentProfileAlreadyExists, StudentProfileNotFound,
)
from app.student.models import StudentAcademicState, StudentCourseAttemptRecord
from app.progress.models import AcademicProgress
from app.roadmap.engine import AcademicRoadmap
from app.roadmap.report import build_report_snapshot

OWNER = "11111111-1111-1111-1111-111111111111"
PLAN = "10000000-0000-0000-0000-000000000005"
PROFILE = "22222222-2222-2222-2222-222222222222"
ATTEMPT = "33333333-3333-3333-3333-333333333333"
NOW = datetime(2026, 9, 17, tzinfo=timezone.utc)


def profile(attempts=()) -> StudentAcademicState:
    return StudentAcademicState(PROFILE, OWNER, PLAN, Decimal("3.25"), Decimal("4"), Decimal("15"), tuple(attempts), NOW, NOW)


def attempt(status=AttemptOutcome.PASSED, code="0300103") -> StudentCourseAttemptRecord:
    return StudentCourseAttemptRecord(ATTEMPT, PROFILE, code, status, None, None, None, "A", "manual_entry", NOW, NOW)


class FakeStudentService:
    def __init__(self) -> None:
        self.state = profile()
        self.records = [attempt()]
        self.missing = False
        self.duplicate = False
        self.created_owners: list[str] = []

    async def get_profile(self, owner):
        if self.missing: raise StudentProfileNotFound("missing")
        return self.state
    async def create_profile(self, owner, **values):
        if self.duplicate: raise StudentProfileAlreadyExists("duplicate")
        self.created_owners.append(owner); return self.state
    async def update_profile(self, owner, changes): return self.state
    async def delete_profile(self, owner):
        if self.missing: raise StudentProfileNotFound("missing")
    async def list_attempts(self, owner): return tuple(self.records)
    async def create_attempt(self, owner, course_code, status, **values):
        if course_code == "unknown": raise StudentCourseNotFound("missing")
        if course_code == "foreign": raise StudentCourseUniversityMismatch("foreign")
        row = attempt(status, course_code); self.records.append(row); return row
    async def update_attempt(self, owner, attempt_id, changes):
        if str(attempt_id) != ATTEMPT: raise StudentAttemptNotFound("missing")
        return attempt(changes.get("status", AttemptOutcome.PASSED))
    async def delete_attempt(self, owner, attempt_id):
        if str(attempt_id) != ATTEMPT: raise StudentAttemptNotFound("missing")
    async def evaluate_can_take(self, owner, target):
        if self.missing: raise StudentProfileNotFound("missing")
        if target == "unknown":
            from app.catalog.errors import TargetCourseNotFound
            raise TargetCourseNotFound("missing")
        if target == "0300103":
            from app.catalog.errors import TargetCourseNotInStudyPlan
            raise TargetCourseNotInStudyPlan("not member")
        status = {"1505311": PrerequisiteLogicStatus.UNRESOLVED,
            "1505320": PrerequisiteLogicStatus.SOURCE_CONFLICT,
            "0200115": PrerequisiteLogicStatus.NOT_APPLICABLE}.get(target, PrerequisiteLogicStatus.VERIFIED)
        groups = () if status is not PrerequisiteLogicStatus.VERIFIED else (DependencyGroup(1, DependencyType.PREREQUISITE, ("1501110",)),)
        catalog = CanTakeCatalog(PLAN, (PlanCourseRule(target, status, groups),),
            tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in {target, "1501110"}))
        return evaluate_can_take(catalog, CanTakeRequest(PLAN, target, self.state.attempts))
    async def get_academic_progress(self, owner):
        if self.missing: raise StudentProfileNotFound("missing")
        self.progress_owner = owner
        return AcademicProgress(
            study_plan_id=PLAN,
            plan_total_required_credits=Decimal("132"),
            completed_plan_credits=Decimal("3"),
            in_progress_plan_credits=Decimal("0"),
            remaining_plan_credits=Decimal("129"),
            satisfied_requirement_group_count=0,
            total_requirement_group_count=6,
            all_modeled_plan_requirements_satisfied=False,
            requirement_groups=(),
            courses=(),
            reported_cumulative_gpa=self.state.reported_cumulative_gpa,
            reported_gpa_scale=self.state.reported_gpa_scale,
            reported_earned_credit_hours=self.state.reported_earned_credit_hours,
        )

    async def get_academic_roadmap(self, owner):
        if self.missing: raise StudentProfileNotFound("missing")
        self.roadmap_owner = owner
        return AcademicRoadmap(PLAN, "synthetic-1", 2026, None, NOW,
            Decimal("132"), Decimal("3"), Decimal("0"), Decimal("129"), (), (), ("Modeled only",),
            snapshot_fingerprint="synthetic-snapshot")

    async def get_academic_report(self, owner):
        return build_report_snapshot(await self.get_academic_roadmap(owner))

    async def get_modeled_roadmap(self, owner, **kwargs):
        self.modeled_owner = owner
        self.modeled_kwargs = kwargs
        return await self.get_academic_roadmap(owner)


@pytest.fixture
def api() -> Iterator[tuple[TestClient, FakeStudentService]]:
    service = FakeStudentService()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    app.dependency_overrides[get_student_service] = lambda: service
    with TestClient(app) as client: yield client, service
    app.dependency_overrides.clear()


def test_all_student_routes_require_auth() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        for method, path in [
            ("GET", "/api/v1/me/academic-profile"),
            ("GET", "/api/v1/me/academic-progress"),
            ("GET", "/api/v1/me/academic-roadmap"),
            ("GET", "/api/v1/me/academic-report"),
            ("POST", "/api/v1/me/academic-roadmap/modeled-path"),
            ("GET", "/api/v1/me/course-recommendations"),
            ("GET", "/api/v1/me/academic-profile/attempts"),
            ("GET", "/api/v1/me/eligibility/1501112"),
        ]:
            assert client.request(method, path).status_code == 401


def test_progress_uses_only_authenticated_owner_and_reported_facts_remain_distinct(api) -> None:
    client, service = api
    response = client.get("/api/v1/me/academic-progress")
    assert response.status_code == 200
    assert service.progress_owner == OWNER
    body = response.json()
    assert body["study_plan_id"] == PLAN
    assert body["completed_plan_credits"] == "3"
    assert body["reported_earned_credit_hours"] == "15"
    service.missing = True
    assert client.get("/api/v1/me/academic-progress").status_code == 404


def test_roadmap_uses_authenticated_owner_and_has_no_client_owner_selector(api) -> None:
    client, service = api
    response = client.get("/api/v1/me/academic-roadmap")
    assert response.status_code == 200
    assert service.roadmap_owner == OWNER
    assert response.json()["plan_number"] == "synthetic-1"
    assert "owner_user_id" not in response.json()
    service.missing = True
    assert client.get("/api/v1/me/academic-roadmap").status_code == 404


def test_report_and_explicit_modeled_path_remain_owner_scoped(api) -> None:
    client, service = api
    report = client.get("/api/v1/me/academic-report")
    assert report.status_code == 200
    assert report.headers["cache-control"] == "private, no-store"
    assert report.json()["modeled_state_marker"] == "MODELED_UNOFFICIAL"
    assert service.roadmap_owner == OWNER
    modeled = client.post("/api/v1/me/academic-roadmap/modeled-path", json={
        "max_credit_hours_per_semester": 18, "max_paths": 1,
    })
    assert modeled.status_code == 200
    assert service.modeled_owner == OWNER
    assert client.post("/api/v1/me/academic-roadmap/modeled-path", json={
        "max_credit_hours_per_semester": 18, "owner_user_id": "attacker",
    }).status_code == 422


def test_profile_crud_and_owner_is_never_client_controlled(api) -> None:
    client, service = api
    assert client.get("/api/v1/me/academic-profile").status_code == 200
    created = client.post("/api/v1/me/academic-profile", json={"study_plan_id": PLAN})
    assert created.status_code == 201 and service.created_owners == [OWNER]
    assert client.post("/api/v1/me/academic-profile", json={"study_plan_id": PLAN, "owner_user_id": "attacker"}).status_code == 422
    assert client.patch("/api/v1/me/academic-profile", json={"reported_cumulative_gpa": 3.5, "reported_gpa_scale": 4}).status_code == 200
    assert client.patch("/api/v1/me/academic-profile", json={"study_plan_id": PLAN}).status_code == 422
    assert client.delete("/api/v1/me/academic-profile").status_code == 204


def test_profile_missing_and_duplicate_have_intentional_statuses(api) -> None:
    client, service = api; service.missing = True
    assert client.get("/api/v1/me/academic-profile").status_code == 404
    service.missing = False; service.duplicate = True
    assert client.post("/api/v1/me/academic-profile", json={"study_plan_id": PLAN}).status_code == 409


@pytest.mark.parametrize("status_value", [item.value for item in AttemptOutcome])
def test_attempt_crud_accepts_exact_statuses_and_repeats(api, status_value) -> None:
    client, service = api
    before = len(service.records)
    response = client.post("/api/v1/me/academic-profile/attempts", json={"course_code": "0300103", "status": status_value, "raw_grade_text": "evidence"})
    assert response.status_code == 201 and response.json()["course_code"] == "0300103"
    assert response.json()["status"] == status_value and len(service.records) == before + 1
    assert client.get("/api/v1/me/academic-profile/attempts").status_code == 200
    assert client.patch(f"/api/v1/me/academic-profile/attempts/{ATTEMPT}", json={"status": "FAILED", "raw_grade_text": "A"}).json()["status"] == "FAILED"
    assert client.delete(f"/api/v1/me/academic-profile/attempts/{ATTEMPT}").status_code == 204


def test_attempt_validation_identity_immutability_and_errors(api) -> None:
    client, _ = api
    endpoint = "/api/v1/me/academic-profile/attempts"
    assert client.post(endpoint, json={"course_code": 300103, "status": "PASSED"}).status_code == 422
    assert client.post(endpoint, json={"course_code": "0300103", "status": "BAD"}).status_code == 422
    assert client.patch(f"{endpoint}/{ATTEMPT}", json={"course_code": "1501110"}).status_code == 422
    assert client.post(endpoint, json={"course_code": "unknown", "status": "PASSED"}).status_code == 404
    assert client.post(endpoint, json={"course_code": "foreign", "status": "PASSED"}).status_code == 409
    assert client.delete(f"{endpoint}/44444444-4444-4444-4444-444444444444").status_code == 404


@pytest.mark.parametrize("field", ["term_label", "raw_grade_text"])
@pytest.mark.parametrize("value", ["", "   "])
def test_nonblank_optional_attempt_text_is_rejected_as_422(api, field, value) -> None:
    client, _ = api
    endpoint = "/api/v1/me/academic-profile/attempts"
    assert client.post(endpoint, json={"course_code": "0300103", "status": "PASSED", field: value}).status_code == 422
    assert client.patch(f"{endpoint}/{ATTEMPT}", json={field: value}).status_code == 422


@pytest.mark.parametrize(("attempts", "target", "decision"), [
    ((AttemptOutcome.PASSED,), "1501112", "ELIGIBLE"),
    ((AttemptOutcome.FAILED,), "1501112", "NOT_ELIGIBLE"),
    ((), "1501112", "NOT_ELIGIBLE"),
    ((AttemptOutcome.FAILED, AttemptOutcome.PASSED), "1501112", "ELIGIBLE"),
    ((), "1505311", "REVIEW_REQUIRED"), ((), "1505320", "REVIEW_REQUIRED"),
    ((), "0200115", "ELIGIBLE"),
])
def test_profile_backed_eligibility_reuses_phase5(api, attempts, target, decision) -> None:
    client, service = api
    service.state = profile(tuple(__import__("app.rules.models", fromlist=["StudentCourseAttempt"]).StudentCourseAttempt("1501110", value) for value in attempts))
    response = client.get(f"/api/v1/me/eligibility/{target}")
    assert response.status_code == 200 and response.json()["decision"] == decision


def test_profile_eligibility_target_and_profile_errors(api) -> None:
    client, service = api
    assert client.get("/api/v1/me/eligibility/0300103").status_code == 409
    assert client.get("/api/v1/me/eligibility/unknown").status_code == 404
    service.missing = True
    assert client.get("/api/v1/me/eligibility/1501112").status_code == 404


def test_openapi_documents_secured_student_contracts(api) -> None:
    schema = api[0].get("/openapi.json").json()
    assert "/api/v1/me/academic-profile" in schema["paths"]
    assert "/api/v1/me/academic-profile/attempts/{attempt_id}" in schema["paths"]
    assert "/api/v1/me/eligibility/{target_course_code}" in schema["paths"]
    assert "/api/v1/me/academic-progress" in schema["paths"]
    assert schema["paths"]["/api/v1/me/academic-profile"]["get"]["security"]
    assert schema["paths"]["/api/v1/me/academic-progress"]["get"]["security"]
    assert schema["paths"]["/api/v1/me/academic-progress"]["get"].get("parameters", []) == []
    assert schema["components"]["schemas"]["AttemptOutcome"]["enum"] == ["PASSED", "FAILED", "IN_PROGRESS", "WITHDRAWN"]
    assert schema["components"]["schemas"]["CourseProgressState"]["enum"] == [
        "COMPLETED", "IN_PROGRESS", "ATTEMPTED_NOT_COMPLETED", "NOT_ATTEMPTED"
    ]
    assert schema["components"]["schemas"]["RequirementType"]["enum"] == ["required", "elective"]
    for request_schema in ("ProfileCreateRequest", "ProfileUpdateRequest", "AttemptCreateRequest", "AttemptUpdateRequest"):
        assert "owner_user_id" not in schema["components"]["schemas"][request_schema]["properties"]
    assert schema["components"]["schemas"]["AttemptCreateRequest"]["properties"]["course_code"]["type"] == "string"
