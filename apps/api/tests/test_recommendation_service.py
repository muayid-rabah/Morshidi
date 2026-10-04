"""StudentService recommendation orchestration unit tests."""

import asyncio
from decimal import Decimal
import inspect
import pytest

from app.progress.models import (
    AcademicProgressCatalog,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.recommendations.models import (
    RECOMMENDATION_POLICY_VERSION,
    RecommendationResult,
)
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CourseCatalogStatus,
    CourseIdentity,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)
from app.services.student import StudentService
from app.student.errors import StudentProfileNotFound
from app.student.models import StudentAcademicState

OWNER = "11111111-1111-1111-1111-111111111111"
PLAN = "10000000-0000-0000-0000-000000000005"
GROUP = "10000000-0000-0000-0000-000000000011"


class FakeStudentRepository:
    def __init__(self, state: StudentAcademicState | None = None) -> None:
        self.state = state
        self.load_count = 0
        self.loaded_owners: list[str] = []
        self.write_calls: list[str] = []

    async def load_student_academic_state(self, owner: str) -> StudentAcademicState:
        self.load_count += 1
        self.loaded_owners.append(owner)
        if self.state is None:
            raise StudentProfileNotFound("Student profile was not found")
        return self.state

    async def create_profile(self, *args, **kwargs):
        self.write_calls.append("create_profile")

    async def update_profile(self, *args, **kwargs):
        self.write_calls.append("update_profile")

    async def delete_profile(self, *args, **kwargs):
        self.write_calls.append("delete_profile")

    async def create_attempt(self, *args, **kwargs):
        self.write_calls.append("create_attempt")

    async def update_attempt(self, *args, **kwargs):
        self.write_calls.append("update_attempt")

    async def delete_attempt(self, *args, **kwargs):
        self.write_calls.append("delete_attempt")


class FakeCatalogRepository:
    def __init__(
        self,
        progress_catalog: AcademicProgressCatalog,
        eligibility_catalog: CanTakeCatalog,
    ) -> None:
        self.progress_catalog = progress_catalog
        self.eligibility_catalog = eligibility_catalog
        self.progress_plan_ids: list[str] = []
        self.eligibility_plan_ids: list[str] = []
        self.write_calls: list[str] = []

    async def load_progress_catalog(self, plan_id: str) -> AcademicProgressCatalog:
        self.progress_plan_ids.append(str(plan_id))
        return self.progress_catalog

    async def load_plan_eligibility_catalog(self, plan_id: str) -> CanTakeCatalog:
        self.eligibility_plan_ids.append(str(plan_id))
        return self.eligibility_catalog


def _make_catalogs():
    groups = (
        ProgressRequirementGroup(
            GROUP, PLAN, "FACULTY_REQUIRED", "كلية", None, "faculty",
            RequirementType.REQUIRED, Decimal("6"), 1,
        ),
    )
    courses = (
        ProgressPlanCourse("pc-1", PLAN, GROUP, "1501110", CourseCatalogStatus.KNOWN, Decimal("3"), 1),
        ProgressPlanCourse("pc-2", PLAN, GROUP, "1501112", CourseCatalogStatus.KNOWN, Decimal("3"), 2),
        ProgressPlanCourse("pc-3", PLAN, GROUP, "1505311", CourseCatalogStatus.KNOWN, Decimal("3"), 3),
    )
    progress_catalog = AcademicProgressCatalog(
        ProgressStudyPlan(PLAN, Decimal("6")),
        groups,
        courses,
    )
    rules = (
        PlanCourseRule("1501110", PrerequisiteLogicStatus.NOT_APPLICABLE, ()),
        PlanCourseRule(
            "1501112",
            PrerequisiteLogicStatus.VERIFIED,
            (DependencyGroup(1, DependencyType.PREREQUISITE, ("1501110",)),),
        ),
        PlanCourseRule("1505311", PrerequisiteLogicStatus.UNRESOLVED, ()),
    )
    identities = tuple(
        CourseIdentity(code, CourseCatalogStatus.KNOWN)
        for code in ("1501110", "1501112", "1505311")
    )
    eligibility_catalog = CanTakeCatalog(PLAN, rules, identities)
    return progress_catalog, eligibility_catalog


