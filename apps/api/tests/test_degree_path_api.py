"""Authenticated student degree path planner API tests (Phase 9.3)."""

from collections.abc import Iterator
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from app.api.routes.student import get_student_service
from app.catalog.errors import CatalogIntegrityError, CatalogTransportError
from app.core.auth import CurrentUser, get_current_user
from app.degree_path.models import (
    DEGREE_PATH_POLICY_VERSION,
    PLANNING_SCOPE,
    BlockerType,
    DegreePathConstraintError,
    DegreePathCapacityError,
    DegreePathComputationTimeout,
    DegreePathConstraints,
    DegreePathIntegrityError,
    DegreePathOption,
    DegreePathResult,
    ModeledSemesterEntry,
    PathReasonCode,
    PathStatus,
)
from app.main import app
from app.planner.models import (
    PlanReasonCode,
    PlannedCourseEntry,
    SemesterPlanOption,
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
    ),
) -> SemesterPlanOption:
    if courses is None:
        courses = (
            _sample_planned_course("1501110", phase7_rank=1, display_order=1),
            _sample_planned_course("0200110", phase7_rank=2, display_order=2),
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
        recommendation_rank_sum=3,
        priority_tuple=(
            mandatory_count,
            0,
            Decimal(credit_delta),
            1,
            Decimal(total_credit),
            3,
            tuple(c.course_code for c in courses),
        ),
        reason_codes=reasons,
    )


def _sample_modeled_semester(
    semester_index: int = 1,
    plan_option: SemesterPlanOption | None = None,
    completed_after: str = "15",
    remaining_after: str = "117",
    satisfied_groups: tuple[str, ...] = ("FACULTY_REQUIRED",),
) -> ModeledSemesterEntry:
    return ModeledSemesterEntry(
        semester_index=semester_index,
        plan_option=plan_option or _sample_plan_option(),
        completed_plan_credits_after=Decimal(completed_after),
        remaining_plan_credits_after=Decimal(remaining_after),
        newly_satisfied_requirement_group_codes=satisfied_groups,
    )


def _sample_degree_path_option(
    rank: int = 1,
    status: PathStatus = PathStatus.MODELED_COMPLETE,
    semesters: tuple[ModeledSemesterEntry, ...] | None = None,
    semester_count: int = 1,
    total_planned_courses: int = 2,
    total_planned_credits: str = "6",
    credit_delta: str = "6",
    final_completed: str = "132",
    final_remaining: str = "0",
    newly_satisfied_group_count: int = 1,
    unresolved_blockers: tuple[str, ...] = (),
    reason_codes: tuple[PathReasonCode, ...] = (
        PathReasonCode.REACHES_MODELED_PLAN_COMPLETION,
        PathReasonCode.FEWER_MODELED_SEMESTERS,
    ),
) -> DegreePathOption:
    if semesters is None:
        semesters = (_sample_modeled_semester(),)
    p1 = 1 if status is PathStatus.MODELED_COMPLETE else 0
    return DegreePathOption(
        rank=rank,
        status=status,
        semesters=semesters,
        semester_count=semester_count,
        total_planned_courses=total_planned_courses,
        total_planned_credits=Decimal(total_planned_credits),
        completed_plan_credit_delta=Decimal(credit_delta),
        final_completed_plan_credits=Decimal(final_completed),
        final_remaining_plan_credits=Decimal(final_remaining),
        newly_satisfied_requirement_group_count=newly_satisfied_group_count,
        newly_satisfied_requirement_group_codes=("FACULTY_REQUIRED",),
        remaining_required_course_codes=(),
        unresolved_blocker_codes=unresolved_blockers,
        aggregate_semester_rank_sum=1,
        priority_tuple=(
            -p1,
            semester_count,
            -Decimal(credit_delta),
            -newly_satisfied_group_count,
            len(unresolved_blockers),
            1,
            (("1501110", "0200110"),),
        ),
        reason_codes=reason_codes,
    )


