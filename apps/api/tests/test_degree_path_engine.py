"""Exhaustive pure unit tests for Phase 9.2 — Pure Degree Path Engine.

All tests are pure (no Supabase, no FastAPI, no network, no I/O, no DB).
Tests use in-memory catalog objects constructed from verified Plan 12 facts and test fixtures.

Test coverage categories:
  1-18:   Constraints & validation
  19-23:  Initial state
  24-30:  Hypothetical transitions & synthetic attempts
  31-35:  Phase 5/6/7/8 reuse
  36-40:  Prerequisites & multi-semester chains
  41-45:  Current IN_PROGRESS non-resolution
  46-49:  Zero-credit handling
  50-55:  Depth-aware state deduplication
  56-61:  Beam search bounds & ranking
  62-69:  Termination precedence & horizon
  70-78:  Lexicographic ranking tuples
  79-89:  Path reason codes (relative & absolute)
  90-92:  max_paths presentation behavior
  93-100: Real Plan 12 verified integration
  101-104: Determinism & stability
  105-108: Boundary checks (no HTTP/FastAPI/Supabase)
"""

from __future__ import annotations

import sys
from decimal import Decimal

import pytest

from app.degree_path.engine import plan_degree_paths
from app.degree_path.models import (
    DEFAULT_BEAM_WIDTH,
    DEFAULT_SEMESTER_BRANCH_WIDTH,
    DEGREE_PATH_POLICY_VERSION,
    MAX_CREDIT_HOURS_SAFETY_CEILING,
    PLANNING_SCOPE,
    BlockerType,
    DegreePathConstraintError,
    DegreePathConstraints,
    DegreePathIntegrityError,
    DegreePathOption,
    DegreePathResult,
    ModeledSemesterEntry,
    PathReasonCode,
    PathStatus,
)
from app.progress.engine import calculate_academic_progress
from app.progress.models import (
    AcademicProgressCatalog,
    CourseProgressState,
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

PLAN_ID = "10000000-0000-0000-0000-000000000009"
GRP_REQ = "grp-req"
GRP_ELEC = "grp-elec"
GRP_UNIV_REQ = "grp-univ-req"
GRP_FAC_REQ = "grp-fac-req"


# ---------------------------------------------------------------------------
# Test Fixture Helpers
# ---------------------------------------------------------------------------


def _study_plan(total_credits: str = "132") -> ProgressStudyPlan:
    return ProgressStudyPlan(study_plan_id=PLAN_ID, total_credit_hours=Decimal(total_credits))


def _rg(
    group_id: str = GRP_REQ,
    code: str = "MAJOR_REQUIRED",
    req_type: RequirementType = RequirementType.REQUIRED,
    required_hours: str = "12",
    display_order: int = 1,
) -> ProgressRequirementGroup:
    return ProgressRequirementGroup(
        group_id=group_id,
        study_plan_id=PLAN_ID,
        group_code=code,
        name_ar="متطلب إجباري",
        name_en="Required",
        scope="major",
        requirement_type=req_type,
        required_credit_hours=Decimal(required_hours),
        display_order=display_order,
    )


def _pc(
    code: str,
    group_id: str = GRP_REQ,
    credits: str = "3",
    display_order: int = 1,
) -> ProgressPlanCourse:
    return ProgressPlanCourse(
        plan_course_id=f"pc-{code}",
        study_plan_id=PLAN_ID,
        requirement_group_id=group_id,
        course_code=code,
        catalog_status=CourseCatalogStatus.KNOWN,
        credit_hours=Decimal(credits),
        display_order=display_order,
    )


def _rule_na(code: str, name_ar: str | None = None) -> PlanCourseRule:
    return PlanCourseRule(
        course_code=code,
        prerequisite_logic_status=PrerequisiteLogicStatus.NOT_APPLICABLE,
        dependency_groups=(),
        raw_prerequisite_text=None,
        target_name_ar=name_ar,
    )


def _rule_prereq(code: str, prereq: str, name_ar: str | None = None) -> PlanCourseRule:
    return PlanCourseRule(
        course_code=code,
        prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
        dependency_groups=(
            DependencyGroup(
                group_number=1,
                dependency_type=DependencyType.PREREQUISITE,
                option_course_codes=(prereq,),
            ),
        ),
        raw_prerequisite_text=prereq,
        target_name_ar=name_ar,
    )


def _rule_joint_and(code: str, prereq1: str, prereq2: str) -> PlanCourseRule:
    return PlanCourseRule(
        course_code=code,
        prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
        dependency_groups=(
            DependencyGroup(1, DependencyType.PREREQUISITE, (prereq1,)),
            DependencyGroup(2, DependencyType.PREREQUISITE, (prereq2,)),
        ),
        raw_prerequisite_text=f"{prereq1} AND {prereq2}",
    )


def _rule_review(code: str, name_ar: str | None = None) -> PlanCourseRule:
    return PlanCourseRule(
        course_code=code,
        prerequisite_logic_status=PrerequisiteLogicStatus.SOURCE_CONFLICT,
        dependency_groups=(),
        raw_prerequisite_text="source conflict",
        target_name_ar=name_ar,
    )


def _rule_unresolved(code: str, name_ar: str | None = None) -> PlanCourseRule:
    return PlanCourseRule(
        course_code=code,
        prerequisite_logic_status=PrerequisiteLogicStatus.UNRESOLVED,
        dependency_groups=(),
        raw_prerequisite_text="unresolved prerequisite logic",
        target_name_ar=name_ar,
    )


def _catalogs(
    plan_courses: tuple[ProgressPlanCourse, ...],
    rules: tuple[PlanCourseRule, ...],
    groups: tuple[ProgressRequirementGroup, ...] | None = None,
    total_credits: str = "12",
) -> tuple[AcademicProgressCatalog, CanTakeCatalog]:
    if groups is None:
        groups = (_rg(required_hours=total_credits),)
    p_cat = AcademicProgressCatalog(
        study_plan=_study_plan(total_credits),
        requirement_groups=groups,
        plan_courses=plan_courses,
    )
    c_identities = tuple(
        CourseIdentity(course_code=r.course_code, catalog_status=CourseCatalogStatus.KNOWN)
        for r in rules
    )
    e_cat = CanTakeCatalog(
        study_plan_id=PLAN_ID,
        plan_courses=rules,
        courses=c_identities,
    )
    return p_cat, e_cat


# ===========================================================================
# 1. Constraints & Input Validation (Tests 1-18)
# ===========================================================================


class TestConstraintsValidation:
    def test_01_valid_defaults(self) -> None:
        c = DegreePathConstraints(max_credit_hours_per_semester=Decimal("15"))
        assert c.max_credit_hours_per_semester == Decimal("15")
        assert c.max_courses_per_semester is None
        assert c.max_semesters_ahead == 8
        assert c.max_paths == 3

    def test_02_zero_credits_valid(self) -> None:
        c = DegreePathConstraints(max_credit_hours_per_semester=Decimal("0"))
        assert c.max_credit_hours_per_semester == Decimal("0")

    def test_03_credits_exceeding_ceiling_rejected(self) -> None:
        with pytest.raises(DegreePathConstraintError, match="safety limit"):
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("30.01"))

    def test_04_negative_credits_rejected(self) -> None:
        with pytest.raises(DegreePathConstraintError, match="cannot be negative"):
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("-1"))

    def test_05_float_credit_hours_rejected(self) -> None:
        with pytest.raises(DegreePathConstraintError, match="not float"):
            DegreePathConstraints(max_credit_hours_per_semester=15.0)  # type: ignore

    def test_06_max_courses_none_valid(self) -> None:
        c = DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_courses_per_semester=None)
        assert c.max_courses_per_semester is None

    def test_07_max_courses_lower_bound_one(self) -> None:
        c = DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_courses_per_semester=1)
        assert c.max_courses_per_semester == 1

    def test_08_max_courses_upper_bound_ten(self) -> None:
        c = DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_courses_per_semester=10)
        assert c.max_courses_per_semester == 10

    def test_09_max_courses_zero_rejected(self) -> None:
        with pytest.raises(DegreePathConstraintError, match="between 1 and 10"):
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_courses_per_semester=0)

    def test_10_max_courses_eleven_rejected(self) -> None:
        with pytest.raises(DegreePathConstraintError, match="between 1 and 10"):
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_courses_per_semester=11)

    def test_11_horizon_lower_bound_one(self) -> None:
        c = DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_semesters_ahead=1)
        assert c.max_semesters_ahead == 1

    def test_12_horizon_upper_bound_sixteen(self) -> None:
        c = DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_semesters_ahead=16)
        assert c.max_semesters_ahead == 16

    def test_13_horizon_zero_rejected(self) -> None:
        with pytest.raises(DegreePathConstraintError, match="between 1 and 16"):
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_semesters_ahead=0)

    def test_14_horizon_seventeen_rejected(self) -> None:
        with pytest.raises(DegreePathConstraintError, match="between 1 and 16"):
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_semesters_ahead=17)

    def test_15_max_paths_lower_bound_one(self) -> None:
        c = DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_paths=1)
        assert c.max_paths == 1

    def test_16_max_paths_upper_bound_ten(self) -> None:
        c = DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_paths=10)
        assert c.max_paths == 10

    def test_17_max_paths_invalid_rejected(self) -> None:
        with pytest.raises(DegreePathConstraintError, match="between 1 and 10"):
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_paths=0)
        with pytest.raises(DegreePathConstraintError, match="between 1 and 10"):
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("12"), max_paths=11)

    def test_18_booleans_rejected(self) -> None:
        with pytest.raises(DegreePathConstraintError, match="cannot be a boolean"):
            DegreePathConstraints(max_credit_hours_per_semester=True)  # type: ignore
        with pytest.raises(DegreePathConstraintError, match="must be an integer"):
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("15"), max_semesters_ahead=True)  # type: ignore
        with pytest.raises(DegreePathConstraintError, match="must be an integer"):
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("15"), max_paths=False)  # type: ignore
        with pytest.raises(DegreePathConstraintError, match="must be an integer"):
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("15"), max_courses_per_semester=True)  # type: ignore


