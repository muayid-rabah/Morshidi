"""Authenticated student semester planner API tests (Phase 8.3)."""

from collections.abc import Iterator
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.api.routes.student import get_student_service
from app.catalog.errors import CatalogIntegrityError, CatalogTransportError
from app.core.auth import CurrentUser, get_current_user
from app.main import app
from app.planner.models import (
    DEFAULT_CANDIDATE_WINDOW_SIZE,
    PLANNING_SCOPE,
    SEMESTER_PLANNER_POLICY_VERSION,
    PlanReasonCode,
    PlannedCourseEntry,
    PlannerConstraints,
    PlannerIntegrityError,
    SemesterPlanOption,
    SemesterPlannerResult,
)
from app.student.errors import StudentProfileIntegrityError, StudentProfileNotFound

OWNER = "11111111-1111-1111-1111-111111111111"
PLAN = "10000000-0000-0000-0000-000000000005"


def _sample_planned_course(
    code: str = "1501110",
    name_ar: str = "برمجة الحاسوب (1)",
    name_en: str | None = "Computer Programming (1)",
    credit: str = "3",
    group: str = "FACULTY_REQUIRED",
    req_type: str = "required",
    phase7_rank: int = 1,
    previously_attempted: bool = False,
    display_order: int = 1,
) -> PlannedCourseEntry:
    return PlannedCourseEntry(
        course_code=code,
        course_name_ar=name_ar,
        course_name_en=name_en,
        credit_hours=Decimal(credit),
        requirement_group_code=group,
        requirement_type=req_type,
        phase7_rank=phase7_rank,
        previously_attempted=previously_attempted,
        display_order=display_order,
    )


def _sample_plan_option(
    rank: int = 1,
    courses: tuple[PlannedCourseEntry, ...] | None = None,
    total_credit: str = "15",
    total_courses: int = 5,
    mandatory_count: int = 5,
    zero_credit_count: int = 0,
    credit_delta: str = "15",
    reasons: tuple[PlanReasonCode, ...] = (
        PlanReasonCode.CONTAINS_MANDATORY_COURSES,
        PlanReasonCode.MAXIMIZES_MODELED_CREDIT_PROGRESS,
        PlanReasonCode.UNLOCKS_MULTIPLE_FUTURE_COURSES,
        PlanReasonCode.USES_FULL_CREDIT_PREFERENCE,
    ),
) -> SemesterPlanOption:
    if courses is None:
        courses = (
            _sample_planned_course("1501110", phase7_rank=1, display_order=1),
            _sample_planned_course("0200104", phase7_rank=2, display_order=2),
            _sample_planned_course("0200111", phase7_rank=3, display_order=3),
            _sample_planned_course("0200110", phase7_rank=4, display_order=4),
            _sample_planned_course("1501221", phase7_rank=5, display_order=5),
        )
    return SemesterPlanOption(
        rank=rank,
        courses=courses,
        total_credit_hours=Decimal(total_credit),
        total_courses=total_courses,
        mandatory_course_count=mandatory_count,
        zero_credit_required_count=zero_credit_count,
        completed_plan_credit_delta=Decimal(credit_delta),
        newly_satisfied_requirement_group_codes=(),
        newly_satisfied_requirement_group_count=0,
        newly_eligible_course_codes=("1501112",),
        newly_eligible_count=1,
        recommendation_rank_sum=15,
        priority_tuple=(
            mandatory_count,
            0,
            Decimal(credit_delta),
            1,
            Decimal(total_credit),
            15,
            tuple(c.course_code for c in courses),
        ),
        reason_codes=reasons,
    )