def _sample_degree_path_result(
    constraints: DegreePathConstraints | None = None,
    paths: tuple[DegreePathOption, ...] | None = None,
    unresolved_review: tuple[str, ...] = (),
    persisted_in_prog: tuple[str, ...] = (),
    total_parent_states_expanded: int = 3,
) -> DegreePathResult:
    if constraints is None:
        constraints = DegreePathConstraints(
            max_credit_hours_per_semester=Decimal("15"),
            max_courses_per_semester=5,
            max_semesters_ahead=8,
            max_paths=3,
        )
    if paths is None:
        paths = (_sample_degree_path_option(),)
    return DegreePathResult(
        study_plan_id=PLAN,
        degree_path_policy_version=DEGREE_PATH_POLICY_VERSION,
        planning_scope=PLANNING_SCOPE,
        constraints=constraints,
        paths=paths,
        initial_completed_credits=Decimal("0"),
        initial_remaining_credits=Decimal("132"),
        initial_satisfied_group_count=0,
        total_requirement_group_count=5,
        unresolved_review_required_courses=unresolved_review,
        persisted_in_progress_courses=persisted_in_prog,
        total_parent_states_expanded=total_parent_states_expanded,
        methodology_note="Academic simulation note.",
        limitations=("Hypothetical passes only.",),
    )


class FakeStudentService:
    def __init__(self, result: DegreePathResult | None = None, error: Exception | None = None) -> None:
        self.result = result or _sample_degree_path_result()
        self.error = error
        self.calls: list[dict] = []

    async def get_degree_paths(
        self,
        owner: str,
        *,
        max_credit_hours_per_semester: Decimal,
        max_courses_per_semester: int | None = None,
        max_semesters_ahead: int = 8,
        max_paths: int = 3,
        cancel_event=None,
    ) -> DegreePathResult:
        self.calls.append({
            "owner": owner,
            "max_credit_hours_per_semester": max_credit_hours_per_semester,
            "max_courses_per_semester": max_courses_per_semester,
            "max_semesters_ahead": max_semesters_ahead,
            "max_paths": max_paths,
        })
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def fake_service() -> FakeStudentService:
    return FakeStudentService()


@pytest.fixture
def auth_user() -> CurrentUser:
    return CurrentUser(OWNER)


@pytest.fixture
def client(fake_service: FakeStudentService, auth_user: CurrentUser) -> Iterator[TestClient]:
    app.dependency_overrides[get_student_service] = lambda: fake_service
    app.dependency_overrides[get_current_user] = lambda: auth_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ===========================================================================
# 1. Authentication (Tests 1-2)
# ===========================================================================


def test_01_missing_auth_returns_401(fake_service: FakeStudentService) -> None:
    app.dependency_overrides[get_student_service] = lambda: fake_service
    with TestClient(app) as unauth_client:
        resp = unauth_client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
        assert resp.status_code == 401
    app.dependency_overrides.clear()


def test_02_authenticated_user_request_accepted(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 200


# ===========================================================================
# 2. Request Surface (Tests 3-6)
# ===========================================================================


def test_03_max_credit_hours_per_semester_accepted(client: TestClient, fake_service: FakeStudentService) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 18})
    assert resp.status_code == 200
    assert fake_service.calls[-1]["max_credit_hours_per_semester"] == Decimal("18")


def test_04_max_courses_per_semester_optional(client: TestClient, fake_service: FakeStudentService) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 200
    assert fake_service.calls[-1]["max_courses_per_semester"] is None


def test_05_max_semesters_ahead_default_8(client: TestClient, fake_service: FakeStudentService) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 200
    assert fake_service.calls[-1]["max_semesters_ahead"] == 8


def test_06_max_paths_default_3(client: TestClient, fake_service: FakeStudentService) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 200
    assert fake_service.calls[-1]["max_paths"] == 3


# ===========================================================================
# 3. Forbidden Overrides (Tests 7-14)
# ===========================================================================


def test_07_owner_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "owner": "hacker"})
    assert resp.status_code == 422


def test_08_study_plan_id_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "study_plan_id": PLAN})
    assert resp.status_code == 422


def test_09_attempts_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "attempts": []})
    assert resp.status_code == 422


def test_10_gpa_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "reported_cumulative_gpa": 3.5})
    assert resp.status_code == 422


def test_11_beam_width_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "beam_width": 5})
    assert resp.status_code == 422


def test_12_semester_branch_width_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "semester_branch_width": 5})
    assert resp.status_code == 422


def test_13_candidate_window_size_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "candidate_window_size": 20})
    assert resp.status_code == 422


def test_14_recommendation_input_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "recommendations": []})
    assert resp.status_code == 422


# ===========================================================================
# 4. Validation (Tests 15-31)
# ===========================================================================


def test_15_credits_0_accepted(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 0})
    assert resp.status_code == 200


def test_16_credits_30_accepted(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 30})
    assert resp.status_code == 200


def test_17_credits_negative_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": -1})
    assert resp.status_code == 422


def test_18_credits_exceeding_30_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 30.5})
    assert resp.status_code == 422


