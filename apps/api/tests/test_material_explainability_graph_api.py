"""Student and assigned-advisor graph HTTP boundaries."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.advisor_persistence.models import AdvisorAccessContext
from app.advisor_service.errors import AdvisorAuthorizationError, AdvisorAuthorizationErrorCode
from app.api.routes.advisor_explainability_graph import get_advisor_authorization
from app.api.routes.student import get_student_service
from app.core.auth import CurrentUser, get_current_user
from app.main import app
from tests.test_degree_path_api import _sample_degree_path_result
from tests.test_recommendation_api import FakeStudentServiceForRecommendations
from tests.test_semester_planner_api import FakeStudentServiceForPlanner
from tests.test_student_api import FakeStudentService


STUDENT = "11111111-1111-1111-1111-111111111111"
ADVISOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
UNIVERSITY = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ASSIGNMENT = "cccccccc-cccc-cccc-cccc-cccccccccccc"


class GraphStudentService:
    def __init__(self) -> None:
        self.owners: list[str] = []
        self.recommendations = FakeStudentServiceForRecommendations()
        self.planner = FakeStudentServiceForPlanner()
        self.eligibility = FakeStudentService()

    async def get_course_recommendations(self, owner, *, limit=None):
        self.owners.append(owner)
        return await self.recommendations.get_course_recommendations(owner, limit=limit)

    async def get_semester_plans(self, owner, **kwargs):
        self.owners.append(owner)
        return await self.planner.get_semester_plans(owner, **kwargs)

    async def get_degree_paths(self, owner, **kwargs):
        self.owners.append(owner)
        return _sample_degree_path_result()

    async def evaluate_can_take(self, owner, target):
        self.owners.append(owner)
        return await self.eligibility.evaluate_can_take(owner, target)


class Authorization:
    def __init__(self) -> None:
        self.deny = False
        self.calls: list[tuple[str, str]] = []

    async def authorize_advisor_for_student(self, advisor, student):
        self.calls.append((str(advisor), str(student)))
        if self.deny:
            raise AdvisorAuthorizationError(AdvisorAuthorizationErrorCode.ADVISOR_ACCESS_DENIED, "denied")
        if str(student) != STUDENT:
            raise AdvisorAuthorizationError(AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH, "denied")
        return AdvisorAccessContext(UUID(ADVISOR), UUID(STUDENT), UUID(UNIVERSITY),
                                    UUID(ASSIGNMENT), "test", "1")


@pytest.fixture
def api():
    service = GraphStudentService()
    authorization = Authorization()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(ADVISOR)
    app.dependency_overrides[get_student_service] = lambda: service
    app.dependency_overrides[get_advisor_authorization] = lambda: authorization
    with TestClient(app) as client:
        yield client, service, authorization
    app.dependency_overrides.clear()


def test_graph_routes_require_authentication():
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        for method, path, body in (
            ("get", "/api/v1/me/course-recommendations/explanation-graph", None),
            ("post", "/api/v1/me/semester-plans/explanation-graph", {"max_credit_hours": "15"}),
            ("post", "/api/v1/me/degree-paths/explanation-graph", {"max_credit_hours_per_semester": "15"}),
            ("get", f"/api/v1/advisor/students/{STUDENT}/course-recommendations/explanation-graph", None),
        ):
            response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
            assert response.status_code == 401


def test_student_material_routes_use_authenticated_owner_and_original_constraints(api):
    client, service, _ = api
    rec = client.get("/api/v1/me/course-recommendations/explanation-graph?limit=2")
    plan = client.post("/api/v1/me/semester-plans/explanation-graph",
                       json={"max_credit_hours": "15", "max_courses": 5, "max_options": 2})
    path = client.post("/api/v1/me/degree-paths/explanation-graph",
                       json={"max_credit_hours_per_semester": "15", "max_paths": 2})
    assert (rec.status_code, plan.status_code, path.status_code) == (200, 200, 200)
    assert service.owners == [ADVISOR, ADVISOR, ADVISOR]
    assert rec.json()["subject_type"] == "COURSE_RECOMMENDATIONS"
    assert plan.json()["policy_versions"] == ["1.0"]
    assert path.json()["subject_type"] == "DEGREE_PATH"
    assert STUDENT not in str(rec.json()) and ADVISOR not in str(plan.json())


def test_student_why_not_is_bounded_and_unknown_evidence_abstains(api):
    client, _, _ = api
    url = "/api/v1/me/course-recommendations/explanation-graph"
    assert client.get(url + "?mode=why_not&course_code=1505311").status_code == 200
    unknown = client.get(url + "?mode=why_not&course_code=9999999")
    assert unknown.status_code == 200
    assert "WHY_NOT_EVIDENCE_UNAVAILABLE" in unknown.json()["limitations"]
    assert client.get(url + "?mode=why_not").status_code == 422
    assert client.get(url + "?student_user_id=" + STUDENT).status_code == 422
    assert client.post("/api/v1/me/semester-plans/explanation-graph",
                       json={"max_credit_hours": "15", "study_plan_id": STUDENT}).status_code == 422


def test_advisor_routes_authorize_exact_target_before_any_student_load(api):
    client, service, authorization = api
    base = f"/api/v1/advisor/students/{STUDENT}"
    for method, path, body in (
        ("get", base + "/eligibility/0200115/explanation-graph", None),
        ("get", base + "/course-recommendations/explanation-graph", None),
        ("post", base + "/semester-plans/explanation-graph", {"max_credit_hours": "15"}),
        ("post", base + "/degree-paths/explanation-graph", {"max_credit_hours_per_semester": "15"}),
    ):
        response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
        assert response.status_code == 200, response.text
        assert STUDENT not in str(response.json())
    assert service.owners == [STUDENT] * 4
    assert authorization.calls == [(ADVISOR, STUDENT)] * 4

    service.owners.clear()
    authorization.deny = True
    denied = client.get(base + "/course-recommendations/explanation-graph")
    assert denied.status_code == 403 and not service.owners
    assert client.get(f"/api/v1/advisor/students/{UUID(int=4)}/course-recommendations/explanation-graph").status_code == 403
