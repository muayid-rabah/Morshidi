"""StudentService semester planner orchestration unit tests (Phase 8.3)."""

from decimal import Decimal
import pytest

from app.planner.models import (
    DEFAULT_CANDIDATE_WINDOW_SIZE,
    PlanReasonCode,
    PlannerConstraintError,
    PlannerConstraints,
    PlannerIntegrityError,
    SemesterPlannerResult,
)
from app.progress.models import (
    AcademicProgressCatalog,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
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
from app.planner.engine import plan_semester
from app.recommendations.engine import recommend_courses
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

    async def resolve_student_university_id(self, owner: str) -> str:
        return "test-institution"

    async def load_attempt_records(self, owner: str) -> tuple:
        return ()

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


def _make_catalogs(plan_id: str = PLAN):
    groups = (
        ProgressRequirementGroup(
            GROUP, plan_id, "FACULTY_REQUIRED", "كلية", None, "faculty",
            RequirementType.REQUIRED, Decimal("12"), 1,
        ),
    )
    courses = (
        ProgressPlanCourse("pc-1", plan_id, GROUP, "1501110", CourseCatalogStatus.KNOWN, Decimal("3"), 1),
        ProgressPlanCourse("pc-2", plan_id, GROUP, "1501112", CourseCatalogStatus.KNOWN, Decimal("3"), 2),
        ProgressPlanCourse("pc-3", plan_id, GROUP, "1501221", CourseCatalogStatus.KNOWN, Decimal("3"), 3),
        ProgressPlanCourse("pc-4", plan_id, GROUP, "1505311", CourseCatalogStatus.KNOWN, Decimal("3"), 4),
    )
    progress_catalog = AcademicProgressCatalog(
        ProgressStudyPlan(plan_id, Decimal("12")),
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
        PlanCourseRule("1501221", PrerequisiteLogicStatus.NOT_APPLICABLE, ()),
        PlanCourseRule("1505311", PrerequisiteLogicStatus.UNRESOLVED, ()),
    )
    identities = tuple(
        CourseIdentity(code, CourseCatalogStatus.KNOWN)
        for code in ("1501110", "1501112", "1501221", "1505311")
    )
    eligibility_catalog = CanTakeCatalog(plan_id, rules, identities)
    return progress_catalog, eligibility_catalog


def _make_state(attempts: tuple[StudentCourseAttempt, ...] = ()) -> StudentAcademicState:
    return StudentAcademicState(
        profile_id="profile-1",
        owner_user_id=OWNER,
        study_plan_id=PLAN,
        reported_cumulative_gpa=None,
        reported_gpa_scale=None,
        reported_earned_credit_hours=None,
        attempts=attempts,
    )


def _make_service(state: StudentAcademicState | None = None, plan_id: str = PLAN):
    prog_cat, elig_cat = _make_catalogs(plan_id)
    student_repo = FakeStudentRepository(state)
    catalog_repo = FakeCatalogRepository(prog_cat, elig_cat)
    service = StudentService(
        repository=student_repo,
        eligibility=None,
        catalog_repository=catalog_repo,
    )
    return service, student_repo, catalog_repo


def test_adaptive_candidate_window_never_admits_ineligible_courses() -> None:
    progress, eligibility = _make_catalogs()
    recs = recommend_courses(progress, eligibility, ())
    eligible = [item.course_code for item in recs.ranked_recommendations]
    assert len(eligible) >= 2
    score = {eligible[1]: 100}
    result = plan_semester(progress, eligibility, (), recs,
                           PlannerConstraints(max_credit_hours=Decimal("15")),
                           candidate_window_size=1, adaptive_scores=score)
    assert result.evaluated_candidate_count == 1
    assert result.plan_options[0].courses[0].course_code == eligible[1]
    with pytest.raises(PlannerIntegrityError):
        plan_semester(progress, eligibility, (), recs,
                      PlannerConstraints(max_credit_hours=Decimal("15")),
                      adaptive_scores={"1505311": 100})


@pytest.mark.anyio
async def test_01_student_state_loaded_once() -> None:
    state = _make_state()
    service, student_repo, _ = _make_service(state=state)
    res = await service.get_semester_plans(OWNER, max_credit_hours=Decimal("15"))
    assert student_repo.load_count == 1
    assert student_repo.loaded_owners == [OWNER]
    assert isinstance(res, SemesterPlannerResult)


@pytest.mark.anyio
async def test_02_progress_catalog_loaded_with_study_plan_id() -> None:
    state = _make_state()
    service, _, catalog_repo = _make_service(state=state)
    await service.get_semester_plans(OWNER, max_credit_hours=Decimal("15"))
    assert catalog_repo.progress_plan_ids == [PLAN]


@pytest.mark.anyio
async def test_03_eligibility_catalog_loaded_with_study_plan_id() -> None:
    state = _make_state()
    service, _, catalog_repo = _make_service(state=state)
    await service.get_semester_plans(OWNER, max_credit_hours=Decimal("15"))
    assert catalog_repo.eligibility_plan_ids == [PLAN]


@pytest.mark.anyio
async def test_04_full_phase7_result_used_before_planner_candidate_window() -> None:
    # Student has 1501110 and 1501221 both eligible
    state = _make_state()
    service, _, _ = _make_service(state=state)
    res = await service.get_semester_plans(OWNER, max_credit_hours=Decimal("15"))
    # Both candidates evaluated
    assert res.eligible_ranked_candidate_count >= 2
    assert res.evaluated_candidate_count >= 2


@pytest.mark.anyio
async def test_05_planner_called_with_stored_attempts() -> None:
    # 1501110 PASSED means 1501112 becomes eligible
    state = _make_state(attempts=(StudentCourseAttempt("1501110", AttemptOutcome.PASSED),))
    service, _, _ = _make_service(state=state)
    res = await service.get_semester_plans(OWNER, max_credit_hours=Decimal("15"))
    planned_codes = {c.course_code for opt in res.plan_options for c in opt.courses}
    assert "1501112" in planned_codes


@pytest.mark.anyio
async def test_06_constraints_pass_request_values_accurately() -> None:
    state = _make_state()
    service, _, _ = _make_service(state=state)
    res = await service.get_semester_plans(
        OWNER,
        max_credit_hours=Decimal("6"),
        max_courses=2,
        max_options=3,
    )
    assert res.constraints.max_credit_hours == Decimal("6")
    assert res.constraints.max_courses == 2
    assert res.constraints.max_options == 3
    assert len(res.plan_options) <= 3


@pytest.mark.anyio
async def test_07_default_candidate_window_size_used() -> None:
    state = _make_state()
    service, _, _ = _make_service(state=state)
    res = await service.get_semester_plans(OWNER, max_credit_hours=Decimal("15"))
    assert res.candidate_window_size == DEFAULT_CANDIDATE_WINDOW_SIZE


@pytest.mark.anyio
async def test_08_no_repository_writes() -> None:
    state = _make_state()
    service, student_repo, catalog_repo = _make_service(state=state)
    await service.get_semester_plans(OWNER, max_credit_hours=Decimal("15"))
    assert student_repo.write_calls == []
    assert catalog_repo.write_calls == []


@pytest.mark.anyio
async def test_09_profile_missing_propagates_not_found() -> None:
    service, _, _ = _make_service(state=None)
    with pytest.raises(StudentProfileNotFound):
        await service.get_semester_plans(OWNER, max_credit_hours=Decimal("15"))


@pytest.mark.anyio
async def test_10_invalid_constraints_raise_constraint_error() -> None:
    state = _make_state()
    service, _, _ = _make_service(state=state)
    with pytest.raises(PlannerConstraintError, match="cannot be negative"):
        await service.get_semester_plans(OWNER, max_credit_hours=Decimal("-5"))


@pytest.mark.anyio
async def test_11_plan_id_mismatch_raises_integrity_error() -> None:
    state = _make_state()
    prog_cat, _ = _make_catalogs(PLAN)
    _, elig_cat = _make_catalogs("DIFFERENT_PLAN_ID")
    student_repo = FakeStudentRepository(state)
    catalog_repo = FakeCatalogRepository(prog_cat, elig_cat)
    service = StudentService(student_repo, None, catalog_repo)

    with pytest.raises(PlannerIntegrityError):
        await service.get_semester_plans(OWNER, max_credit_hours=Decimal("15"))


@pytest.mark.anyio
async def test_planner_cpu_is_offloaded_and_shares_capacity() -> None:
    import asyncio
    from threading import Event
    from time import perf_counter
    from unittest.mock import patch

    from app.degree_path.models import DegreePathCapacityError
    from app.planner.engine import plan_semester as real_plan_semester

    service, _, _ = _make_service(state=_make_state())
    entered = Event()
    release = Event()

    def slow_plan(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return real_plan_semester(*args, **kwargs)

    with patch("app.services.student.plan_semester", side_effect=slow_plan):
        first = asyncio.create_task(service.get_semester_plans(
            OWNER, max_credit_hours=Decimal("15"),
        ))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            started = perf_counter()
            await asyncio.wait_for(asyncio.sleep(0.01), 0.5)
            assert perf_counter() - started < 0.5
            with pytest.raises(DegreePathCapacityError):
                await service.get_semester_plans(OWNER, max_credit_hours=Decimal("15"))
        finally:
            release.set()
        assert isinstance(await first, SemesterPlannerResult)