class FakeStudentServiceForPlanner:
    def __init__(self) -> None:
        self.options: list[SemesterPlanOption] = [_sample_plan_option(rank=1)]
        self.review_required_courses: list[str] = ["1505311"]
        self.excluded_in_progress: list[str] = ["1501221"]
        self.missing_profile = False
        self.student_integrity_error = False
        self.catalog_integrity_error = False
        self.planner_integrity_error = False
        self.transport_error = False
        self.last_requested_owner: str | None = None
        self.last_max_credit_hours: Decimal | None = None
        self.last_max_courses: int | None = None
        self.last_max_options: int | None = None

    async def get_semester_plans(
        self,
        owner: str,
        *,
        max_credit_hours: Decimal,
        max_courses: int | None = None,
        max_options: int = 5,
        candidate_window_size: int = DEFAULT_CANDIDATE_WINDOW_SIZE,
    ) -> SemesterPlannerResult:
        self.last_requested_owner = owner
        self.last_max_credit_hours = max_credit_hours
        self.last_max_courses = max_courses
        self.last_max_options = max_options

        if self.missing_profile:
            raise StudentProfileNotFound("Student profile was not found")
        if self.student_integrity_error:
            raise StudentProfileIntegrityError("Student integrity failure")
        if self.catalog_integrity_error:
            raise CatalogIntegrityError("Catalog integrity failure")
        if self.planner_integrity_error:
            raise PlannerIntegrityError("Planner integrity failure")
        if self.transport_error:
            raise CatalogTransportError("GET", "study_plans")

        constraints = PlannerConstraints(
            max_credit_hours=max_credit_hours,
            max_courses=max_courses,
            max_options=max_options,
        )

        return SemesterPlannerResult(
            study_plan_id=PLAN,
            semester_planner_policy_version=SEMESTER_PLANNER_POLICY_VERSION,
            planning_scope=PLANNING_SCOPE,
            constraints=constraints,
            candidate_window_size=candidate_window_size,
            eligible_ranked_candidate_count=len(self.options[0].courses) if self.options else 0,
            evaluated_candidate_count=len(self.options[0].courses) if self.options else 0,
            valid_combination_count=len(self.options),
            plan_options=tuple(self.options[:max_options]),
            review_required_courses=tuple(self.review_required_courses),
            excluded_in_progress=tuple(self.excluded_in_progress),
            methodology_note="Deterministic semester planner.",
            limitations=("Search bounded to top M.",),
        )


@pytest.fixture
def api() -> Iterator[tuple[TestClient, FakeStudentServiceForPlanner]]:
    service = FakeStudentServiceForPlanner()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    app.dependency_overrides[get_student_service] = lambda: service
    with TestClient(app) as client:
        yield client, service
    app.dependency_overrides.clear()


# ===========================================================================
# PART 8.1: AUTHENTICATION & INPUT BOUNDARY (Tests 1–6)
# ===========================================================================


def test_01_missing_auth_returns_401() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
        assert res.status_code == 401


def test_02_authenticated_user_request_accepted(api) -> None:
    client, service = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    assert service.last_requested_owner == OWNER


def test_03_no_owner_user_id_accepted_in_body(api) -> None:
    client, _ = api
    res = client.post(
        "/api/v1/me/semester-plans",
        json={"max_credit_hours": 15, "owner_user_id": "other-user"},
    )
    assert res.status_code == 422


def test_04_no_study_plan_id_accepted_in_body(api) -> None:
    client, _ = api
    res = client.post(
        "/api/v1/me/semester-plans",
        json={"max_credit_hours": 15, "study_plan_id": "some-plan"},
    )
    assert res.status_code == 422


def test_05_no_attempts_accepted_in_body(api) -> None:
    client, _ = api
    res = client.post(
        "/api/v1/me/semester-plans",
        json={"max_credit_hours": 15, "attempts": []},
    )
    assert res.status_code == 422


def test_06_no_candidate_window_size_accepted_in_body(api) -> None:
    client, _ = api
    res = client.post(
        "/api/v1/me/semester-plans",
        json={"max_credit_hours": 15, "candidate_window_size": 20},
    )
    assert res.status_code == 422


# ===========================================================================
# PART 8.2: VALID REQUEST VALUES (Tests 7–14)
# ===========================================================================


def test_07_valid_15_credits_returns_200(api) -> None:
    client, service = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    assert service.last_max_credit_hours == Decimal("15")


def test_08_valid_zero_credits_accepted(api) -> None:
    client, service = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 0})
    assert res.status_code == 200
    assert service.last_max_credit_hours == Decimal("0")


def test_09_max_courses_omitted_accepted(api) -> None:
    client, service = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    assert service.last_max_courses is None


def test_10_max_courses_1_accepted(api) -> None:
    client, service = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15, "max_courses": 1})
    assert res.status_code == 200
    assert service.last_max_courses == 1


def test_11_max_courses_10_accepted(api) -> None:
    client, service = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15, "max_courses": 10})
    assert res.status_code == 200
    assert service.last_max_courses == 10


def test_12_max_options_default_5(api) -> None:
    client, service = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    assert service.last_max_options == 5


def test_13_max_options_1_accepted(api) -> None:
    client, service = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15, "max_options": 1})
    assert res.status_code == 200
    assert service.last_max_options == 1


def test_14_max_options_10_accepted(api) -> None:
    client, service = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15, "max_options": 10})
    assert res.status_code == 200
    assert service.last_max_options == 10