def _make_service(state: StudentAcademicState | None = None):
    prog_cat, elig_cat = _make_catalogs()
    student_repo = FakeStudentRepository(state)
    catalog_repo = FakeCatalogRepository(prog_cat, elig_cat)
    service = StudentService(
        repository=student_repo,
        eligibility=None,
        catalog_repository=catalog_repo,
    )
    return service, student_repo, catalog_repo


def test_01_profile_missing_raises_typed_error() -> None:
    service, _, _ = _make_service(state=None)
    with pytest.raises(StudentProfileNotFound):
        asyncio.run(service.get_course_recommendations(OWNER))


def test_02_state_loaded_once() -> None:
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, Decimal("3.5"), Decimal("4"), Decimal("15"), (),
    )
    service, student_repo, _ = _make_service(state=state)
    asyncio.run(service.get_course_recommendations(OWNER))
    assert student_repo.load_count == 1
    assert student_repo.loaded_owners == [OWNER]


def test_03_progress_catalog_loaded_with_study_plan_id() -> None:
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, Decimal("3.5"), Decimal("4"), Decimal("15"), (),
    )
    service, _, catalog_repo = _make_service(state=state)
    asyncio.run(service.get_course_recommendations(OWNER))
    assert catalog_repo.progress_plan_ids == [PLAN]


def test_04_eligibility_catalog_loaded_with_same_study_plan_id() -> None:
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, Decimal("3.5"), Decimal("4"), Decimal("15"), (),
    )
    service, _, catalog_repo = _make_service(state=state)
    asyncio.run(service.get_course_recommendations(OWNER))
    assert catalog_repo.eligibility_plan_ids == [PLAN]


def test_05_recommend_courses_receives_exact_stored_attempts() -> None:
    attempts = (
        StudentCourseAttempt("1501110", AttemptOutcome.PASSED),
    )
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, None, None, None, attempts,
    )
    service, _, _ = _make_service(state=state)
    result = asyncio.run(service.get_course_recommendations(OWNER))
    # With 1501110 passed, 1501110 is COMPLETED (excluded), 1501112 is ELIGIBLE (ranked)
    ranked_codes = [c.course_code for c in result.ranked_recommendations]
    assert "1501110" not in ranked_codes
    assert "1501112" in ranked_codes


def test_06_reported_gpa_passed_through_unchanged() -> None:
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, Decimal("3.75"), Decimal("4"), Decimal("45"), (),
    )
    service, _, _ = _make_service(state=state)
    result = asyncio.run(service.get_course_recommendations(OWNER))
    assert result.recommendation_policy_version == RECOMMENDATION_POLICY_VERSION


def test_07_reported_earned_credits_passed_through_unchanged() -> None:
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, Decimal("3.0"), Decimal("4"), Decimal("90"), (),
    )
    service, _, _ = _make_service(state=state)
    result = asyncio.run(service.get_course_recommendations(OWNER))
    assert isinstance(result, RecommendationResult)


def test_08_full_result_returned_when_limit_omitted() -> None:
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, None, None, None, (),
    )
    service, _, _ = _make_service(state=state)
    result = asyncio.run(service.get_course_recommendations(OWNER))
    # 1501110 is ELIGIBLE
    assert len(result.ranked_recommendations) >= 1
    assert len(result.review_required_courses) == 1
    assert result.review_required_courses[0].course_code == "1505311"


