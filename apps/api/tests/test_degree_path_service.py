"""StudentService degree path planner orchestration unit tests (Phase 9.3)."""

import asyncio
from decimal import Decimal
from threading import Event
from time import sleep
from unittest.mock import patch
import pytest

from app.degree_path.models import (
    DEFAULT_BEAM_WIDTH,
    DEFAULT_SEMESTER_BRANCH_WIDTH,
    DegreePathConstraintError,
    DegreePathCapacityError,
    DegreePathComputationTimeout,
    DegreePathConstraints,
    DegreePathIntegrityError,
    DegreePathResult,
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


def _make_catalogs(plan_id: str = PLAN):
    groups = (
        ProgressRequirementGroup(
            GROUP, plan_id, "FACULTY_REQUIRED", "كلية", None, "faculty",
            RequirementType.REQUIRED, Decimal("12"), 1,
        ),
    )
    plan_courses = (
        ProgressPlanCourse(
            "pc-1", plan_id, GROUP, "0300153", CourseCatalogStatus.KNOWN,
            Decimal("3"), 1,
        ),
        ProgressPlanCourse(
            "pc-2", plan_id, GROUP, "1501110", CourseCatalogStatus.KNOWN,
            Decimal("3"), 2,
        ),
    )
    study_plan = ProgressStudyPlan(plan_id, Decimal("6"))
    progress_catalog = AcademicProgressCatalog(study_plan, groups, plan_courses)

    courses = (
        CourseIdentity("0300153", CourseCatalogStatus.KNOWN),
        CourseIdentity("1501110", CourseCatalogStatus.KNOWN),
    )
    rules = (
        PlanCourseRule("0300153", PrerequisiteLogicStatus.NOT_APPLICABLE, ()),
        PlanCourseRule(
            "1501110", PrerequisiteLogicStatus.VERIFIED,
            (DependencyGroup(1, DependencyType.PREREQUISITE, ("0300153",)),),
        ),
    )
    eligibility_catalog = CanTakeCatalog(plan_id, rules, courses)
    return progress_catalog, eligibility_catalog


def _make_state(
    attempts: tuple[StudentCourseAttempt, ...] = (),
    plan_id: str = PLAN,
) -> StudentAcademicState:
    return StudentAcademicState(
        profile_id="22222222-2222-2222-2222-222222222222",
        owner_user_id=OWNER,
        study_plan_id=plan_id,
        reported_cumulative_gpa=None,
        reported_gpa_scale=None,
        reported_earned_credit_hours=None,
        attempts=attempts,
    )


# ===========================================================================
# Unit Tests
# ===========================================================================


@pytest.mark.anyio
async def test_01_student_state_loaded_once() -> None:
    p_cat, e_cat = _make_catalogs()
    student_repo = FakeStudentRepository(_make_state())
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    await service.get_degree_paths(
        OWNER,
        max_credit_hours_per_semester=Decimal("15"),
    )

    assert student_repo.load_count == 1
    assert student_repo.loaded_owners == [OWNER]


@pytest.mark.anyio
async def test_02_progress_catalog_loaded_once() -> None:
    p_cat, e_cat = _make_catalogs()
    student_repo = FakeStudentRepository(_make_state())
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    await service.get_degree_paths(
        OWNER,
        max_credit_hours_per_semester=Decimal("15"),
    )

    assert len(catalog_repo.progress_plan_ids) == 1
    assert catalog_repo.progress_plan_ids == [PLAN]


@pytest.mark.anyio
async def test_03_eligibility_catalog_loaded_once() -> None:
    p_cat, e_cat = _make_catalogs()
    student_repo = FakeStudentRepository(_make_state())
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    await service.get_degree_paths(
        OWNER,
        max_credit_hours_per_semester=Decimal("15"),
    )

    assert len(catalog_repo.eligibility_plan_ids) == 1
    assert catalog_repo.eligibility_plan_ids == [PLAN]


@pytest.mark.anyio
async def test_04_both_catalogs_use_state_study_plan_id() -> None:
    custom_plan = "99999999-9999-9999-9999-999999999999"
    p_cat, e_cat = _make_catalogs(custom_plan)
    student_repo = FakeStudentRepository(_make_state(plan_id=custom_plan))
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    await service.get_degree_paths(
        OWNER,
        max_credit_hours_per_semester=Decimal("15"),
    )

    assert catalog_repo.progress_plan_ids == [custom_plan]
    assert catalog_repo.eligibility_plan_ids == [custom_plan]


@pytest.mark.anyio
async def test_05_constraints_pass_request_values_accurately() -> None:
    p_cat, e_cat = _make_catalogs()
    student_repo = FakeStudentRepository(_make_state())
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    with patch("app.services.student.plan_degree_paths") as mock_plan:
        mock_plan.return_value = "mock_result"
        await service.get_degree_paths(
            OWNER,
            max_credit_hours_per_semester=Decimal("18"),
            max_courses_per_semester=5,
            max_semesters_ahead=6,
            max_paths=2,
        )

        assert mock_plan.call_count == 1
        _, kwargs = mock_plan.call_args
        # Constraints argument is 4th positional
        args, _ = mock_plan.call_args
        constraints = args[3]
        assert isinstance(constraints, DegreePathConstraints)
        assert constraints.max_credit_hours_per_semester == Decimal("18")
        assert constraints.max_courses_per_semester == 5
        assert constraints.max_semesters_ahead == 6
        assert constraints.max_paths == 2


@pytest.mark.anyio
async def test_06_plan_degree_paths_called_with_stored_attempts() -> None:
    p_cat, e_cat = _make_catalogs()
    attempts = (
        StudentCourseAttempt("0300153", AttemptOutcome.PASSED),
    )
    student_repo = FakeStudentRepository(_make_state(attempts=attempts))
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    with patch("app.services.student.plan_degree_paths") as mock_plan:
        mock_plan.return_value = "mock_result"
        await service.get_degree_paths(
            OWNER,
            max_credit_hours_per_semester=Decimal("15"),
        )

        args, _ = mock_plan.call_args
        # args[2] is student_attempts
        assert args[2] == attempts


@pytest.mark.anyio
async def test_07_plan_degree_paths_called_with_exact_catalogs() -> None:
    p_cat, e_cat = _make_catalogs()
    student_repo = FakeStudentRepository(_make_state())
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    with patch("app.services.student.plan_degree_paths") as mock_plan:
        mock_plan.return_value = "mock_result"
        await service.get_degree_paths(
            OWNER,
            max_credit_hours_per_semester=Decimal("15"),
        )

        args, _ = mock_plan.call_args
        assert args[0] is p_cat
        assert args[1] is e_cat


@pytest.mark.anyio
async def test_08_result_returned_unchanged() -> None:
    p_cat, e_cat = _make_catalogs()
    student_repo = FakeStudentRepository(_make_state())
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    result = await service.get_degree_paths(
        OWNER,
        max_credit_hours_per_semester=Decimal("15"),
    )

    assert isinstance(result, DegreePathResult)
    assert result.study_plan_id == PLAN
    assert result.degree_path_policy_version == "1.0"
    assert result.planning_scope == "MODELED_DEGREE_PATH_ONLY"


@pytest.mark.anyio
async def test_09_beam_and_branch_width_not_client_derived() -> None:
    """Service invokes plan_degree_paths using pure engine default beam and branch width."""
    p_cat, e_cat = _make_catalogs()
    student_repo = FakeStudentRepository(_make_state())
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    with patch("app.services.student.plan_degree_paths") as mock_plan:
        mock_plan.return_value = "mock_result"
        await service.get_degree_paths(
            OWNER,
            max_credit_hours_per_semester=Decimal("15"),
        )

        _, kwargs = mock_plan.call_args
        # beam_width and semester_branch_width are not passed as custom overrides by service
        assert "beam_width" not in kwargs
        assert "semester_branch_width" not in kwargs


@pytest.mark.anyio
async def test_10_no_database_writes() -> None:
    p_cat, e_cat = _make_catalogs()
    student_repo = FakeStudentRepository(_make_state())
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    await service.get_degree_paths(
        OWNER,
        max_credit_hours_per_semester=Decimal("15"),
    )

    assert student_repo.write_calls == []
    assert catalog_repo.write_calls == []


@pytest.mark.anyio
async def test_11_missing_profile_propagates() -> None:
    p_cat, e_cat = _make_catalogs()
    student_repo = FakeStudentRepository(None)
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    with pytest.raises(StudentProfileNotFound):
        await service.get_degree_paths(
            OWNER,
            max_credit_hours_per_semester=Decimal("15"),
        )


@pytest.mark.anyio
async def test_12_invalid_constraints_raise_constraint_error() -> None:
    p_cat, e_cat = _make_catalogs()
    student_repo = FakeStudentRepository(_make_state())
    catalog_repo = FakeCatalogRepository(p_cat, e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    with pytest.raises(DegreePathConstraintError):
        await service.get_degree_paths(
            OWNER,
            max_credit_hours_per_semester=Decimal("-5"),
        )


@pytest.mark.anyio
async def test_13_plan_id_mismatch_raises_integrity_error() -> None:
    p_cat, _ = _make_catalogs(PLAN)
    _, mismatched_e_cat = _make_catalogs("10000000-0000-0000-0000-000000000099")
    student_repo = FakeStudentRepository(_make_state(plan_id=PLAN))
    catalog_repo = FakeCatalogRepository(p_cat, mismatched_e_cat)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    with pytest.raises(DegreePathIntegrityError):
        await service.get_degree_paths(
            OWNER,
            max_credit_hours_per_semester=Decimal("15"),
        )


@pytest.mark.anyio
async def test_14_zero_semester_modeled_complete_service() -> None:
    # Catalog with 1 course and 1 required group of 3 credits
    groups = (
        ProgressRequirementGroup(
            GROUP, PLAN, "FACULTY_REQUIRED", "كلية", None, "faculty",
            RequirementType.REQUIRED, Decimal("3"), 1,
        ),
    )
    plan_courses = (
        ProgressPlanCourse(
            "pc-1", PLAN, GROUP, "0300153", CourseCatalogStatus.KNOWN,
            Decimal("3"), 1,
        ),
    )
    study_plan = ProgressStudyPlan(PLAN, Decimal("3"))
    progress_catalog = AcademicProgressCatalog(study_plan, groups, plan_courses)

    courses = (CourseIdentity("0300153", CourseCatalogStatus.KNOWN),)
    rules = (PlanCourseRule("0300153", PrerequisiteLogicStatus.NOT_APPLICABLE, ()),)
    eligibility_catalog = CanTakeCatalog(PLAN, rules, courses)

    # Student has already completed 0300153
    attempts = (StudentCourseAttempt("0300153", AttemptOutcome.PASSED),)
    student_repo = FakeStudentRepository(_make_state(attempts=attempts))
    catalog_repo = FakeCatalogRepository(progress_catalog, eligibility_catalog)
    service = StudentService(student_repo, None, catalog_repo)  # type: ignore[arg-type]

    res = await service.get_degree_paths(
        OWNER,
        max_credit_hours_per_semester=Decimal("15"),
    )
    assert len(res.paths) == 1
    path = res.paths[0]
    assert path.status.value == "MODELED_COMPLETE"
    assert path.semester_count == 0
    assert path.semesters == ()
    assert any(rc.value == "REACHES_MODELED_PLAN_COMPLETION" for rc in path.reason_codes)
    assert res.total_parent_states_expanded == 0


@pytest.mark.anyio
async def test_degree_path_worker_does_not_block_event_loop_and_limits_overlap() -> None:
    p_cat, e_cat = _make_catalogs()
    service = StudentService(
        FakeStudentRepository(_make_state()), None, FakeCatalogRepository(p_cat, e_cat)
    )  # type: ignore[arg-type]
    entered = Event()
    release = Event()

    def slow_plan(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return "result"

    with patch("app.services.student.plan_degree_paths", side_effect=slow_plan):
        first = asyncio.create_task(service.get_degree_paths(OWNER, max_credit_hours_per_semester=Decimal("15")))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            await asyncio.wait_for(asyncio.sleep(0.01), 0.5)
            with pytest.raises(DegreePathCapacityError):
                await service.get_degree_paths(OWNER, max_credit_hours_per_semester=Decimal("15"))
        finally:
            release.set()
        assert await first == "result"


@pytest.mark.anyio
async def test_degree_path_deadline_stops_worker_and_releases_capacity() -> None:
    p_cat, e_cat = _make_catalogs()
    service = StudentService(
        FakeStudentRepository(_make_state()), None, FakeCatalogRepository(p_cat, e_cat)
    )  # type: ignore[arg-type]
    entered = Event()

    def cooperative_plan(*args, **kwargs):
        entered.set()
        while True:
            kwargs["check_budget"]()
            sleep(0.001)

    with patch("app.services.student.DEGREE_PATH_BUDGET_SECONDS", 0.05), patch(
        "app.services.student.plan_degree_paths", side_effect=cooperative_plan
    ):
        with pytest.raises(DegreePathComputationTimeout):
            await service.get_degree_paths(OWNER, max_credit_hours_per_semester=Decimal("15"))
        assert entered.is_set()
        for _ in range(100):
            if service._academic_compute_limiter.in_use == 0:
                break
            await asyncio.sleep(0.005)
        assert service._academic_compute_limiter.in_use == 0