# ===========================================================================
# PART 8.3: REQUEST VALIDATION ERRORS (Tests 15–22)
# ===========================================================================


def test_15_negative_max_credit_hours_rejected(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": -1})
    assert res.status_code == 422


def test_16_exceeding_30_credits_rejected(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 30.5})
    assert res.status_code == 422


def test_17_malformed_credit_rejected(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": "abc"})
    assert res.status_code == 422


def test_18_max_courses_zero_rejected(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15, "max_courses": 0})
    assert res.status_code == 422


def test_19_max_courses_11_rejected(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15, "max_courses": 11})
    assert res.status_code == 422


def test_20_max_options_zero_rejected(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15, "max_options": 0})
    assert res.status_code == 422


def test_21_max_options_11_rejected(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15, "max_options": 11})
    assert res.status_code == 422


def test_22_extra_field_rejected(api) -> None:
    client, _ = api
    res = client.post(
        "/api/v1/me/semester-plans",
        json={"max_credit_hours": 15, "unknown_field": "val"},
    )
    assert res.status_code == 422


# ===========================================================================
# PART 8.4: RESPONSE SERIALIZATION (Tests 23–30)
# ===========================================================================


def test_23_policy_version_and_planning_scope(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    data = res.json()
    assert data["semester_planner_policy_version"] == "1.0"
    assert data["planning_scope"] == "ACADEMIC_STRUCTURE_ONLY"


def test_24_candidate_window_size_in_response(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    data = res.json()
    assert data["candidate_window_size"] == 15


def test_25_plan_options_serialized(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    data = res.json()
    assert len(data["plan_options"]) == 1
    opt = data["plan_options"][0]
    assert opt["rank"] == 1
    assert opt["total_courses"] == 5
    assert len(opt["courses"]) == 5
    c0 = opt["courses"][0]
    assert c0["course_code"] == "1501110"
    assert c0["course_name_en"] == "Computer Programming (1)"
    assert c0["requirement_type"] == "required"


def test_26_reason_codes_serialized(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    opt = res.json()["plan_options"][0]
    assert "CONTAINS_MANDATORY_COURSES" in opt["reason_codes"]
    assert "MAXIMIZES_MODELED_CREDIT_PROGRESS" in opt["reason_codes"]


def test_27_priority_tuple_serialized_correctly(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    opt = res.json()["plan_options"][0]
    assert isinstance(opt["priority_tuple"], list)
    assert len(opt["priority_tuple"]) == 7


def test_28_decimal_credits_serialization(api) -> None:
    client, service = api
    course = _sample_planned_course(credit="3.50")
    service.options = [_sample_plan_option(total_credit="12.50", courses=(course,))]
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": "12.50"})
    assert res.status_code == 200
    opt = res.json()["plan_options"][0]
    assert Decimal(str(opt["total_credit_hours"])) == Decimal("12.50")


def test_29_review_required_courses_serialized(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    data = res.json()
    assert data["review_required_courses"] == ["1505311"]


def test_30_excluded_in_progress_serialized(api) -> None:
    client, _ = api
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    data = res.json()
    assert data["excluded_in_progress"] == ["1501221"]


# ===========================================================================
# PART 8.5: EMPTY & SPECIAL STATES (Tests 31–32)
# ===========================================================================


def test_31_empty_plan_options_returns_200(api) -> None:
    client, service = api
    service.options = []
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    data = res.json()
    assert data["plan_options"] == []
    assert data["valid_combination_count"] == 0


def test_32_completed_plan_state_returns_200(api) -> None:
    client, service = api
    service.options = []
    service.review_required_courses = []
    service.excluded_in_progress = []
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 200
    assert res.json()["plan_options"] == []


# ===========================================================================
# PART 8.6: ERROR MAPPINGS (Tests 33–35)
# ===========================================================================


def test_33_profile_missing_returns_404(api) -> None:
    client, service = api
    service.missing_profile = True
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 404
    assert res.json()["error_code"] == "STUDENT_RESOURCE_NOT_FOUND"


def test_34_integrity_error_returns_500(api) -> None:
    client, service = api
    service.planner_integrity_error = True
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 500
    assert res.json()["error_code"] == "CATALOG_INTEGRITY_ERROR"


def test_35_transport_error_returns_503(api) -> None:
    client, service = api
    service.transport_error = True
    res = client.post("/api/v1/me/semester-plans", json={"max_credit_hours": 15})
    assert res.status_code == 503
    assert res.json()["error_code"] == "CATALOG_TRANSPORT_ERROR"
