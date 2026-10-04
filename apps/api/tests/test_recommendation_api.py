"""Authenticated student course-recommendation API tests."""

from collections.abc import Iterator
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.api.routes.student import get_student_service
from app.catalog.errors import CatalogIntegrityError, CatalogTransportError
from app.core.auth import CurrentUser, get_current_user
from app.main import app
from app.recommendations.models import (
    RECOMMENDATION_POLICY_VERSION,
    RecommendationCandidate,
    RecommendationReason,
    RecommendationResult,
    ReviewRequiredCourse,
)
from app.student.errors import StudentProfileIntegrityError, StudentProfileNotFound

OWNER = "11111111-1111-1111-1111-111111111111"
PLAN = "10000000-0000-0000-0000-000000000005"


def _sample_candidate(
    code: str = "1501110",
    rank: int = 1,
    credit: str = "3",
    group: str = "FACULTY_REQUIRED",
    req_type: str = "required",
    p1: int = 2,
    p2: int = 1,
    p3: str = "3",
    p4: int = 0,
    p5: int = 2,
    p6: int = -1,
    reasons: tuple[RecommendationReason, ...] = (
        RecommendationReason.REQUIRED_PLAN_COURSE,
        RecommendationReason.ADVANCES_REQUIRED_GROUP,
        RecommendationReason.UNLOCKS_MULTIPLE_FUTURE_COURSES,
    ),
    previously_attempted: bool = False,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        course_code=code,
        course_name_ar="برمجة الحاسوب (1)",
        credit_hours=Decimal(credit),
        requirement_group_code=group,
        requirement_type=req_type,
        course_state="NOT_ATTEMPTED",
        eligibility_decision="ELIGIBLE",
        effective_credit_contribution=Decimal(p3),
        group_remaining_credits_before=Decimal("6"),
        group_remaining_credits_after=Decimal("3"),
        completes_requirement_group=bool(p4),
        newly_eligible_count=p5,
        newly_eligible_course_codes=("1501112", "1505101") if p5 > 0 else (),
        priority_tuple=(p1, p2, Decimal(p3), p4, p5, p6, code),
        rank=rank,
        reason_codes=reasons,
        previously_attempted=previously_attempted,
    )


def _sample_review_required(
    code: str = "1505311",
    reason: str = "PREREQUISITE_LOGIC_UNRESOLVED",
) -> ReviewRequiredCourse:
    return ReviewRequiredCourse(
        course_code=code,
        course_name_ar="ذكاء اصطناعي متقدم",
        credit_hours=Decimal("3"),
        requirement_group_code="MAJOR_REQUIRED",
        requirement_type="required",
        review_reason=reason,
        previously_attempted=False,
    )


class FakeStudentServiceForRecommendations:
    def __init__(self) -> None:
        self.ranked: list[RecommendationCandidate] = [
            _sample_candidate("1501110", rank=1, p6=-1),
            _sample_candidate("0200104", rank=2, p6=-2),
            _sample_candidate("0200111", rank=3, p6=-3),
            _sample_candidate("0200110", rank=4, p6=-4),
            _sample_candidate("0200115", rank=5, credit="0", p1=1, p3="0", p6=-5),
        ]
        self.review_required: list[ReviewRequiredCourse] = [
            _sample_review_required("1505311"),
        ]
        self.excluded_in_progress: list[str] = ["1501221"]
        self.missing_profile = False
        self.student_integrity_error = False
        self.catalog_integrity_error = False
        self.transport_error = False
        self.last_requested_owner: str | None = None
        self.last_limit: int | None = None

    async def get_course_recommendations(
        self,
        owner: str,
        *,
        limit: int | None = None,
    ) -> RecommendationResult:
        self.last_requested_owner = owner
        self.last_limit = limit

        if self.missing_profile:
            raise StudentProfileNotFound("Student profile was not found")
        if self.student_integrity_error:
            raise StudentProfileIntegrityError("Student integrity failure")
        if self.catalog_integrity_error:
            raise CatalogIntegrityError("Catalog integrity failure")
        if self.transport_error:
            raise CatalogTransportError("GET", "study_plans")

        ranked = tuple(self.ranked[:limit]) if limit is not None else tuple(self.ranked)
        return RecommendationResult(
            study_plan_id=PLAN,
            recommendation_policy_version=RECOMMENDATION_POLICY_VERSION,
            ranked_recommendations=ranked,
            review_required_courses=tuple(self.review_required),
            excluded_in_progress=tuple(self.excluded_in_progress),
            methodology_note="Academic decision support.",
            limitations=("Model bounded.",),
        )