def test_19_credits_malformed_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": "invalid"})
    assert resp.status_code == 422


def test_20_max_courses_1_accepted(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_courses_per_semester": 1})
    assert resp.status_code == 200


def test_21_max_courses_10_accepted(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_courses_per_semester": 10})
    assert resp.status_code == 200


def test_22_max_courses_0_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_courses_per_semester": 0})
    assert resp.status_code == 422


def test_23_max_courses_11_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_courses_per_semester": 11})
    assert resp.status_code == 422


def test_24_horizon_1_accepted(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 1})
    assert resp.status_code == 200


def test_25_horizon_16_accepted(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 16})
    assert resp.status_code == 200


def test_26_horizon_0_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 0})
    assert resp.status_code == 422


def test_27_horizon_17_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 17})
    assert resp.status_code == 422


def test_28_max_paths_1_accepted(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_paths": 1})
    assert resp.status_code == 200


def test_29_max_paths_10_accepted(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_paths": 10})
    assert resp.status_code == 200


def test_30_max_paths_0_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_paths": 0})
    assert resp.status_code == 422


def test_31_max_paths_11_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15, "max_paths": 11})
    assert resp.status_code == 422


# ===========================================================================
# 5. Response Structure & Serialization (Tests 32-41)
# ===========================================================================


def test_32_policy_version_and_scope(client: TestClient) -> None:
    data = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15}).json()
    assert data["degree_path_policy_version"] == "1.0"
    assert data["planning_scope"] == "MODELED_DEGREE_PATH_ONLY"


def test_33_scope_marker(client: TestClient) -> None:
    data = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15}).json()
    assert data["planning_scope"] == "MODELED_DEGREE_PATH_ONLY"


def test_34_paths_serialize(client: TestClient) -> None:
    data = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15}).json()
    assert len(data["paths"]) == 1
    assert data["paths"][0]["rank"] == 1


def test_35_semesters_serialize(client: TestClient) -> None:
    data = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15}).json()
    sem = data["paths"][0]["semesters"][0]
    assert sem["semester_index"] == 1
    assert sem["plan_option"]["total_credit_hours"] == "15"


def test_36_statuses_serialize(client: TestClient) -> None:
    data = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15}).json()
    assert data["paths"][0]["status"] == "MODELED_COMPLETE"


def test_37_blockers_serialize(client: TestClient, fake_service: FakeStudentService) -> None:
    opt = _sample_degree_path_option(
        status=PathStatus.BLOCKED_BY_REVIEW_REQUIRED,
        unresolved_blockers=(BlockerType.REVIEW_REQUIRED_BLOCKER.value,),
    )
    fake_service.result = _sample_degree_path_result(paths=(opt,))
    data = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15}).json()
    assert data["paths"][0]["unresolved_blocker_codes"] == ["REVIEW_REQUIRED_BLOCKER"]


def test_38_reason_codes_serialize(client: TestClient) -> None:
    data = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15}).json()
    assert "REACHES_MODELED_PLAN_COMPLETION" in data["paths"][0]["reason_codes"]


def test_39_priority_tuple_serializes(client: TestClient) -> None:
    data = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15}).json()
    tup = data["paths"][0]["priority_tuple"]
    assert isinstance(tup, list)
    assert len(tup) == 7


def test_40_decimal_values_serialize_consistently(client: TestClient) -> None:
    data = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": "12.50"}).json()
    assert data["paths"][0]["total_planned_credits"] == "6"
    assert data["initial_remaining_credits"] == "132"


def test_41_limitations_serialize(client: TestClient) -> None:
    data = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15}).json()
    assert len(data["limitations"]) > 0


# ===========================================================================
# 6. Domain Statuses / HTTP 200 (Tests 42-46)
# ===========================================================================


def test_42_modeled_complete_returns_200(client: TestClient, fake_service: FakeStudentService) -> None:
    fake_service.result = _sample_degree_path_result(paths=(_sample_degree_path_option(status=PathStatus.MODELED_COMPLETE),))
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 200
    assert resp.json()["paths"][0]["status"] == "MODELED_COMPLETE"


def test_43_horizon_reached_returns_200(client: TestClient, fake_service: FakeStudentService) -> None:
    fake_service.result = _sample_degree_path_result(paths=(_sample_degree_path_option(status=PathStatus.HORIZON_REACHED),))
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 200
    assert resp.json()["paths"][0]["status"] == "HORIZON_REACHED"