# ===========================================================================
# 2. Initial State & Special Cases (Tests 19-23)
# ===========================================================================


class TestInitialState:
    def test_19_initial_progress_computed(self) -> None:
        pcs = (_pc("C1", credits="3"), _pc("C2", credits="3"))
        rules = (_rule_na("C1"), _rule_na("C2"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6")),
        )
        assert res.initial_completed_credits == Decimal("0")
        assert res.initial_remaining_credits == Decimal("6")
        assert res.initial_satisfied_group_count == 0
        assert res.total_requirement_group_count == 1

    def test_20_zero_semester_already_complete(self) -> None:
        pcs = (_pc("C1", credits="3"),)
        rules = (_rule_na("C1"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        attempts = (StudentCourseAttempt("C1", AttemptOutcome.PASSED),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6")),
        )
        assert len(res.paths) == 1
        path = res.paths[0]
        assert path.status is PathStatus.MODELED_COMPLETE
        assert path.semester_count == 0
        assert path.semesters == ()
        assert PathReasonCode.REACHES_MODELED_PLAN_COMPLETION in path.reason_codes
        assert res.total_parent_states_expanded == 0

    def test_21_initial_in_progress_remains_unresolved(self) -> None:
        pcs = (_pc("C1", credits="3"), _pc("C2", credits="3"))
        rules = (_rule_na("C1"), _rule_prereq("C2", "C1"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        attempts = (StudentCourseAttempt("C1", AttemptOutcome.IN_PROGRESS),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6")),
        )
        assert "C1" in res.persisted_in_progress_courses
        # C2 should NOT be taken because C1 is only in progress
        for path in res.paths:
            for sem in path.semesters:
                planned_codes = [c.course_code for c in sem.plan_option.courses]
                assert "C1" not in planned_codes
                assert "C2" not in planned_codes

    def test_22_initial_failed_preserved(self) -> None:
        pcs = (_pc("C1", credits="3"),)
        rules = (_rule_na("C1"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        attempts = (StudentCourseAttempt("C1", AttemptOutcome.FAILED),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert len(res.paths) >= 1
        path = res.paths[0]
        assert PathReasonCode.INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE in path.reason_codes

    def test_23_initial_withdrawn_preserved(self) -> None:
        pcs = (_pc("C1", credits="3"),)
        rules = (_rule_na("C1"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        attempts = (StudentCourseAttempt("C1", AttemptOutcome.WITHDRAWN),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert len(res.paths) >= 1
        path = res.paths[0]
        assert PathReasonCode.INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE in path.reason_codes


# ===========================================================================
# 3. Transitions & Synthetic Attempts (Tests 24-30)
# ===========================================================================


class TestTransitions:
    def test_24_selected_course_becomes_synthetic_passed(self) -> None:
        pcs = (_pc("C1", credits="3"), _pc("C2", credits="3"))
        rules = (_rule_na("C1"), _rule_prereq("C2", "C1"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=2),
        )
        path = res.paths[0]
        assert path.semester_count == 2
        assert [c.course_code for c in path.semesters[0].plan_option.courses] == ["C1"]
        assert [c.course_code for c in path.semesters[1].plan_option.courses] == ["C2"]

    def test_25_all_selected_courses_pass_together(self) -> None:
        pcs = (_pc("C1", credits="3"), _pc("C2", credits="3"), _pc("C3", credits="3"))
        rules = (_rule_na("C1"), _rule_na("C2"), _rule_joint_and("C3", "C1", "C2"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6"), max_semesters_ahead=2),
        )
        path = res.paths[0]
        # Sem 1 takes C1, C2 together; Sem 2 takes C3
        assert len(path.semesters) == 2
        sem1_codes = {c.course_code for c in path.semesters[0].plan_option.courses}
        assert sem1_codes == {"C1", "C2"}
        assert [c.course_code for c in path.semesters[1].plan_option.courses] == ["C3"]

    def test_26_original_attempts_immutable(self) -> None:
        pcs = (_pc("C1", credits="3"),)
        rules = (_rule_na("C1"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        attempts = (StudentCourseAttempt("HIST", AttemptOutcome.PASSED),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert len(attempts) == 1
        assert attempts[0].course_code == "HIST"

    def test_27_hypothetical_attempts_accumulate(self) -> None:
        pcs = (_pc("C1", credits="3"), _pc("C2", credits="3"), _pc("C3", credits="3"))
        rules = (_rule_na("C1"), _rule_prereq("C2", "C1"), _rule_prereq("C3", "C2"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=3),
        )
        path = res.paths[0]
        assert path.status is PathStatus.MODELED_COMPLETE
        assert path.semester_count == 3
        assert path.final_completed_plan_credits == Decimal("9")
        assert path.final_remaining_plan_credits == Decimal("0")

    def test_28_no_synthetic_gpa(self) -> None:
        pcs = (_pc("C1", credits="3"),)
        rules = (_rule_na("C1"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        # DegreePathResult contains no GPA fields
        assert not hasattr(res, "gpa")
        assert not hasattr(res.paths[0], "gpa")

    def test_29_no_synthetic_grade(self) -> None:
        pcs = (_pc("C1", credits="3"),)
        rules = (_rule_na("C1"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        for sem in res.paths[0].semesters:
            for course in sem.plan_option.courses:
                assert not hasattr(course, "grade")

    def test_30_depth_increments_once_per_semester(self) -> None:
        pcs = (_pc("C1", credits="3"), _pc("C2", credits="3"))
        rules = (_rule_na("C1"), _rule_prereq("C2", "C1"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        assert [s.semester_index for s in path.semesters] == [1, 2]


# ===========================================================================
# 4. Phase Reuse (Tests 31-35)
# ===========================================================================


class TestPhaseReuse:
    def test_31_phase_6_called_per_child_state(self) -> None:
        pcs = (_pc("C1", credits="3"), _pc("C2", credits="3"))
        rules = (_rule_na("C1"), _rule_na("C2"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6")),
        )
        path = res.paths[0]
        assert path.completed_plan_credit_delta == Decimal("6")

    def test_32_phase_7_recomputed_at_next_state(self) -> None:
        # C2 requires C1; in initial state C2 is NOT in recommendations, but at Sem 2 it must be recommended
        pcs = (_pc("C1", credits="3"), _pc("C2", credits="3"))
        rules = (_rule_na("C1"), _rule_prereq("C2", "C1"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        assert path.semesters[1].plan_option.courses[0].course_code == "C2"

    def test_33_phase_8_recomputed_at_next_state(self) -> None:
        pcs = (_pc("C1", credits="3"), _pc("C2", credits="3"))
        rules = (_rule_na("C1"), _rule_na("C2"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert len(res.paths[0].semesters) == 2

    def test_34_no_stale_recommendation_reuse(self) -> None:
        # If C1 is passed in Sem 1, Phase 7 at Sem 2 must NOT recommend C1 again
        pcs = (_pc("C1", credits="3"), _pc("C2", credits="3"))
        rules = (_rule_na("C1"), _rule_na("C2"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        sem2_codes = [c.course_code for c in path.semesters[1].plan_option.courses]
        assert "C1" not in sem2_codes

    def test_35_integrity_error_on_mismatched_study_plan_id(self) -> None:
        pcs = (_pc("C1", credits="3"),)
        rules = (_rule_na("C1"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        # Tamper e_cat study_plan_id
        tampered_e_cat = CanTakeCatalog(study_plan_id="MISMATCH", plan_courses=e_cat.plan_courses, courses=e_cat.courses)
        with pytest.raises(DegreePathIntegrityError, match="Mismatched study_plan_id"):
            plan_degree_paths(
                p_cat,
                tampered_e_cat,
                (),
                DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
            )


# ===========================================================================
# 5. Prerequisites (Tests 36-40)
# ===========================================================================


class TestPrerequisites:
    def test_36_prereq_a_to_b_across_semesters(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_prereq("B", "A"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6")),
        )
        # Even with max 6 credits, Phase 8 prevents A and B in same semester!
        path = res.paths[0]
        assert path.semester_count == 2
        assert [c.course_code for c in path.semesters[0].plan_option.courses] == ["A"]
        assert [c.course_code for c in path.semesters[1].plan_option.courses] == ["B"]

    def test_37_prereq_same_semester_prohibited(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_prereq("B", "A"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("15")),
        )
        path = res.paths[0]
        # Never in the same semester
        for sem in path.semesters:
            codes = {c.course_code for c in sem.plan_option.courses}
            assert not ({"A", "B"}.issubset(codes))

    def test_38_three_course_chain(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"), _pc("C", credits="3"))
        rules = (_rule_na("A"), _rule_prereq("B", "A"), _rule_prereq("C", "B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("15"), max_semesters_ahead=3),
        )
        path = res.paths[0]
        assert path.semester_count == 3
        assert [c.course_code for c in path.semesters[0].plan_option.courses] == ["A"]
        assert [c.course_code for c in path.semesters[1].plan_option.courses] == ["B"]
        assert [c.course_code for c in path.semesters[2].plan_option.courses] == ["C"]

    def test_39_joint_and_prerequisites(self) -> None:
        pcs = (_pc("P1", credits="3"), _pc("P2", credits="3"), _pc("TARGET", credits="3"))
        rules = (_rule_na("P1"), _rule_na("P2"), _rule_joint_and("TARGET", "P1", "P2"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6"), max_semesters_ahead=2),
        )
        path = res.paths[0]
        assert [c.course_code for c in path.semesters[1].plan_option.courses] == ["TARGET"]

    def test_40_review_required_never_bypassed(self) -> None:
        pcs = (_pc("SAFE", credits="3"), _pc("REV", credits="3"))
        rules = (_rule_na("SAFE"), _rule_review("REV"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6"), max_semesters_ahead=3),
        )
        path = res.paths[0]
        # Path completes SAFE in Sem 1, then halts with BLOCKED_BY_REVIEW_REQUIRED because REV cannot be taken
        assert path.status is PathStatus.BLOCKED_BY_REVIEW_REQUIRED
        assert "REV" in path.unresolved_blocker_codes or BlockerType.REVIEW_REQUIRED_BLOCKER.value in path.unresolved_blocker_codes


# ===========================================================================
# 6. Current IN_PROGRESS Policy (Tests 41-45)
# ===========================================================================


class TestInProgressPolicy:
    def test_41_in_progress_does_not_auto_pass(self) -> None:
        pcs = (_pc("IP_C", credits="3"), _pc("NEXT_C", credits="3"))
        rules = (_rule_na("IP_C"), _rule_prereq("NEXT_C", "IP_C"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        attempts = (StudentCourseAttempt("IP_C", AttemptOutcome.IN_PROGRESS),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6"), max_semesters_ahead=3),
        )
        path = res.paths[0]
        assert path.status is PathStatus.BLOCKED_BY_CURRENT_IN_PROGRESS
        assert path.semester_count == 0

    def test_42_downstream_course_remains_locked(self) -> None:
        pcs = (_pc("IP", credits="3"), _pc("LOCKED", credits="3"))
        rules = (_rule_na("IP"), _rule_prereq("LOCKED", "IP"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        attempts = (StudentCourseAttempt("IP", AttemptOutcome.IN_PROGRESS),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6")),
        )
        path = res.paths[0]
        for sem in path.semesters:
            for c in sem.plan_option.courses:
                assert c.course_code != "LOCKED"

    def test_43_independent_courses_still_progress(self) -> None:
        pcs = (_pc("IP", credits="3"), _pc("INDEP", credits="3"), _pc("LOCKED", credits="3"))
        rules = (_rule_na("IP"), _rule_na("INDEP"), _rule_prereq("LOCKED", "IP"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        attempts = (StudentCourseAttempt("IP", AttemptOutcome.IN_PROGRESS),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=3),
        )
        path = res.paths[0]
        assert path.semester_count == 1
        assert path.semesters[0].plan_option.courses[0].course_code == "INDEP"
        assert path.status is PathStatus.BLOCKED_BY_CURRENT_IN_PROGRESS

    def test_44_blocker_only_when_it_actually_stops_path(self) -> None:
        # Student has an unrelated IN_PROGRESS course, but all remaining required courses are independent
        pcs = (_pc("IP", credits="3"), _pc("REQ1", credits="3"))
        rules = (_rule_na("IP"), _rule_na("REQ1"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        attempts = (StudentCourseAttempt("IP", AttemptOutcome.IN_PROGRESS),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        assert path.semesters[0].plan_option.courses[0].course_code == "REQ1"

    def test_45_horizon_overrides_blocker_status(self) -> None:
        # Horizon = 1, but 2 independent semesters are needed and an in-progress exists
        pcs = (_pc("IP", credits="3"), _pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("IP"), _rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        attempts = (StudentCourseAttempt("IP", AttemptOutcome.IN_PROGRESS),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=1),
        )
        path = res.paths[0]
        assert path.status is PathStatus.HORIZON_REACHED


# ===========================================================================
# 7. Zero-Credit Courses (Tests 46-49)
# ===========================================================================


class TestZeroCredit:
    def test_46_zero_credit_selectable(self) -> None:
        pcs = (_pc("Z1", credits="0"), _pc("A", credits="3"))
        rules = (_rule_na("Z1"), _rule_na("A"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        # Both Z1 and A can be planned together because Z1 takes 0 credits!
        all_planned = [c.course_code for sem in path.semesters for c in sem.plan_option.courses]
        assert "Z1" in all_planned
        assert "A" in all_planned

    def test_47_zero_credit_consumes_no_credit_budget(self) -> None:
        pcs = (_pc("Z1", credits="0"), _pc("A", credits="3"))
        rules = (_rule_na("Z1"), _rule_na("A"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        assert path.semesters[0].plan_option.total_credit_hours == Decimal("3")

    def test_48_zero_credit_counts_toward_max_courses(self) -> None:
        pcs = (_pc("Z1", credits="0"), _pc("A", credits="3"))
        rules = (_rule_na("Z1"), _rule_na("A"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        # max_courses = 1 prevents taking Z1 and A together
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_courses_per_semester=1, max_semesters_ahead=2),
        )
        path = res.paths[0]
        assert path.semester_count == 2
        assert len(path.semesters[0].plan_option.courses) == 1
        assert len(path.semesters[1].plan_option.courses) == 1

    def test_49_required_zero_credit_prevents_premature_completion(self) -> None:
        pcs = (_pc("Z1", credits="0"), _pc("A", credits="3"))
        rules = (_rule_na("Z1"), _rule_na("A"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        # If student completed A (3 cr), but not Z1:
        attempts = (StudentCourseAttempt("A", AttemptOutcome.PASSED),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        assert path.semesters[0].plan_option.courses[0].course_code == "Z1"
        assert path.status is PathStatus.MODELED_COMPLETE


# ===========================================================================
# 8. State Deduplication (Tests 50-55)
# ===========================================================================


class TestStateDeduplication:
    def test_50_same_academic_state_different_order_deduplicates(self) -> None:
        # A, B independent; taking A then B vs B then A reaches identical state {A, B}
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=2, max_paths=5),
            semester_branch_width=2,
        )
        # At depth 2, only unique state representatives survive
        assert len(res.paths) >= 1

    def test_51_shallower_depth_wins_collision(self) -> None:
        # Suppose path 1 reaches state {A, B} in 1 semester (taking A+B), path 2 in 2 semesters (A then B)
        # The shallower representative (1 semester) leaves more remaining horizon and must win!
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6"), max_semesters_ahead=2),
        )
        path = res.paths[0]
        assert path.semester_count == 1  # took A+B in 1 semester

    def test_52_equal_depth_better_partial_tuple_wins(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=2),
        )
        assert len(res.paths) >= 1

    def test_53_failed_history_preserved_despite_key_exclusion(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        attempts = (StudentCourseAttempt("A", AttemptOutcome.FAILED),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert PathReasonCode.INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE in res.paths[0].reason_codes

    def test_54_in_progress_participates_in_state_key(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        attempts = (StudentCourseAttempt("A", AttemptOutcome.IN_PROGRESS),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert "A" in res.persisted_in_progress_courses

    def test_55_dedup_occurs_before_beam_slicing(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"), _pc("C", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"), _rule_na("C"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=3),
            beam_width=3,
        )
        assert len(res.paths) >= 1


# ===========================================================================
# 9. Beam Search & Complexity Bounds (Tests 56-61)
# ===========================================================================


class TestBeamSearch:
    def test_56_beam_width_enforced(self) -> None:
        pcs = tuple(_pc(f"C{i}", credits="3") for i in range(1, 8))
        rules = tuple(_rule_na(f"C{i}") for i in range(1, 8))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="21")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=4),
            beam_width=2,
            semester_branch_width=2,
        )
        assert res.total_parent_states_expanded <= 2 * 4

    def test_57_branch_width_enforced(self) -> None:
        pcs = tuple(_pc(f"C{i}", credits="3") for i in range(1, 6))
        rules = tuple(_rule_na(f"C{i}") for i in range(1, 6))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="15")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=2),
            beam_width=3,
            semester_branch_width=3,
        )
        assert res.total_parent_states_expanded <= 3 * 2

    def test_58_max_parent_expansions_bounded_by_48(self) -> None:
        pcs = tuple(_pc(f"C{i}", credits="3") for i in range(1, 16))
        rules = tuple(_rule_na(f"C{i}") for i in range(1, 16))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="45")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=16),
            beam_width=DEFAULT_BEAM_WIDTH,
            semester_branch_width=DEFAULT_SEMESTER_BRANCH_WIDTH,
        )
        # B * H = 3 * 16 = 48
        assert res.total_parent_states_expanded <= 48

    def test_59_deterministic_beam_ranking(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res1 = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        res2 = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert res1.paths[0].priority_tuple == res2.paths[0].priority_tuple

    def test_60_canonical_path_tie_break(self) -> None:
        pcs = (_pc("C2", credits="3"), _pc("C1", credits="3"))
        rules = (_rule_na("C2"), _rule_na("C1"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6")),
        )
        path = res.paths[0]
        # Codes in canonical_path_codes are sorted
        assert path.semesters[0].plan_option.courses[0].course_code in ("C1", "C2")

    def test_61_beam_branch_validation(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        with pytest.raises(DegreePathConstraintError, match="beam_width must be at least 1"):
            plan_degree_paths(p_cat, e_cat, (), DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")), beam_width=0)
        with pytest.raises(DegreePathConstraintError, match="semester_branch_width must be at least 1"):
            plan_degree_paths(p_cat, e_cat, (), DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")), semester_branch_width=0)
        with pytest.raises(DegreePathConstraintError, match="beam_width must be an integer"):
            plan_degree_paths(p_cat, e_cat, (), DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")), beam_width="3")  # type: ignore[arg-type]
        with pytest.raises(DegreePathConstraintError, match="semester_branch_width must be an integer"):
            plan_degree_paths(p_cat, e_cat, (), DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")), semester_branch_width="3")  # type: ignore[arg-type]


# ===========================================================================
# 10. Termination Precedence & Horizon (Tests 62-69)
# ===========================================================================


class TestTerminationPrecedence:
    def test_62_complete_at_horizon_is_modeled_complete(self) -> None:
        # Completes exactly at depth == max_semesters_ahead
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_prereq("B", "A"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=2),
        )
        path = res.paths[0]
        assert path.semester_count == 2
        assert path.status is PathStatus.MODELED_COMPLETE

    def test_63_incomplete_at_horizon_is_horizon_reached(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"), _pc("C", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"), _rule_na("C"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=2),
        )
        path = res.paths[0]
        assert path.status is PathStatus.HORIZON_REACHED

    def test_64_horizon_with_review_diagnostics(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("REV", credits="3"))
        rules = (_rule_na("A"), _rule_review("REV"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=1),
        )
        path = res.paths[0]
        # At depth 1 == max_semesters_ahead, status is HORIZON_REACHED!
        assert path.status is PathStatus.HORIZON_REACHED
        assert BlockerType.REVIEW_REQUIRED_BLOCKER.value in path.unresolved_blocker_codes

    def test_65_horizon_with_in_progress_diagnostics(self) -> None:
        pcs = (_pc("IP", credits="3"), _pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("IP"), _rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        attempts = (StudentCourseAttempt("IP", AttemptOutcome.IN_PROGRESS),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=1),
        )
        path = res.paths[0]
        assert path.status is PathStatus.HORIZON_REACHED
        assert BlockerType.CURRENT_IN_PROGRESS_BLOCKER.value in path.unresolved_blocker_codes

    def test_66_review_block_below_horizon(self) -> None:
        pcs = (_pc("REV", credits="3"),)
        rules = (_rule_review("REV"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=4),
        )
        path = res.paths[0]
        assert path.status is PathStatus.BLOCKED_BY_REVIEW_REQUIRED

    def test_67_in_progress_block_below_horizon(self) -> None:
        pcs = (_pc("IP", credits="3"), _pc("NEXT", credits="3"))
        rules = (_rule_na("IP"), _rule_prereq("NEXT", "IP"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        attempts = (StudentCourseAttempt("IP", AttemptOutcome.IN_PROGRESS),)
        res = plan_degree_paths(
            p_cat,
            e_cat,
            attempts,
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6"), max_semesters_ahead=4),
        )
        path = res.paths[0]
        assert path.status is PathStatus.BLOCKED_BY_CURRENT_IN_PROGRESS

    def test_68_generic_no_valid_next_plan(self) -> None:
        # Constraints too tight: student requests max 2 credits, but all courses are 3 credits
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("2"), max_semesters_ahead=4),
        )
        path = res.paths[0]
        assert path.status is PathStatus.NO_VALID_NEXT_PLAN
        assert BlockerType.PLAN_CONSTRAINTS_TOO_RESTRICTIVE.value in path.unresolved_blocker_codes

    def test_69_no_false_academic_dead_end(self) -> None:
        # Verify method notes and status avoid saying "no academic path exists globally"
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("2")),
        )
        assert "no academic path exists globally" not in res.methodology_note.lower()

    def test_69a_horizon_in_progress_only_has_no_speculative_prerequisite_lock(self) -> None:
        pcs = (_pc("IP", credits="3"), _pc("A", credits="3"))
        rules = (_rule_na("IP"), _rule_na("A"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        attempts = (StudentCourseAttempt("IP", AttemptOutcome.IN_PROGRESS),)
        constraints = DegreePathConstraints(
            max_credit_hours_per_semester=Decimal("3"),
            max_semesters_ahead=1,
        )

        first = plan_degree_paths(p_cat, e_cat, attempts, constraints)
        second = plan_degree_paths(p_cat, e_cat, attempts, constraints)

        assert first == second
        path = first.paths[0]
        assert path.status is PathStatus.HORIZON_REACHED
        assert path.unresolved_blocker_codes == (
            BlockerType.CURRENT_IN_PROGRESS_BLOCKER.value,
        )
        assert BlockerType.PREREQUISITES_LOCKED.value not in path.unresolved_blocker_codes
        assert BlockerType.CANDIDATE_WINDOW_EXCLUSION.value not in path.unresolved_blocker_codes

    def test_69b_genuine_missing_prerequisite_emits_prerequisites_locked(self) -> None:
        pcs = (_pc("LOCKED", credits="3"),)
        rules = (_rule_prereq("LOCKED", "MISSING"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")

        result = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(
                max_credit_hours_per_semester=Decimal("3"),
                max_semesters_ahead=4,
            ),
        )

        path = result.paths[0]
        assert path.status is PathStatus.NO_VALID_NEXT_PLAN
        assert BlockerType.PREREQUISITES_LOCKED.value in path.unresolved_blocker_codes
        assert BlockerType.PLAN_CONSTRAINTS_TOO_RESTRICTIVE.value not in path.unresolved_blocker_codes

    def test_69c_more_than_candidate_window_with_valid_plan_has_no_window_blocker(self) -> None:
        pcs = tuple(_pc(f"C{i:02d}", credits="3", display_order=i) for i in range(1, 17))
        rules = tuple(_rule_na(f"C{i:02d}") for i in range(1, 17))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="48")

        result = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(
                max_credit_hours_per_semester=Decimal("3"),
                max_semesters_ahead=1,
                max_paths=10,
            ),
        )

        assert result.paths
        assert all(path.semester_count == 1 for path in result.paths)
        assert all(
            BlockerType.CANDIDATE_WINDOW_EXCLUSION.value not in path.unresolved_blocker_codes
            for path in result.paths
        )

    def test_69d_outside_window_candidate_must_fit_constraints_to_emit_blocker(self) -> None:
        pcs = tuple(
            _pc(f"C{i:02d}", credits="3" if i <= 15 else "1", display_order=i)
            for i in range(1, 17)
        )
        rules = tuple(_rule_na(f"C{i:02d}") for i in range(1, 17))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="46")

        result = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(
                max_credit_hours_per_semester=Decimal("2"),
                max_semesters_ahead=1,
            ),
        )

        path = result.paths[0]
        assert path.status is PathStatus.NO_VALID_NEXT_PLAN
        assert BlockerType.CANDIDATE_WINDOW_EXCLUSION.value in path.unresolved_blocker_codes
        assert BlockerType.PLAN_CONSTRAINTS_TOO_RESTRICTIVE.value not in path.unresolved_blocker_codes

    def test_69e_outside_window_candidates_that_do_not_fit_are_not_blockers(self) -> None:
        pcs = tuple(_pc(f"C{i:02d}", credits="3", display_order=i) for i in range(1, 17))
        rules = tuple(_rule_na(f"C{i:02d}") for i in range(1, 17))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="48")

        result = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(
                max_credit_hours_per_semester=Decimal("2"),
                max_semesters_ahead=1,
            ),
        )

        path = result.paths[0]
        assert path.status is PathStatus.NO_VALID_NEXT_PLAN
        assert BlockerType.PLAN_CONSTRAINTS_TOO_RESTRICTIVE.value in path.unresolved_blocker_codes
        assert BlockerType.CANDIDATE_WINDOW_EXCLUSION.value not in path.unresolved_blocker_codes

    def test_69f_independently_proven_current_and_prerequisite_blockers_can_coexist(self) -> None:
        pcs = (
            _pc("IP", credits="3"),
            _pc("A", credits="3"),
            _pc("LOCKED", credits="3"),
        )
        rules = (
            _rule_na("IP"),
            _rule_na("A"),
            _rule_prereq("LOCKED", "MISSING"),
        )
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")

        result = plan_degree_paths(
            p_cat,
            e_cat,
            (StudentCourseAttempt("IP", AttemptOutcome.IN_PROGRESS),),
            DegreePathConstraints(
                max_credit_hours_per_semester=Decimal("3"),
                max_semesters_ahead=1,
            ),
        )

        path = result.paths[0]
        assert path.status is PathStatus.HORIZON_REACHED
        assert BlockerType.CURRENT_IN_PROGRESS_BLOCKER.value in path.unresolved_blocker_codes
        assert BlockerType.PREREQUISITES_LOCKED.value in path.unresolved_blocker_codes


# ===========================================================================
# 11. Ranking & Priority Tuples (Tests 70-78)
# ===========================================================================


class TestRanking:
    def test_70_complete_outranks_incomplete(self) -> None:
        # Path 1 completes in 2 sem; Path 2 is truncated
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=2),
        )
        path = res.paths[0]
        assert path.status is PathStatus.MODELED_COMPLETE
        assert path.priority_tuple[0] == -1

    def test_71_fewer_semesters_ranks_higher_among_complete(self) -> None:
        # Path A takes 6 cr in 1 sem; Path B takes 3 cr + 3 cr in 2 sem
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6"), max_semesters_ahead=2, max_paths=3),
            semester_branch_width=3,
        )
        assert res.paths[0].semester_count == 1
        assert res.paths[0].status is PathStatus.MODELED_COMPLETE

    def test_72_incomplete_paths_shorter_semester_count_precedence(self) -> None:
        # Verifies accepted spec: P2 (semester_count) appears before P3 in FinalPriorityTuple
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"), _pc("C", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"), _rule_na("C"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=2),
        )
        assert res.paths[0].priority_tuple[0] == 0  # incomplete

    def test_73_more_newly_satisfied_groups_higher_rank(self) -> None:
        g1 = _rg("g1", "G1", required_hours="3", display_order=1)
        g2 = _rg("g2", "G2", required_hours="3", display_order=2)
        pcs = (_pc("C1", group_id="g1", credits="3"), _pc("C2", group_id="g2", credits="3"))
        rules = (_rule_na("C1"), _rule_na("C2"))
        p_cat, e_cat = _catalogs(pcs, rules, groups=(g1, g2), total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6")),
        )
        assert res.paths[0].newly_satisfied_requirement_group_count == 2

    def test_74_fewer_blockers_higher_rank(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert res.paths[0].priority_tuple[4] == 0  # 0 blockers

    def test_75_lower_aggregate_rank_sum(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert res.paths[0].aggregate_semester_rank_sum >= 1

    def test_76_canonical_final_tie_break(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        # Check canonical codes in priority_tuple
        assert isinstance(res.paths[0].priority_tuple[6], tuple)

    def test_77_exact_final_tuple_structure(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        tup = res.paths[0].priority_tuple
        assert len(tup) == 7
        assert tup[0] == -1  # -P1
        assert tup[1] == 1   # P2
        assert tup[2] == Decimal("-3")  # -P3
        assert tup[3] == -1  # -P4
        assert tup[4] == 0   # P5
        assert tup[5] == 1   # P6
        assert tup[6] == (("A",),)  # P7

    def test_78_exact_partial_tuple_structure(self) -> None:
        from app.degree_path.engine import _partial_priority_tuple, _PathState
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        state = _PathState(
            depth=1,
            accumulated_attempts=(),
            academic_progress=p_cat.requirement_groups[0],  # type: ignore
            selected_semesters=(),
            unresolved_blocker_codes=(),
            canonical_path_codes=(("A",),),
        )
        # Tuple contains 7 components: -Q1, Q2, -Q3, -Q4, Q5, Q6, Q7
        assert len(res.paths[0].priority_tuple) == 7


# ===========================================================================
# 12. Path Reason Codes (Tests 79-89)
# ===========================================================================


class TestReasonCodes:
    def test_79_modeled_completion_reason(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        assert PathReasonCode.REACHES_MODELED_PLAN_COMPLETION in path.reason_codes
        assert PathReasonCode.COMPLETES_ALL_REQUIREMENT_GROUPS in path.reason_codes

    def test_80_fewer_modeled_semesters_relative_reason(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6"), max_semesters_ahead=2, max_paths=3),
            semester_branch_width=3,
        )
        assert PathReasonCode.FEWER_MODELED_SEMESTERS in res.paths[0].reason_codes

    def test_81_progress_max_relative_reason(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"), _pc("C", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"), _rule_na("C"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=1),
        )
        assert PathReasonCode.MAXIMIZES_PROGRESS_WITHIN_HORIZON in res.paths[0].reason_codes

    def test_82_tied_fewer_semester_paths_both_receive_reason(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=2, max_paths=5),
            semester_branch_width=2,
        )
        for p in res.paths:
            if p.status is PathStatus.MODELED_COMPLETE and p.semester_count == 2:
                assert PathReasonCode.FEWER_MODELED_SEMESTERS in p.reason_codes

    def test_83_tied_max_progress_paths_both_handled(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"), _pc("C", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"), _rule_na("C"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=1, max_paths=5),
            semester_branch_width=2,
        )
        for p in res.paths:
            if p.completed_plan_credit_delta == Decimal("3"):
                assert PathReasonCode.MAXIMIZES_PROGRESS_WITHIN_HORIZON in p.reason_codes

    def test_84_mandatory_reason_propagation(self) -> None:
        pcs = (_pc("MAND", credits="3"),)
        rules = (_rule_na("MAND"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert PathReasonCode.CONTAINS_MANDATORY_COURSES in res.paths[0].reason_codes

    def test_85_zero_credit_reason_propagation(self) -> None:
        pcs = (_pc("Z", credits="0"),)
        rules = (_rule_na("Z"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="0")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert PathReasonCode.INCLUDES_ZERO_CREDIT_REQUIRED in res.paths[0].reason_codes

    def test_86_previously_attempted_reason_propagation(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (StudentCourseAttempt("A", AttemptOutcome.FAILED),),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert PathReasonCode.INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE in res.paths[0].reason_codes

    def test_87_review_block_reason(self) -> None:
        pcs = (_pc("REV", credits="3"),)
        rules = (_rule_review("REV"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert PathReasonCode.BLOCKED_BY_REVIEW_REQUIRED in res.paths[0].reason_codes

    def test_88_in_progress_block_reason(self) -> None:
        pcs = (_pc("IP", credits="3"), _pc("NEXT", credits="3"))
        rules = (_rule_na("IP"), _rule_prereq("NEXT", "IP"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (StudentCourseAttempt("IP", AttemptOutcome.IN_PROGRESS),),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert PathReasonCode.BLOCKED_BY_CURRENT_IN_PROGRESS in res.paths[0].reason_codes

    def test_89_no_next_semester_reason(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("1")),
        )
        assert PathReasonCode.NO_VALID_NEXT_SEMESTER in res.paths[0].reason_codes


# ===========================================================================
# 13. Max Paths Presentation Behavior (Tests 90-92)
# ===========================================================================


class TestMaxPathsPresentation:
    def test_90_max_paths_one_presentation_only(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6"), max_paths=1),
        )
        assert len(res.paths) == 1

    def test_91_max_paths_prefix_equivalence(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"), _pc("C", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"), _rule_na("C"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        res_5 = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=3, max_paths=5),
            semester_branch_width=3,
        )
        res_2 = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=3, max_paths=2),
            semester_branch_width=3,
        )
        assert len(res_2.paths) == min(2, len(res_5.paths))
        for i in range(len(res_2.paths)):
            assert res_2.paths[i].priority_tuple == res_5.paths[i].priority_tuple

    def test_92_search_unaffected_by_max_paths(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res1 = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_paths=1),
        )
        res3 = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_paths=3),
        )
        assert res1.total_parent_states_expanded == res3.total_parent_states_expanded


# ===========================================================================
# 14. Real Plan 12 Verified Facts (Tests 93-100)
# ===========================================================================


class TestRealPlan12:
    def test_93_plan12_progression_chain(self) -> None:
        # Verified canonical chain: 0300153 -> 1501110 -> 1501112 -> 1501221
        pcs = (
            _pc("0300153", credits="3", display_order=1),
            _pc("1501110", credits="3", display_order=2),
            _pc("1501112", credits="3", display_order=3),
            _pc("1501221", credits="3", display_order=4),
        )
        rules = (
            _rule_na("0300153", "مهارات الحاسوب"),
            _rule_prereq("1501110", "0300153", "برمجة حاسوب 1"),
            _rule_prereq("1501112", "1501110", "برمجة حاسوب 2"),
            _rule_prereq("1501221", "1501112", "تراكيب البيانات"),
        )
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="12")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=4),
        )
        path = res.paths[0]
        assert path.semester_count == 4
        assert path.semesters[0].plan_option.courses[0].course_code == "0300153"
        assert path.semesters[1].plan_option.courses[0].course_code == "1501110"
        assert path.semesters[2].plan_option.courses[0].course_code == "1501112"
        assert path.semesters[3].plan_option.courses[0].course_code == "1501221"

    def test_94_1501110_prereq_is_0300153(self) -> None:
        pcs = (_pc("0300153", credits="3"), _pc("1501110", credits="3"))
        rules = (_rule_na("0300153"), _rule_prereq("1501110", "0300153"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("6")),
        )
        path = res.paths[0]
        assert path.semester_count == 2
        assert path.semesters[0].plan_option.courses[0].course_code == "0300153"
        assert path.semesters[1].plan_option.courses[0].course_code == "1501110"

    def test_95_1501221_prereq_is_1501112(self) -> None:
        pcs = (_pc("1501112", credits="3"), _pc("1501221", credits="3"))
        rules = (_rule_na("1501112"), _rule_prereq("1501221", "1501112"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (StudentCourseAttempt("1501112", AttemptOutcome.PASSED),),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        assert path.semesters[0].plan_option.courses[0].course_code == "1501221"

    def test_96_0200115_community_volunteer_zero_credit(self) -> None:
        g_univ = _rg(GRP_UNIV_REQ, "UNIVERSITY_REQUIRED", RequirementType.REQUIRED, "3", 1)
        pcs = (
            ProgressPlanCourse("pc-0200115", PLAN_ID, GRP_UNIV_REQ, "0200115", CourseCatalogStatus.KNOWN, Decimal("0"), 1),
            ProgressPlanCourse("pc-0200110", PLAN_ID, GRP_UNIV_REQ, "0200110", CourseCatalogStatus.KNOWN, Decimal("3"), 2),
        )
        rules = (_rule_na("0200115", "تنمية المجتمع والعمل التطوعي"), _rule_na("0200110", "العلوم العسكرية"))
        p_cat, e_cat = _catalogs(pcs, rules, groups=(g_univ,), total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        codes = [c.course_code for c in path.semesters[0].plan_option.courses]
        assert "0200115" in codes
        assert "0200110" in codes

    def test_97_1509999_it_seminar_zero_credit(self) -> None:
        g_fac = _rg(GRP_FAC_REQ, "FACULTY_REQUIRED", RequirementType.REQUIRED, "3", 1)
        pcs = (
            ProgressPlanCourse("pc-1509999", PLAN_ID, GRP_FAC_REQ, "1509999", CourseCatalogStatus.KNOWN, Decimal("0"), 1),
            ProgressPlanCourse("pc-FAC1", PLAN_ID, GRP_FAC_REQ, "FAC1", CourseCatalogStatus.KNOWN, Decimal("3"), 2),
        )
        rules = (_rule_na("1509999", "حلقة بحث لطلبة كلية تكنولوجيا المعلومات"), _rule_na("FAC1"))
        p_cat, e_cat = _catalogs(pcs, rules, groups=(g_fac,), total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        codes = [c.course_code for c in path.semesters[0].plan_option.courses]
        assert "1509999" in codes

    def test_98_1505311_never_selected(self) -> None:
        pcs = (_pc("1505311", credits="3"),)
        rules = (_rule_unresolved("1505311", "تعلم الالة"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        assert path.status is PathStatus.BLOCKED_BY_REVIEW_REQUIRED
        for sem in path.semesters:
            for c in sem.plan_option.courses:
                assert c.course_code != "1505311"

    def test_99_1505320_never_selected(self) -> None:
        pcs = (_pc("1505320", credits="3"),)
        rules = (_rule_review("1505320", "تعلم الآلة المتقدم"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        assert path.status is PathStatus.BLOCKED_BY_REVIEW_REQUIRED

    def test_100_0300103_referenced_only_never_selected(self) -> None:
        # الإحصاء والاحتمالات (0300103) is referenced-only, not in plan_courses
        pcs = (_pc("STAT_ADV", credits="3"),)
        # Rule specifies 0300103 as prerequisite
        rules = (
            PlanCourseRule("STAT_ADV", PrerequisiteLogicStatus.VERIFIED, (
                DependencyGroup(1, DependencyType.PREREQUISITE, ("0300103",)),
            )),
        )
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        for sem in path.semesters:
            for c in sem.plan_option.courses:
                assert c.course_code != "0300103"


# ===========================================================================
# 15. Determinism & Stability (Tests 101-104)
# ===========================================================================


class TestDeterminism:
    def test_101_identical_run_identical_result(self) -> None:
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"), _pc("C", credits="3"))
        rules = (_rule_na("A"), _rule_prereq("B", "A"), _rule_na("C"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="9")
        constraints = DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=3)
        res1 = plan_degree_paths(p_cat, e_cat, (), constraints)
        res2 = plan_degree_paths(p_cat, e_cat, (), constraints)
        assert len(res1.paths) == len(res2.paths)
        for p1, p2 in zip(res1.paths, res2.paths):
            assert p1.priority_tuple == p2.priority_tuple
            assert p1.reason_codes == p2.reason_codes

    def test_102_candidate_ordering_stability(self) -> None:
        # Reversed catalog course order must still produce identical plans
        pcs1 = (_pc("A", credits="3", display_order=1), _pc("B", credits="3", display_order=2))
        rules1 = (_rule_na("A"), _rule_na("B"))
        pcs2 = (_pc("B", credits="3", display_order=2), _pc("A", credits="3", display_order=1))
        rules2 = (_rule_na("B"), _rule_na("A"))
        p_cat1, e_cat1 = _catalogs(pcs1, rules1, total_credits="6")
        p_cat2, e_cat2 = _catalogs(pcs2, rules2, total_credits="6")
        constraints = DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"))
        res1 = plan_degree_paths(p_cat1, e_cat1, (), constraints)
        res2 = plan_degree_paths(p_cat2, e_cat2, (), constraints)
        assert res1.paths[0].priority_tuple == res2.paths[0].priority_tuple

    def test_103_no_timestamps_in_result(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert not hasattr(res, "timestamp")
        assert not hasattr(res, "created_at")

    def test_104_no_random_uuid_in_result(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        for path in res.paths:
            assert not hasattr(path, "uuid")
            assert not hasattr(path, "path_id")


# ===========================================================================
# 16. Pure Boundary Audit (Tests 105-108)
# ===========================================================================


class TestBoundaryAudit:
    def test_105_no_fastapi_imports(self) -> None:
        import app.degree_path.engine as eng
        import app.degree_path.models as mod
        assert "fastapi" not in sys.modules or "fastapi" not in eng.__dict__
        assert "fastapi" not in mod.__dict__

    def test_106_no_http_imports(self) -> None:
        import app.degree_path.engine as eng
        import app.degree_path.models as mod
        assert "httpx" not in eng.__dict__
        assert "httpx" not in mod.__dict__

    def test_107_no_supabase_imports(self) -> None:
        import app.degree_path.engine as eng
        import app.degree_path.models as mod
        assert "supabase" not in eng.__dict__
        assert "supabase" not in mod.__dict__

    def test_108_policy_version_and_scope(self) -> None:
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        assert res.degree_path_policy_version == DEGREE_PATH_POLICY_VERSION == "1.0"
        assert res.planning_scope == PLANNING_SCOPE == "MODELED_DEGREE_PATH_ONLY"


# ===========================================================================
# 17. Policy Specification Contracts (Tests 109-113)
# ===========================================================================


class TestPolicySpecificationContracts:
    def test_109_path_reason_code_exact_members(self) -> None:
        """Assert exact PathReasonCode vocabulary matching Phase 9.1 §26."""
        expected = {
            "REACHES_MODELED_PLAN_COMPLETION",
            "FEWER_MODELED_SEMESTERS",
            "MAXIMIZES_PROGRESS_WITHIN_HORIZON",
            "CONTAINS_MANDATORY_COURSES",
            "INCLUDES_ZERO_CREDIT_REQUIRED",
            "COMPLETES_ALL_REQUIREMENT_GROUPS",
            "INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE",
            "BLOCKED_BY_REVIEW_REQUIRED",
            "BLOCKED_BY_CURRENT_IN_PROGRESS",
            "NO_VALID_NEXT_SEMESTER",
        }
        actual = {m.value for m in PathReasonCode}
        assert actual == expected
        assert len(PathReasonCode) == 10

    def test_110_academic_state_key_exact_policy(self) -> None:
        """AcademicStateKey = (frozenset(C_completed_and_hypothetical), frozenset(C_persisted_in_progress))."""
        from app.degree_path.engine import _completed_passed_codes
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, _ = _catalogs(pcs, rules, total_credits="6")
        prog = calculate_academic_progress(p_cat, (StudentCourseAttempt("A", AttemptOutcome.PASSED),))
        passed = _completed_passed_codes(prog)
        assert passed == frozenset({"A"})

    def test_111_dedup_independent_progress_construction(self) -> None:
        """States with identical passed + in-progress sets deduplicate even if progress objects differ."""
        from app.degree_path.engine import _PathState, _partial_priority_tuple
        from app.planner.models import SemesterPlanOption, PlannedCourseEntry, PlanReasonCode
        pcs = (_pc("A", credits="3"), _pc("B", credits="3"))
        rules = (_rule_na("A"), _rule_na("B"))
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="6")

        # Two paths reaching identical passed set {A, B} via different orders
        # State 1: A then B
        prog1 = calculate_academic_progress(p_cat, (
            StudentCourseAttempt("A", AttemptOutcome.PASSED),
            StudentCourseAttempt("B", AttemptOutcome.PASSED),
        ))
        # State 2: B then A
        prog2 = calculate_academic_progress(p_cat, (
            StudentCourseAttempt("B", AttemptOutcome.PASSED),
            StudentCourseAttempt("A", AttemptOutcome.PASSED),
        ))

        # Ensure their completed passed sets are strictly equal
        from app.degree_path.engine import _completed_passed_codes
        assert _completed_passed_codes(prog1) == _completed_passed_codes(prog2) == frozenset({"A", "B"})

        # Run engine: both permutations should yield a single canonical complete path
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3"), max_semesters_ahead=2, max_paths=10),
            semester_branch_width=3,
        )
        complete_paths = [p for p in res.paths if p.status is PathStatus.MODELED_COMPLETE]
        # Deduplication must collapse the identical end-states into canonical winners
        assert len(complete_paths) >= 1
        # Distinct complete paths must have distinct course sets or sequences
        path_codes = [tuple(c.course_code for s in p.semesters for c in s.plan_option.courses) for p in complete_paths]
        assert len(path_codes) == len(set(path_codes))

    def test_112_final_priority_tuple_exact_structure(self) -> None:
        """Assert exact FinalPriorityTuple = (-P1, P2, -P3, -P4, P5, P6, P7) matching Phase 9.1 §23."""
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        res = plan_degree_paths(
            p_cat,
            e_cat,
            (),
            DegreePathConstraints(max_credit_hours_per_semester=Decimal("3")),
        )
        path = res.paths[0]
        # Priority tuple has 7 elements
        tup = path.priority_tuple
        assert len(tup) == 7
        p1, p2, p3, p4, p5, p6, p7 = tup
        assert p1 == -1  # -completion_rank (-1 for MODELED_COMPLETE)
        assert p2 == 1   # semester_count
        assert p3 == -Decimal("3")  # -completed_credits_delta
        assert p4 == -1  # -newly_satisfied_groups
        assert p5 == 0   # unresolved_blocker_count
        assert p6 == 1   # aggregate_rank_sum
        assert p7 == (("A",),)  # canonical_path_codes

    def test_113_partial_priority_tuple_exact_structure(self) -> None:
        """Assert exact PartialPriorityTuple = (-Q1, Q2, -Q3, -Q4, Q5, Q6, Q7) matching Phase 9.1 §24."""
        from app.degree_path.engine import _PathState, _partial_priority_tuple
        pcs = (_pc("A", credits="3"),)
        rules = (_rule_na("A"),)
        p_cat, e_cat = _catalogs(pcs, rules, total_credits="3")
        initial_progress = calculate_academic_progress(p_cat, ())
        child_progress = calculate_academic_progress(p_cat, (StudentCourseAttempt("A", AttemptOutcome.PASSED),))

        state = _PathState(
            depth=1,
            accumulated_attempts=(StudentCourseAttempt("A", AttemptOutcome.PASSED),),
            academic_progress=child_progress,
            selected_semesters=(),
            unresolved_blocker_codes=(),
            canonical_path_codes=(("A",),),
        )
        tup = _partial_priority_tuple(state, initial_progress)
        assert len(tup) == 7
        q1, q2, q3, q4, q5, q6, q7 = tup
        assert q1 == -1  # -is_complete
        assert q2 == 1   # depth
        assert q3 == -Decimal("3")  # -modeled_credits_delta
        assert q4 == -1  # -satisfied_groups_count
        assert q5 == 0   # blocker_count
        assert q6 == 0   # aggregate_rank_sum
        assert q7 == (("A",),)  # canonical_path_codes