@pytest.fixture
def api() -> Iterator[tuple[TestClient, FakeStudentServiceForRecommendations]]:
    service = FakeStudentServiceForRecommendations()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    app.dependency_overrides[get_student_service] = lambda: service
    with TestClient(app) as client:
        yield client, service
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------


def test_01_missing_auth_returns_401() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        response = client.get("/api/v1/me/course-recommendations")
        assert response.status_code == 401


def test_02_authenticated_current_user_accepted(api) -> None:
    client, service = api
    response = client.get("/api/v1/me/course-recommendations")
    assert response.status_code == 200
    assert service.last_requested_owner == OWNER


def test_03_no_owner_input_supported(api) -> None:
    client, service = api
    # Passing an owner in query params must NOT affect the owner used by service
    response = client.get("/api/v1/me/course-recommendations?owner_user_id=attacker")
    assert response.status_code == 200
    assert service.last_requested_owner == OWNER


# ---------------------------------------------------------------------------
# SUCCESS
# ---------------------------------------------------------------------------


def test_04_endpoint_returns_200(api) -> None:
    client, _ = api
    response = client.get("/api/v1/me/course-recommendations")
    assert response.status_code == 200


def test_05_policy_version_is_1_0(api) -> None:
    client, _ = api
    response = client.get("/api/v1/me/course-recommendations")
    assert response.json()["recommendation_policy_version"] == "1.0"


def test_06_ranked_recommendations_serialized(api) -> None:
    client, _ = api
    response = client.get("/api/v1/me/course-recommendations")
    data = response.json()
    assert len(data["ranked_recommendations"]) == 5
    first = data["ranked_recommendations"][0]
    assert first["course_code"] == "1501110"
    assert first["credit_hours"] == "3"
    assert first["rank"] == 1
    assert "REQUIRED_PLAN_COURSE" in first["reason_codes"]
    assert first["priority_tuple"] == [2, 1, "3", 0, 2, -1, "1501110"]


def test_07_review_required_serialized(api) -> None:
    client, _ = api
    response = client.get("/api/v1/me/course-recommendations")
    data = response.json()
    assert len(data["review_required_courses"]) == 1
    rr = data["review_required_courses"][0]
    assert rr["course_code"] == "1505311"
    assert rr["review_reason"] == "PREREQUISITE_LOGIC_UNRESOLVED"
    assert "rank" not in rr
    assert "priority_tuple" not in rr


def test_08_excluded_in_progress_serialized(api) -> None:
    client, _ = api
    response = client.get("/api/v1/me/course-recommendations")
    data = response.json()
    assert data["excluded_in_progress"] == ["1501221"]


# ---------------------------------------------------------------------------
# LIMIT
# ---------------------------------------------------------------------------


def test_09_limit_one_returns_first_ranked_item_only(api) -> None:
    client, service = api
    response = client.get("/api/v1/me/course-recommendations?limit=1")
    assert response.status_code == 200
    assert service.last_limit == 1
    data = response.json()
    assert len(data["ranked_recommendations"]) == 1
    assert data["ranked_recommendations"][0]["course_code"] == "1501110"


def test_10_limit_five_preserves_exact_ordering(api) -> None:
    client, service = api
    response = client.get("/api/v1/me/course-recommendations?limit=5")
    assert response.status_code == 200
    assert service.last_limit == 5
    data = response.json()
    codes = [c["course_code"] for c in data["ranked_recommendations"]]
    assert codes == ["1501110", "0200104", "0200111", "0200110", "0200115"]


def test_11_no_limit_returns_all(api) -> None:
    client, service = api
    response = client.get("/api/v1/me/course-recommendations")
    assert response.status_code == 200
    assert service.last_limit is None
    assert len(response.json()["ranked_recommendations"]) == 5