def test_44_review_blocked_returns_200(client: TestClient, fake_service: FakeStudentService) -> None:
    fake_service.result = _sample_degree_path_result(paths=(_sample_degree_path_option(status=PathStatus.BLOCKED_BY_REVIEW_REQUIRED),))
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 200
    assert resp.json()["paths"][0]["status"] == "BLOCKED_BY_REVIEW_REQUIRED"


def test_45_in_progress_blocked_returns_200(client: TestClient, fake_service: FakeStudentService) -> None:
    fake_service.result = _sample_degree_path_result(paths=(_sample_degree_path_option(status=PathStatus.BLOCKED_BY_CURRENT_IN_PROGRESS),))
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 200
    assert resp.json()["paths"][0]["status"] == "BLOCKED_BY_CURRENT_IN_PROGRESS"


def test_46_no_valid_next_plan_returns_200(client: TestClient, fake_service: FakeStudentService) -> None:
    fake_service.result = _sample_degree_path_result(paths=(_sample_degree_path_option(status=PathStatus.NO_VALID_NEXT_PLAN),))
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 200
    assert resp.json()["paths"][0]["status"] == "NO_VALID_NEXT_PLAN"


# ===========================================================================
# 7. Error Mapping (Tests 47-49)
# ===========================================================================


def test_47_missing_profile_returns_404(client: TestClient, fake_service: FakeStudentService) -> None:
    fake_service.error = StudentProfileNotFound("Student profile was not found")
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "STUDENT_RESOURCE_NOT_FOUND"


def test_48_integrity_error_returns_500(client: TestClient, fake_service: FakeStudentService) -> None:
    fake_service.error = DegreePathIntegrityError("Integrity failure in study plan")
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 500
    assert resp.json()["error_code"] == "CATALOG_INTEGRITY_ERROR"


def test_49_transport_error_returns_503(client: TestClient, fake_service: FakeStudentService) -> None:
    fake_service.error = CatalogTransportError("read", "study_plans")
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "CATALOG_TRANSPORT_ERROR"


# ===========================================================================
# 8. OpenAPI Documentation (Test 50)
# ===========================================================================


def test_50_openapi_documents_degree_paths(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/v1/me/degree-paths" in schema["paths"]
    post_op = schema["paths"]["/api/v1/me/degree-paths"]["post"]
    assert post_op["security"]  # Requires auth

    # Request schema properties check
    req_schema = schema["components"]["schemas"]["DegreePathRequest"]
    expected_props = {
        "max_credit_hours_per_semester",
        "max_courses_per_semester",
        "max_semesters_ahead",
        "max_paths",
    }
    assert set(req_schema["properties"].keys()) == expected_props

    # Forbidden properties definitely not in request schema
    forbidden = {
        "owner",
        "owner_user_id",
        "study_plan_id",
        "attempts",
        "beam_width",
        "semester_branch_width",
        "candidate_window_size",
    }
    for field in forbidden:
        assert field not in req_schema["properties"]

    assert "DegreePathResponse" in schema["components"]["schemas"]


def test_51_zero_semester_modeled_complete(client: TestClient, fake_service: FakeStudentService) -> None:
    opt = _sample_degree_path_option(
        status=PathStatus.MODELED_COMPLETE,
        semesters=(),
        semester_count=0,
        total_planned_courses=0,
        total_planned_credits="0",
        credit_delta="0",
        final_completed="132",
        final_remaining="0",
        reason_codes=(PathReasonCode.REACHES_MODELED_PLAN_COMPLETION,),
    )
    fake_service.result = _sample_degree_path_result(
        paths=(opt,),
        total_parent_states_expanded=0,
    )
    resp = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["paths"]) == 1
    path = data["paths"][0]
    assert path["status"] == "MODELED_COMPLETE"
    assert path["semester_count"] == 0
    assert path["semesters"] == []
    assert "REACHES_MODELED_PLAN_COMPLETION" in path["reason_codes"]
    assert data["total_parent_states_expanded"] == 0


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (DegreePathComputationTimeout("expired"), 504, "DEGREE_PATH_COMPUTATION_TIMEOUT"),
        (DegreePathCapacityError("busy"), 503, "DEGREE_PATH_CAPACITY_BUSY"),
    ],
)
def test_bounded_degree_path_errors_are_safe_and_typed(
    client: TestClient, fake_service: FakeStudentService,
    error: Exception, status: int, code: str,
) -> None:
    fake_service.error = error
    response = client.post("/api/v1/me/degree-paths", json={"max_credit_hours_per_semester": 15})
    assert response.status_code == status
    assert response.json()["error_code"] == code
    assert "expired" not in response.text and "busy" not in response.text