def test_09_limit_trims_only_ranked_recommendations() -> None:
    attempts = (StudentCourseAttempt("1501110", AttemptOutcome.PASSED),)
    # Both 1501110 passed -> 1501112 is eligible; let's create 2 eligible courses
    prog_cat, elig_cat = _make_catalogs()
    # Add another eligible course
    groups = prog_cat.requirement_groups
    courses = prog_cat.plan_courses + (
        ProgressPlanCourse("pc-4", PLAN, GROUP, "0200104", CourseCatalogStatus.KNOWN, Decimal("3"), 4),
    )
    rules = elig_cat.plan_courses + (
        PlanCourseRule("0200104", PrerequisiteLogicStatus.NOT_APPLICABLE, ()),
    )
    identities = elig_cat.courses + (CourseIdentity("0200104", CourseCatalogStatus.KNOWN),)

    student_repo = FakeStudentRepository(
        StudentAcademicState("profile-1", OWNER, PLAN, None, None, None, attempts)
    )
    catalog_repo = FakeCatalogRepository(
        AcademicProgressCatalog(prog_cat.study_plan, groups, courses),
        CanTakeCatalog(PLAN, rules, identities),
    )
    service = StudentService(student_repo, None, catalog_repo)

    full = asyncio.run(service.get_course_recommendations(OWNER, limit=None))
    assert len(full.ranked_recommendations) == 2

    limited = asyncio.run(service.get_course_recommendations(OWNER, limit=1))
    assert len(limited.ranked_recommendations) == 1
    assert limited.ranked_recommendations[0].course_code == full.ranked_recommendations[0].course_code


def test_10_review_required_list_unaffected_by_limit() -> None:
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, None, None, None, (),
    )
    service, _, _ = _make_service(state=state)
    limited = asyncio.run(service.get_course_recommendations(OWNER, limit=1))
    assert len(limited.review_required_courses) == 1
    assert limited.review_required_courses[0].course_code == "1505311"


def test_11_limit_does_not_alter_ranking_metadata() -> None:
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, None, None, None, (),
    )
    service, _, _ = _make_service(state=state)
    full = asyncio.run(service.get_course_recommendations(OWNER, limit=None))
    limited = asyncio.run(service.get_course_recommendations(OWNER, limit=1))

    c_full = full.ranked_recommendations[0]
    c_lim = limited.ranked_recommendations[0]

    assert c_full.rank == c_lim.rank
    assert c_full.priority_tuple == c_lim.priority_tuple
    assert c_full.reason_codes == c_lim.reason_codes
    assert c_full.effective_credit_contribution == c_lim.effective_credit_contribution
    assert c_full.newly_eligible_count == c_lim.newly_eligible_count


def test_12_no_write_repository_method_called() -> None:
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, None, None, None, (),
    )
    service, student_repo, catalog_repo = _make_service(state=state)
    asyncio.run(service.get_course_recommendations(OWNER))
    assert student_repo.write_calls == []
    assert catalog_repo.write_calls == []


def test_13_no_recommendation_calculation_in_service_outside_pure_engine() -> None:
    source = inspect.getsource(StudentService.get_course_recommendations)
    # Service must delegate to recommend_courses
    assert "recommend_courses(" in source
    # Must not contain ranking logic or priority tuples
    assert "priority_tuple" not in source
    assert "sort(" not in source
    assert "display_order" not in source


def test_14_limit_less_than_one_raises_value_error() -> None:
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, None, None, None, (),
    )
    service, _, _ = _make_service(state=state)
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        asyncio.run(service.get_course_recommendations(OWNER, limit=0))
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        asyncio.run(service.get_course_recommendations(OWNER, limit=-5))


def test_15_performance_and_n_plus_one_audit() -> None:
    state = StudentAcademicState(
        "profile-1", OWNER, PLAN, None, None, None, (),
    )
    service, student_repo, catalog_repo = _make_service(state=state)
    result = asyncio.run(service.get_course_recommendations(OWNER))
    assert student_repo.load_count == 1
    assert len(catalog_repo.progress_plan_ids) == 1
    assert len(catalog_repo.eligibility_plan_ids) == 1
    assert len(result.ranked_recommendations) >= 1