def test_12_limit_does_not_trim_review_required_courses(api) -> None:
    client, _ = api
    response = client.get("/api/v1/me/course-recommendations?limit=1")
    assert response.status_code == 200
    assert len(response.json()["review_required_courses"]) == 1


def test_13_limit_zero_returns_422(api) -> None:
    client, _ = api
    response = client.get("/api/v1/me/course-recommendations?limit=0")
    assert response.status_code == 422


def test_14_negative_limit_returns_422(api) -> None:
    client, _ = api
    response = client.get("/api/v1/me/course-recommendations?limit=-1")
    assert response.status_code == 422


def test_15_invalid_text_limit_returns_422(api) -> None:
    client, _ = api
    response = client.get("/api/v1/me/course-recommendations?limit=abc")
    assert response.status_code == 422


def test_16_excessive_limit_returns_422(api) -> None:
    client, _ = api
    response = client.get("/api/v1/me/course-recommendations?limit=101")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# EMPTY CASES
# ---------------------------------------------------------------------------


def test_17_empty_ranked_list_returns_200(api) -> None:
    client, service = api
    service.ranked = []
    response = client.get("/api/v1/me/course-recommendations")
    assert response.status_code == 200
    assert response.json()["ranked_recommendations"] == []


def test_18_only_review_required_returns_200(api) -> None:
    client, service = api
    service.ranked = []
    service.review_required = [_sample_review_required("1505311")]
    response = client.get("/api/v1/me/course-recommendations")
    assert response.status_code == 200
    data = response.json()
    assert data["ranked_recommendations"] == []
    assert len(data["review_required_courses"]) == 1


# ---------------------------------------------------------------------------
# ERRORS
# ---------------------------------------------------------------------------


def test_19_missing_profile_returns_404(api) -> None:
    client, service = api
    service.missing_profile = True
    response = client.get("/api/v1/me/course-recommendations")
    assert response.status_code == 404
    assert response.json()["error_code"] == "STUDENT_RESOURCE_NOT_FOUND"


def test_20_student_integrity_returns_500(api) -> None:
    client, service = api
    service.student_integrity_error = True
    response = client.get("/api/v1/me/course-recommendations")
    assert response.status_code == 500
    assert response.json()["error_code"] == "STUDENT_INTEGRITY_ERROR"


def test_21_catalog_integrity_returns_500(api) -> None:
    client, service = api
    service.catalog_integrity_error = True
    response = client.get("/api/v1/me/course-recommendations")
    assert response.status_code == 500
    assert response.json()["error_code"] == "CATALOG_INTEGRITY_ERROR"


def test_22_transport_returns_503(api) -> None:
    client, service = api
    service.transport_error = True
    response = client.get("/api/v1/me/course-recommendations")
    assert response.status_code == 503
    assert response.json()["error_code"] == "CATALOG_TRANSPORT_ERROR"


# ---------------------------------------------------------------------------
# OPENAPI
# ---------------------------------------------------------------------------


def test_23_openapi_documents_course_recommendations_contract() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        paths = schema["paths"]
        assert "/api/v1/me/course-recommendations" in paths
        endpoint = paths["/api/v1/me/course-recommendations"]["get"]
        # Must have security requirement
        assert endpoint.get("security")
        # Parameter checks: no owner, no study_plan_id, no attempts; optional limit
        param_names = [p["name"] for p in endpoint.get("parameters", [])]
        assert "owner_user_id" not in param_names
        assert "study_plan_id" not in param_names
        assert "attempts" not in param_names
        assert "limit" in param_names
        # Check limit schema
        param = next(p for p in endpoint["parameters"] if p["name"] == "limit")
        assert param["in"] == "query"
        param_schema = param["schema"]
        int_schema = next(s for s in param_schema.get("anyOf", [param_schema]) if s.get("type") == "integer")
        assert int_schema.get("minimum") == 1
        assert int_schema.get("maximum") == 100
        # Check component schemas
        components = schema["components"]["schemas"]
        assert "RecommendationResponse" in components
        assert "RecommendationReason" in components
        assert "REQUIRED_PLAN_COURSE" in components["RecommendationReason"]["enum"]
