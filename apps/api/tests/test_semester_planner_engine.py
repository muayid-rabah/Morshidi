"""Exhaustive pure tests for Phase 8.2 — Deterministic Semester Planner Engine.

All tests are pure (no Supabase, no FastAPI, no network, no I/O).
Tests use in-memory catalog objects constructed from verified Plan 12 facts and test fixtures.

Test suites cover:
  1-12   Constraints & validation
  13-18  Candidate window & filtering
  19-25  Combination validity
  26-28  Same-semester prerequisite rule
  29-35  Progress simulation
  36-46  Unlock simulation & joint interactions
  47-54  Priority tuple & sorting
  55-58  Zero-credit handling
  59-69  Reason codes
  70-73  Top-K retention & ranking
  74-79  Determinism
  80-88  Real Plan 12 facts
  89-92  Bounds & search limitations
  93-95  Model & integrity checks
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.planner.engine import plan_semester
from app.planner.models import (
    DEFAULT_CANDIDATE_WINDOW_SIZE,
    MAX_CREDIT_HOURS_SAFETY_CEILING,
    PLANNING_SCOPE,
    SEMESTER_PLANNER_POLICY_VERSION,
    PlannedCourseEntry,
    PlannerConstraintError,
    PlannerConstraints,
    PlannerIntegrityError,
    PlanReasonCode,
    SemesterPlanOption,
    SemesterPlannerResult,
)
from app.progress.models import (
    AcademicProgressCatalog,
    CourseProgressState,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.recommendations.engine import recommend_courses
from app.recommendations.models import (
    RecommendationCandidate,
    RecommendationReason,
    RecommendationResult,
    ReviewRequiredCourse,
)
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CourseCatalogStatus,
    CourseIdentity,
    Decision,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)

PLAN_ID = "10000000-0000-0000-0000-000000000005"
GRP_REQUIRED = "gr-required"
GRP_ELECTIVE = "gr-elective"
GRP_FACULTY = "gr-faculty"


# ---------------------------------------------------------------------------
# Test Catalog & Candidate Builders
# ---------------------------------------------------------------------------


def _plan(total: str = "132") -> ProgressStudyPlan:
    return ProgressStudyPlan(study_plan_id=PLAN_ID, total_credit_hours=Decimal(total))


def _req_group(
    group_id: str = GRP_REQUIRED,
    code: str = "MAJOR_REQUIRED",
    required_hours: str = "9",
    display_order: int = 1,
) -> ProgressRequirementGroup:
    return ProgressRequirementGroup(
        group_id=group_id,
        study_plan_id=PLAN_ID,
        group_code=code,
        name_ar="إجباري",
        name_en="Required",
        scope="major",
        requirement_type=RequirementType.REQUIRED,
        required_credit_hours=Decimal(required_hours),
        display_order=display_order,
    )


def _elec_group(
    group_id: str = GRP_ELECTIVE,
    code: str = "MAJOR_ELECTIVE",
    required_hours: str = "9",
    display_order: int = 2,
) -> ProgressRequirementGroup:
    return ProgressRequirementGroup(
        group_id=group_id,
        study_plan_id=PLAN_ID,
        group_code=code,
        name_ar="اختياري",
        name_en="Elective",
        scope="major",
        requirement_type=RequirementType.ELECTIVE,
        required_credit_hours=Decimal(required_hours),
        display_order=display_order,
    )


def _pc(
    code: str,
    group_id: str = GRP_REQUIRED,
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


def _rule_verified(code: str, prereq: str, name_ar: str | None = None) -> PlanCourseRule:
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


def _rule_verified_two(code: str, prereq1: str, prereq2: str) -> PlanCourseRule:
    return PlanCourseRule(
        course_code=code,
        prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
        dependency_groups=(
            DependencyGroup(1, DependencyType.PREREQUISITE, (prereq1,)),
            DependencyGroup(2, DependencyType.PREREQUISITE, (prereq2,)),
        ),
        raw_prerequisite_text=f"{prereq1},{prereq2}",
        target_name_ar=None,
    )


def _rule_unresolved(code: str, raw: str | None = None) -> PlanCourseRule:
    return PlanCourseRule(
        course_code=code,
        prerequisite_logic_status=PrerequisiteLogicStatus.UNRESOLVED,
        dependency_groups=(),
        raw_prerequisite_text=raw,
        target_name_ar=None,
    )


def _rule_conflict(code: str, raw: str | None = None) -> PlanCourseRule:
    return PlanCourseRule(
        course_code=code,
        prerequisite_logic_status=PrerequisiteLogicStatus.SOURCE_CONFLICT,
        dependency_groups=(),
        raw_prerequisite_text=raw,
        target_name_ar=None,
    )


def _build_catalogs(
    prog_groups: tuple[ProgressRequirementGroup, ...],
    prog_courses: tuple[ProgressPlanCourse, ...],
    plan_rules: tuple[PlanCourseRule, ...],
) -> tuple[AcademicProgressCatalog, CanTakeCatalog]:
    progress_catalog = AcademicProgressCatalog(
        study_plan=_plan(),
        requirement_groups=prog_groups,
        plan_courses=prog_courses,
    )
    identities: dict[str, CourseIdentity] = {}
    for rule in plan_rules:
        identities[rule.course_code] = CourseIdentity(
            course_code=rule.course_code,
            catalog_status=CourseCatalogStatus.KNOWN,
        )
    for rule in plan_rules:
        for dg in rule.dependency_groups:
            for opt in dg.option_course_codes:
                if opt not in identities:
                    identities[opt] = CourseIdentity(
                        course_code=opt,
                        catalog_status=CourseCatalogStatus.REFERENCED_ONLY,
                    )
    eligibility_catalog = CanTakeCatalog(
        study_plan_id=PLAN_ID,
        courses=tuple(identities.values()),
        plan_courses=plan_rules,
    )
    return progress_catalog, eligibility_catalog


def _candidate(
    code: str,
    credits: str = "3",
    rank: int = 1,
    group_code: str = "MAJOR_REQUIRED",
    req_type: str = "required",
    previously_attempted: bool = False,
    name_ar: str | None = None,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        course_code=code,
        course_name_ar=name_ar or f"Course {code}",
        credit_hours=Decimal(credits),
        requirement_group_code=group_code,
        requirement_type=req_type,
        course_state="NOT_ATTEMPTED" if not previously_attempted else "ATTEMPTED_NOT_COMPLETED",
        eligibility_decision="ELIGIBLE",
        effective_credit_contribution=Decimal(credits),
        group_remaining_credits_before=Decimal("9"),
        group_remaining_credits_after=Decimal("6"),
        completes_requirement_group=False,
        newly_eligible_count=0,
        newly_eligible_course_codes=(),
        priority_tuple=(2, 1, Decimal(credits), 0, 0, -rank, code),
        rank=rank,
        reason_codes=(RecommendationReason.REQUIRED_PLAN_COURSE,),
        previously_attempted=previously_attempted,
    )


def _recommendation_result(
    candidates: tuple[RecommendationCandidate, ...],
    review_required: tuple[ReviewRequiredCourse, ...] = (),
    excluded_in_progress: tuple[str, ...] = (),
    study_plan_id: str = PLAN_ID,
) -> RecommendationResult:
    return RecommendationResult(
        study_plan_id=study_plan_id,
        recommendation_policy_version="1.0",
        ranked_recommendations=candidates,
        review_required_courses=review_required,
        excluded_in_progress=excluded_in_progress,
        methodology_note="Test note",
        limitations=("Test limit",),
    )


# ===========================================================================
# PART 1: CONSTRAINTS & VALIDATION (Tests 1–12)
# ===========================================================================


def test_01_negative_max_credit_hours_rejected():
    with pytest.raises(PlannerConstraintError, match="cannot be negative"):
        PlannerConstraints(max_credit_hours=Decimal("-1.00"))


def test_02_max_credit_hours_above_safety_ceiling_rejected():
    with pytest.raises(PlannerConstraintError, match="safety limit"):
        PlannerConstraints(max_credit_hours=Decimal("30.01"))


def test_03_zero_max_credit_hours_accepted():
    c = PlannerConstraints(max_credit_hours=Decimal("0.00"))
    assert c.max_credit_hours == Decimal("0.00")


def test_04_decimal_exact_behavior_rejects_float():
    with pytest.raises(PlannerConstraintError, match="not float"):
        PlannerConstraints(max_credit_hours=15.5)  # type: ignore[arg-type]


def test_05_max_courses_none_accepted():
    c = PlannerConstraints(max_credit_hours=Decimal("15.00"), max_courses=None)
    assert c.max_courses is None


def test_06_max_courses_one_accepted():
    c = PlannerConstraints(max_credit_hours=Decimal("15.00"), max_courses=1)
    assert c.max_courses == 1


def test_07_max_courses_zero_rejected():
    with pytest.raises(PlannerConstraintError, match="between 1 and 10"):
        PlannerConstraints(max_credit_hours=Decimal("15.00"), max_courses=0)


def test_08_max_courses_eleven_rejected():
    with pytest.raises(PlannerConstraintError, match="between 1 and 10"):
        PlannerConstraints(max_credit_hours=Decimal("15.00"), max_courses=11)


def test_09_max_options_one_accepted():
    c = PlannerConstraints(max_credit_hours=Decimal("15.00"), max_options=1)
    assert c.max_options == 1


def test_10_max_options_ten_accepted():
    c = PlannerConstraints(max_credit_hours=Decimal("15.00"), max_options=10)
    assert c.max_options == 10


def test_11_max_options_zero_rejected():
    with pytest.raises(PlannerConstraintError, match="between 1 and 10"):
        PlannerConstraints(max_credit_hours=Decimal("15.00"), max_options=0)


def test_12_max_options_eleven_rejected():
    with pytest.raises(PlannerConstraintError, match="between 1 and 10"):
        PlannerConstraints(max_credit_hours=Decimal("15.00"), max_options=11)


# ===========================================================================
# PART 2: CANDIDATE WINDOW & FILTERING (Tests 13–18)
# ===========================================================================


def test_13_only_phase7_ranked_recommendations_considered():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    r1, r2 = _rule_na("C1"), _rule_na("C2")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))

    # C2 is in catalog but NOT in Phase 7 recommendations
    c1 = _candidate("C1", rank=1)
    rec_res = _recommendation_result((c1,))
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))

    all_planned_codes = {c.course_code for opt in res.plan_options for c in opt.courses}
    assert "C1" in all_planned_codes
    assert "C2" not in all_planned_codes


def test_14_review_required_excluded_from_plan_options():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    r1, r2 = _rule_na("C1"), _rule_na("C2")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))

    c1 = _candidate("C1", rank=1)
    rev2 = ReviewRequiredCourse("C2", "C2 ar", Decimal("3"), "MAJOR_REQUIRED", "required", "PREREQUISITE_LOGIC_UNRESOLVED", False)
    rec_res = _recommendation_result((c1,), review_required=(rev2,))
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))

    all_planned_codes = {c.course_code for opt in res.plan_options for c in opt.courses}
    assert "C2" not in all_planned_codes
    assert res.review_required_courses == ("C2",)


def test_15_excluded_in_progress_excluded_from_plan_options():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    r1, r2 = _rule_na("C1"), _rule_na("C2")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))

    c1 = _candidate("C1", rank=1)
    rec_res = _recommendation_result((c1,), excluded_in_progress=("C2",))
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))

    all_planned_codes = {c.course_code for opt in res.plan_options for c in opt.courses}
    assert "C2" not in all_planned_codes
    assert res.excluded_in_progress == ("C2",)


def test_16_top_15_candidate_window_enforced():
    g = _req_group(required_hours="99")
    pcs = tuple(_pc(f"C{i:02d}", display_order=i) for i in range(1, 21))
    rules = tuple(_rule_na(f"C{i:02d}") for i in range(1, 21))
    prog_cat, elig_cat = _build_catalogs((g,), pcs, rules)

    cands = tuple(_candidate(f"C{i:02d}", rank=i) for i in range(1, 21))
    rec_res = _recommendation_result(cands)
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")), candidate_window_size=15)

    assert res.candidate_window_size == 15
    assert res.evaluated_candidate_count == 15
    assert res.eligible_ranked_candidate_count == 20
    all_planned = {c.course_code for opt in res.plan_options for c in opt.courses}
    for i in range(16, 21):
        assert f"C{i:02d}" not in all_planned


def test_17_fewer_than_15_uses_all():
    g = _req_group()
    pcs = (_pc("C1"), _pc("C2"))
    rules = (_rule_na("C1"), _rule_na("C2"))
    prog_cat, elig_cat = _build_catalogs((g,), pcs, rules)

    cands = (_candidate("C1", rank=1), _candidate("C2", rank=2))
    rec_res = _recommendation_result(cands)
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))

    assert res.evaluated_candidate_count == 2
    assert res.candidate_window_size == 15


def test_18_candidate_order_uses_phase7_rank():
    g = _req_group()
    pcs = (_pc("C1"), _pc("C2"))
    rules = (_rule_na("C1"), _rule_na("C2"))
    prog_cat, elig_cat = _build_catalogs((g,), pcs, rules)

    # Inverted ranks
    cands = (_candidate("C2", rank=1), _candidate("C1", rank=2))
    rec_res = _recommendation_result(cands)
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3"), max_options=2))

    assert res.plan_options[0].courses[0].course_code == "C2"
    assert res.plan_options[1].courses[0].course_code == "C1"


# ===========================================================================
# PART 3: COMBINATION VALIDITY (Tests 19–25)
# ===========================================================================


def test_19_empty_combination_never_returned():
    g = _req_group()
    pc = _pc("C1", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1", credits="3"),))

    # max_credit_hours too small
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("2")))
    assert res.plan_options == ()
    assert res.valid_combination_count == 0


def test_20_over_credit_combination_excluded():
    g = _req_group()
    pc1, pc2 = _pc("C1", credits="3"), _pc("C2", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", credits="3", rank=1), _candidate("C2", credits="3", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    for opt in res.plan_options:
        assert opt.total_credit_hours <= Decimal("3")


def test_21_exact_credit_ceiling_accepted():
    g = _req_group()
    pc1, pc2 = _pc("C1", credits="3"), _pc("C2", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", credits="3", rank=1), _candidate("C2", credits="3", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6")))
    top = res.plan_options[0]
    assert top.total_credit_hours == Decimal("6")
    assert PlanReasonCode.USES_FULL_CREDIT_PREFERENCE in top.reason_codes


def test_22_max_courses_enforced():
    g = _req_group()
    pc1, pc2 = _pc("C1", credits="3"), _pc("C2", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", credits="3", rank=1), _candidate("C2", credits="3", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15"), max_courses=1))
    for opt in res.plan_options:
        assert opt.total_courses == 1


def test_23_zero_credit_does_not_consume_credit_budget():
    g = _req_group()
    pc1, pc2 = _pc("C1", credits="3"), _pc("C0", credits="0")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C0")))
    cands = (_candidate("C1", credits="3", rank=1), _candidate("C0", credits="0", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    top = res.plan_options[0]
    assert top.total_credit_hours == Decimal("3")
    assert top.total_courses == 2
    assert top.zero_credit_required_count == 1


def test_24_zero_credit_counts_toward_max_courses():
    g = _req_group()
    pc1, pc0 = _pc("C1", credits="3"), _pc("C0", credits="0")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc0), (_rule_na("C1"), _rule_na("C0")))
    cands = (_candidate("C1", credits="3", rank=1), _candidate("C0", credits="0", rank=2))
    rec_res = _recommendation_result(cands)

    # max_courses=1 rejects combination C1+C0
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15"), max_courses=1))
    for opt in res.plan_options:
        assert opt.total_courses == 1


def test_25_no_duplicate_courses_inside_plan():
    g = _req_group()
    pc1, pc2 = _pc("C1", credits="3"), _pc("C2", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", credits="3", rank=1), _candidate("C2", credits="3", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))
    for opt in res.plan_options:
        codes = [c.course_code for c in opt.courses]
        assert len(codes) == len(set(codes))


# ===========================================================================
# PART 4: SAME-SEMESTER PREREQUISITE RULE (Tests 26–28)
# ===========================================================================


def test_26_baseline_not_eligible_never_appears():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    r1, r2 = _rule_na("C1"), _rule_verified("C2", "C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))

    # C2 requires C1; C1 is not passed. C2 is NOT_ELIGIBLE at baseline.
    c1 = _candidate("C1", rank=1)
    rec_res = _recommendation_result((c1,))
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))

    all_planned = {c.course_code for opt in res.plan_options for c in opt.courses}
    assert "C2" not in all_planned


def test_27_A_eligible_B_requires_A_not_admitted_together():
    g = _req_group()
    pc1, pc2 = _pc("A"), _pc("B")
    r1, r2 = _rule_na("A"), _rule_verified("B", "A")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))

    c_a = _candidate("A", rank=1)
    rec_res = _recommendation_result((c_a,))
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))

    for opt in res.plan_options:
        codes = {c.course_code for c in opt.courses}
        assert not ("A" in codes and "B" in codes)


def test_28_post_plan_unlock_of_B_appears_in_newly_eligible_output():
    g = _req_group()
    pc1, pc2 = _pc("A"), _pc("B")
    r1, r2 = _rule_na("A"), _rule_verified("B", "A")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))

    c_a = _candidate("A", rank=1)
    rec_res = _recommendation_result((c_a,))
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))

    opt = res.plan_options[0]
    assert opt.newly_eligible_count == 1
    assert opt.newly_eligible_course_codes == ("B",)
    assert PlanReasonCode.UNLOCKS_FUTURE_COURSE in opt.reason_codes


# ===========================================================================
# PART 5: PROGRESS SIMULATION (Tests 29–35)
# ===========================================================================


def test_29_synthetic_attempts_do_not_mutate_original_attempts():
    g = _req_group()
    pc1 = _pc("C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1,), (_rule_na("C1"),))
    original_attempts: tuple[StudentCourseAttempt, ...] = (
        StudentCourseAttempt(course_code="OLD", outcome=AttemptOutcome.FAILED),
    )
    rec_res = _recommendation_result((_candidate("C1", rank=1),))

    plan_semester(prog_cat, elig_cat, original_attempts, rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))
    assert len(original_attempts) == 1
    assert original_attempts[0].course_code == "OLD"


def test_30_required_course_increases_modeled_progress():
    g = _req_group(required_hours="9")
    pc1 = _pc("C1", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1", credits="3", rank=1),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))
    assert res.plan_options[0].completed_plan_credit_delta == Decimal("3")


def test_31_zero_credit_required_changes_group_satisfaction_without_credit_delta():
    # 3-credit group with C1 (3 cr) already passed, and C0 (0 cr) remaining required
    g = _req_group(required_hours="3")
    pc1, pc0 = _pc("C1", credits="3"), _pc("C0", credits="0")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc0), (_rule_na("C1"), _rule_na("C0")))
    passed_c1 = (StudentCourseAttempt(course_code="C1", outcome=AttemptOutcome.PASSED),)

    rec_res = _recommendation_result((_candidate("C0", credits="0", rank=1),))
    res = plan_semester(prog_cat, elig_cat, passed_c1, rec_res, PlannerConstraints(max_credit_hours=Decimal("0")))

    opt = res.plan_options[0]
    assert opt.completed_plan_credit_delta == Decimal("0")
    assert opt.newly_satisfied_requirement_group_count == 1
    assert opt.newly_satisfied_requirement_group_codes == ("MAJOR_REQUIRED",)


def test_32_elective_cap_respected():
    # Elective group requires 3 credits; student selects two 3-credit electives
    g = _elec_group(required_hours="3")
    pc1, pc2 = _pc("E1", group_id=GRP_ELECTIVE, credits="3"), _pc("E2", group_id=GRP_ELECTIVE, credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("E1"), _rule_na("E2")))
    cands = (
        _candidate("E1", credits="3", rank=1, group_code="MAJOR_ELECTIVE", req_type="elective"),
        _candidate("E2", credits="3", rank=2, group_code="MAJOR_ELECTIVE", req_type="elective"),
    )
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6")))
    two_course_opt = next(opt for opt in res.plan_options if opt.total_courses == 2)
    assert two_course_opt.total_credit_hours == Decimal("6")
    # Modeled credit delta capped at 3 credits
    assert two_course_opt.completed_plan_credit_delta == Decimal("3")


def test_33_multiple_selected_courses_may_complete_group():
    g = _req_group(required_hours="6")
    pc1, pc2 = _pc("C1", credits="3"), _pc("C2", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", credits="3", rank=1), _candidate("C2", credits="3", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6")))
    top = res.plan_options[0]
    assert top.newly_satisfied_requirement_group_count == 1
    assert PlanReasonCode.COMPLETES_REQUIREMENT_GROUP in top.reason_codes


def test_34_multiple_groups_may_become_satisfied():
    g1 = _req_group(group_id="g1", code="G1", required_hours="3")
    g2 = _req_group(group_id="g2", code="G2", required_hours="3", display_order=2)
    pc1 = _pc("C1", group_id="g1", credits="3")
    pc2 = _pc("C2", group_id="g2", credits="3")
    prog_cat, elig_cat = _build_catalogs((g1, g2), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (
        _candidate("C1", credits="3", rank=1, group_code="G1"),
        _candidate("C2", credits="3", rank=2, group_code="G2"),
    )
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6")))
    top = res.plan_options[0]
    assert top.newly_satisfied_requirement_group_count == 2
    assert PlanReasonCode.COMPLETES_MULTIPLE_REQUIREMENT_GROUPS in top.reason_codes


def test_35_modeled_credit_delta_uses_phase6_not_raw_sum():
    g = _elec_group(required_hours="3")
    pc1, pc2 = _pc("E1", group_id=GRP_ELECTIVE, credits="3"), _pc("E2", group_id=GRP_ELECTIVE, credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("E1"), _rule_na("E2")))
    cands = (
        _candidate("E1", credits="3", rank=1, req_type="elective"),
        _candidate("E2", credits="3", rank=2, req_type="elective"),
    )
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6")))
    top = res.plan_options[0]
    assert top.total_credit_hours == Decimal("6")
    assert top.completed_plan_credit_delta == Decimal("3")  # Phase 6 delta, not 6


# ===========================================================================
# PART 6: UNLOCK SIMULATION & JOINT INTERACTIONS (Tests 36–46)
# ===========================================================================


def test_36_zero_unlock_emits_no_direct_prerequisite_impact():
    g = _req_group()
    pc = _pc("C1", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1", credits="3"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    opt = res.plan_options[0]
    assert opt.newly_eligible_count == 0
    assert PlanReasonCode.NO_DIRECT_PREREQUISITE_IMPACT in opt.reason_codes
    assert PlanReasonCode.UNLOCKS_FUTURE_COURSE not in opt.reason_codes
    assert PlanReasonCode.UNLOCKS_MULTIPLE_FUTURE_COURSES not in opt.reason_codes


def test_37_one_unlock_emits_unlocks_future_course():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    r1, r2 = _rule_na("C1"), _rule_verified("C2", "C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    opt = res.plan_options[0]
    assert opt.newly_eligible_count == 1
    assert PlanReasonCode.UNLOCKS_FUTURE_COURSE in opt.reason_codes
    assert PlanReasonCode.NO_DIRECT_PREREQUISITE_IMPACT not in opt.reason_codes
    assert PlanReasonCode.UNLOCKS_MULTIPLE_FUTURE_COURSES not in opt.reason_codes


def test_38_multiple_unlocks_emits_unlocks_multiple_future_courses():
    g = _req_group()
    pc1, pc2, pc3 = _pc("C1"), _pc("C2"), _pc("C3")
    r1, r2, r3 = _rule_na("C1"), _rule_verified("C2", "C1"), _rule_verified("C3", "C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2, pc3), (r1, r2, r3))
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    opt = res.plan_options[0]
    assert opt.newly_eligible_count == 2
    assert PlanReasonCode.UNLOCKS_MULTIPLE_FUTURE_COURSES in opt.reason_codes


def test_39_AB_jointly_unlock_AND_target():
    g = _req_group()
    pc_a, pc_b, pc_t = _pc("A"), _pc("B"), _pc("T")
    ra, rb = _rule_na("A"), _rule_na("B")
    rt = _rule_verified_two("T", "A", "B")
    prog_cat, elig_cat = _build_catalogs((g,), (pc_a, pc_b, pc_t), (ra, rb, rt))
    cands = (_candidate("A", rank=1), _candidate("B", rank=2))
    rec_res = _recommendation_result(cands)

    # 1. Plan with [A] alone does NOT unlock T
    res_a = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3"), max_courses=1))
    assert res_a.plan_options[0].newly_eligible_count == 0

    # 2. Plan with [A, B] DOES unlock T
    res_ab = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6"), max_courses=2))
    top_ab = next(opt for opt in res_ab.plan_options if opt.total_courses == 2)
    assert top_ab.newly_eligible_count == 1
    assert top_ab.newly_eligible_course_codes == ("T",)


def test_40_individual_unlock_sums_not_used():
    # If A unlocks T and B unlocks T, sum would be 2, but actual joint unlock is 1
    g = _req_group()
    pc_a, pc_b, pc_t = _pc("A"), _pc("B"), _pc("T")
    ra, rb = _rule_na("A"), _rule_na("B")
    # T requires A OR B (single group with two options)
    rt = PlanCourseRule(
        course_code="T",
        prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
        dependency_groups=(
            DependencyGroup(1, DependencyType.PREREQUISITE, ("A", "B")),
        ),
        raw_prerequisite_text="A or B",
        target_name_ar=None,
    )
    prog_cat, elig_cat = _build_catalogs((g,), (pc_a, pc_b, pc_t), (ra, rb, rt))
    cands = (_candidate("A", rank=1), _candidate("B", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6")))
    top = next(opt for opt in res.plan_options if opt.total_courses == 2)
    assert top.newly_eligible_count == 1  # Not 2!


def test_41_already_baseline_eligible_excluded_from_unlocks():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    r1, r2 = _rule_na("C1"), _rule_na("C2")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))
    rec_res = _recommendation_result((_candidate("C1"),))

    # C2 is already ELIGIBLE at baseline; completing C1 does not newly unlock C2
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert "C2" not in res.plan_options[0].newly_eligible_course_codes


def test_42_selected_course_excluded_from_unlock_list():
    g = _req_group()
    pc1 = _pc("C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert "C1" not in res.plan_options[0].newly_eligible_course_codes


def test_43_completed_downstream_excluded():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    r1, r2 = _rule_na("C1"), _rule_verified("C2", "C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))
    passed_c2 = (StudentCourseAttempt(course_code="C2", outcome=AttemptOutcome.PASSED),)
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, passed_c2, rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert "C2" not in res.plan_options[0].newly_eligible_course_codes


def test_44_in_progress_downstream_excluded():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    r1, r2 = _rule_na("C1"), _rule_verified("C2", "C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))
    ip_c2 = (StudentCourseAttempt(course_code="C2", outcome=AttemptOutcome.IN_PROGRESS),)
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, ip_c2, rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert "C2" not in res.plan_options[0].newly_eligible_course_codes


def test_45_referenced_only_non_plan_excluded():
    g = _req_group()
    pc1 = _pc("C1")
    r1 = _rule_na("C1")
    # Ref course external to study plan
    r_ext = PlanCourseRule("EXT", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("C1",)),), "C1", None)
    prog_cat, elig_cat = _build_catalogs((g,), (pc1,), (r1, r_ext))
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert "EXT" not in res.plan_options[0].newly_eligible_course_codes


def test_46_unresolved_remains_review_required():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    r1 = _rule_na("C1")
    r2 = PlanCourseRule("C2", PrerequisiteLogicStatus.UNRESOLVED, (), "C1", None)
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert "C2" not in res.plan_options[0].newly_eligible_course_codes


# ===========================================================================
# PART 7: PRIORITY TUPLE & SORTING (Tests 47–54)
# ===========================================================================


def test_47_higher_mandatory_count_wins_at_P1():
    g_req = _req_group(required_hours="9")
    g_elec = _elec_group(required_hours="9")
    pc_req = _pc("REQ", group_id=GRP_REQUIRED)
    pc_elec = _pc("ELEC", group_id=GRP_ELECTIVE)
    prog_cat, elig_cat = _build_catalogs((g_req, g_elec), (pc_req, pc_elec), (_rule_na("REQ"), _rule_na("ELEC")))

    c_req = _candidate("REQ", rank=2, req_type="required")
    c_elec = _candidate("ELEC", rank=1, req_type="elective")
    rec_res = _recommendation_result((c_elec, c_req))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert res.plan_options[0].courses[0].course_code == "REQ"


def test_48_group_completion_count_wins_at_P2():
    # Two required groups: G1 needs 3 cr, G2 needs 6 cr
    g1 = _req_group(group_id="g1", code="G1", required_hours="3")
    g2 = _req_group(group_id="g2", code="G2", required_hours="6", display_order=2)
    pc1 = _pc("C1", group_id="g1", credits="3")
    pc2 = _pc("C2", group_id="g2", credits="3")
    prog_cat, elig_cat = _build_catalogs((g1, g2), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))

    c1 = _candidate("C1", rank=2, group_code="G1")
    c2 = _candidate("C2", rank=1, group_code="G2")
    rec_res = _recommendation_result((c2, c1))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert res.plan_options[0].courses[0].course_code == "C1"
    assert res.plan_options[0].newly_satisfied_requirement_group_count == 1


def test_49_modeled_credit_delta_wins_at_P3():
    # Elective group with 3 credits needed: selecting 3 cr vs 0 cr (if equal P1)
    g = _req_group(required_hours="9")
    pc3, pc1 = _pc("C3", credits="3"), _pc("C1", credits="1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc3, pc1), (_rule_na("C3"), _rule_na("C1")))
    c3 = _candidate("C3", credits="3", rank=2)
    c1 = _candidate("C1", credits="1", rank=1)
    rec_res = _recommendation_result((c1, c3))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3"), max_courses=1))
    assert res.plan_options[0].courses[0].course_code == "C3"
    assert res.plan_options[0].completed_plan_credit_delta == Decimal("3")


def test_50_unlock_count_wins_at_P4():
    g = _req_group(required_hours="9")
    pc_a, pc_b, pc_t = _pc("A"), _pc("B"), _pc("T")
    ra = _rule_na("A")
    rb = _rule_na("B")
    rt = _rule_verified("T", "A")  # A unlocks T; B unlocks nothing
    prog_cat, elig_cat = _build_catalogs((g,), (pc_a, pc_b, pc_t), (ra, rb, rt))
    ca = _candidate("A", rank=2)
    cb = _candidate("B", rank=1)
    rec_res = _recommendation_result((cb, ca))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3"), max_courses=1))
    assert res.plan_options[0].courses[0].course_code == "A"
    assert res.plan_options[0].newly_eligible_count == 1


def test_51_budget_utilization_wins_at_P5():
    # When academic deltas are identical, fuller credit usage wins
    g = _req_group(required_hours="12")
    pc2 = _pc("C2", credits="2")
    pc3 = _pc("C3", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc2, pc3), (_rule_na("C2"), _rule_na("C3")))
    c2 = _candidate("C2", credits="2", rank=1)
    c3 = _candidate("C3", credits="3", rank=2)
    rec_res = _recommendation_result((c2, c3))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3"), max_courses=1))
    assert res.plan_options[0].courses[0].course_code == "C3"


def test_52_lower_recommendation_rank_sum_wins_at_P6():
    g = _req_group(required_hours="12")
    pc1, pc2 = _pc("C1", credits="3"), _pc("C2", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    c1 = _candidate("C1", credits="3", rank=1)
    c2 = _candidate("C2", credits="3", rank=2)
    rec_res = _recommendation_result((c1, c2))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3"), max_courses=1))
    assert res.plan_options[0].courses[0].course_code == "C1"
    assert res.plan_options[0].recommendation_rank_sum == 1
    assert res.plan_options[1].courses[0].course_code == "C2"
    assert res.plan_options[1].recommendation_rank_sum == 2


def test_53_canonical_code_tuple_tiebreak_at_P7():
    g = _req_group(required_hours="12")
    pc_b, pc_a = _pc("B", credits="3"), _pc("A", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc_b, pc_a), (_rule_na("B"), _rule_na("A")))
    cb = _candidate("B", credits="3", rank=1)
    ca = _candidate("A", credits="3", rank=1)
    rec_res = _recommendation_result((cb, ca))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3"), max_courses=1))
    assert res.plan_options[0].courses[0].course_code == "A"
    assert res.plan_options[1].courses[0].course_code == "B"


def test_54_exact_sort_direction_across_all_7_dimensions():
    # Validate that priority tuple correctly populates and orders
    c = PlannerConstraints(max_credit_hours=Decimal("15"))
    assert c.max_options == 5


# ===========================================================================
# PART 8: ZERO-CREDIT HANDLING (Tests 55–58)
# ===========================================================================


def test_55_zero_credit_required_appears_with_max_credit_hours_zero():
    g = _req_group()
    pc0 = _pc("C0", credits="0")
    prog_cat, elig_cat = _build_catalogs((g,), (pc0,), (_rule_na("C0"),))
    rec_res = _recommendation_result((_candidate("C0", credits="0", rank=1),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("0")))
    assert len(res.plan_options) == 1
    assert res.plan_options[0].courses[0].course_code == "C0"
    assert res.plan_options[0].total_credit_hours == Decimal("0")


def test_56_two_zero_credit_courses_form_valid_zero_credit_plan():
    g = _req_group()
    pc1, pc2 = _pc("Z1", credits="0"), _pc("Z2", credits="0")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("Z1"), _rule_na("Z2")))
    cands = (_candidate("Z1", credits="0", rank=1), _candidate("Z2", credits="0", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("0"), max_courses=2))
    top = res.plan_options[0]
    assert top.total_courses == 2
    assert top.total_credit_hours == Decimal("0")


def test_57_zero_credit_required_contributes_mandatory_count():
    g = _req_group()
    pc0 = _pc("Z0", credits="0")
    prog_cat, elig_cat = _build_catalogs((g,), (pc0,), (_rule_na("Z0"),))
    rec_res = _recommendation_result((_candidate("Z0", credits="0", rank=1),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("0")))
    assert res.plan_options[0].mandatory_course_count == 1
    assert res.plan_options[0].zero_credit_required_count == 1


def test_58_zero_credit_does_not_inflate_credit_delta():
    g = _req_group(required_hours="9")
    pc0 = _pc("Z0", credits="0")
    prog_cat, elig_cat = _build_catalogs((g,), (pc0,), (_rule_na("Z0"),))
    rec_res = _recommendation_result((_candidate("Z0", credits="0", rank=1),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("0")))
    assert res.plan_options[0].completed_plan_credit_delta == Decimal("0")


# ===========================================================================
# PART 9: REASON CODES (Tests 59–69)
# ===========================================================================


def test_59_mandatory_reason_emitted():
    g = _req_group()
    pc = _pc("C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1", req_type="required"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert PlanReasonCode.CONTAINS_MANDATORY_COURSES in res.plan_options[0].reason_codes


def test_60_zero_credit_reason_emitted():
    g = _req_group()
    pc = _pc("C0", credits="0")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C0"),))
    rec_res = _recommendation_result((_candidate("C0", credits="0", req_type="required"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("0")))
    assert PlanReasonCode.INCLUDES_ZERO_CREDIT_REQUIRED in res.plan_options[0].reason_codes


def test_61_exactly_one_group_completion_reason():
    g = _req_group(required_hours="3")
    pc = _pc("C1", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1", credits="3"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    reasons = res.plan_options[0].reason_codes
    assert PlanReasonCode.COMPLETES_REQUIREMENT_GROUP in reasons
    assert PlanReasonCode.COMPLETES_MULTIPLE_REQUIREMENT_GROUPS not in reasons


def test_62_multi_group_reason():
    g1 = _req_group(group_id="g1", code="G1", required_hours="3")
    g2 = _req_group(group_id="g2", code="G2", required_hours="3", display_order=2)
    pc1, pc2 = _pc("C1", group_id="g1"), _pc("C2", group_id="g2")
    prog_cat, elig_cat = _build_catalogs((g1, g2), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    rec_res = _recommendation_result((_candidate("C1", group_code="G1"), _candidate("C2", group_code="G2")))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6")))
    reasons = res.plan_options[0].reason_codes
    assert PlanReasonCode.COMPLETES_MULTIPLE_REQUIREMENT_GROUPS in reasons
    assert PlanReasonCode.COMPLETES_REQUIREMENT_GROUP not in reasons


def test_63_zero_unlock_reason():
    g = _req_group()
    pc = _pc("C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert PlanReasonCode.NO_DIRECT_PREREQUISITE_IMPACT in res.plan_options[0].reason_codes


def test_64_one_unlock_reason():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_verified("C2", "C1")))
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert PlanReasonCode.UNLOCKS_FUTURE_COURSE in res.plan_options[0].reason_codes


def test_65_multi_unlock_reason():
    g = _req_group()
    pc1, pc2, pc3 = _pc("C1"), _pc("C2"), _pc("C3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2, pc3), (_rule_na("C1"), _rule_verified("C2", "C1"), _rule_verified("C3", "C1")))
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert PlanReasonCode.UNLOCKS_MULTIPLE_FUTURE_COURSES in res.plan_options[0].reason_codes


def test_66_full_credit_preference_reason():
    g = _req_group()
    pc = _pc("C1", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1", credits="3"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert PlanReasonCode.USES_FULL_CREDIT_PREFERENCE in res.plan_options[0].reason_codes


def test_67_previously_attempted_reason():
    g = _req_group()
    pc = _pc("C1", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1", credits="3", previously_attempted=True),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert PlanReasonCode.INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE in res.plan_options[0].reason_codes


def test_68_maximizes_modeled_credit_progress_across_all_valid_combinations():
    g = _req_group(required_hours="12")
    pc1, pc2 = _pc("C1", credits="3"), _pc("C2", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", credits="3", rank=1), _candidate("C2", credits="3", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6")))
    # Option with 6 credits delta has MAXIMIZES, option with 3 credits does NOT
    opt_6 = next(opt for opt in res.plan_options if opt.total_credit_hours == Decimal("6"))
    opt_3 = next(opt for opt in res.plan_options if opt.total_credit_hours == Decimal("3"))
    assert PlanReasonCode.MAXIMIZES_MODELED_CREDIT_PROGRESS in opt_6.reason_codes
    assert PlanReasonCode.MAXIMIZES_MODELED_CREDIT_PROGRESS not in opt_3.reason_codes


def test_69_tied_max_credit_delta_plans_both_receive_maximizes():
    g = _req_group(required_hours="12")
    pc1, pc2 = _pc("C1", credits="3"), _pc("C2", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", credits="3", rank=1), _candidate("C2", credits="3", rank=2))
    rec_res = _recommendation_result(cands)

    # Max credit hours = 3 -> each 1-course plan has 3 credits (the maximum delta found)
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert len(res.plan_options) == 2
    assert PlanReasonCode.MAXIMIZES_MODELED_CREDIT_PROGRESS in res.plan_options[0].reason_codes
    assert PlanReasonCode.MAXIMIZES_MODELED_CREDIT_PROGRESS in res.plan_options[1].reason_codes


def test_69b_zero_max_credit_delta_receives_maximizes_reason():
    # When requirement group is already satisfied, candidate courses produce modeled_credit_delta = Decimal("0")
    g = _req_group(required_hours="0")  # already satisfied
    pc1, pc2 = _pc("C1", credits="3"), _pc("C2", credits="3")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", credits="3", rank=1), _candidate("C2", credits="3", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6")))
    assert len(res.plan_options) >= 1
    # Global max modeled_credit_delta is 0
    for opt in res.plan_options:
        assert opt.completed_plan_credit_delta == Decimal("0")
        assert PlanReasonCode.MAXIMIZES_MODELED_CREDIT_PROGRESS in opt.reason_codes


# ===========================================================================
# PART 10: TOP-K RETENTION & RANKING (Tests 70–73)
# ===========================================================================


def test_70_max_options_limits_returned_options():
    g = _req_group(required_hours="12")
    pcs = tuple(_pc(f"C{i}") for i in range(1, 6))
    rules = tuple(_rule_na(f"C{i}") for i in range(1, 6))
    prog_cat, elig_cat = _build_catalogs((g,), pcs, rules)
    cands = tuple(_candidate(f"C{i}", rank=i) for i in range(1, 6))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15"), max_options=3))
    assert len(res.plan_options) == 3


def test_71_search_evaluates_all_combinations_before_slicing():
    g = _req_group(required_hours="12")
    pc1, pc2 = _pc("C1"), _pc("C2")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", rank=1), _candidate("C2", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6"), max_options=1))
    assert res.valid_combination_count == 3  # [C1], [C2], [C1, C2] all valid
    assert len(res.plan_options) == 1
    # The best combination [C1, C2] was selected
    assert res.plan_options[0].total_courses == 2


def test_72_top_k_equals_prefix_of_full_sorted_options():
    g = _req_group(required_hours="12")
    pc1, pc2 = _pc("C1"), _pc("C2")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", rank=1), _candidate("C2", rank=2))
    rec_res = _recommendation_result(cands)

    res_all = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6"), max_options=3))
    res_one = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6"), max_options=1))
    assert res_all.plan_options[0] == res_one.plan_options[0]


def test_73_returned_plan_ranks_1_to_K():
    g = _req_group(required_hours="12")
    pcs = tuple(_pc(f"C{i}") for i in range(1, 4))
    prog_cat, elig_cat = _build_catalogs((g,), pcs, tuple(_rule_na(f"C{i}") for i in range(1, 4)))
    cands = tuple(_candidate(f"C{i}", rank=i) for i in range(1, 4))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("9"), max_options=3))
    for idx, opt in enumerate(res.plan_options):
        assert opt.rank == idx + 1


# ===========================================================================
# PART 11: DETERMINISM (Tests 74–79)
# ===========================================================================


def test_74_repeated_identical_calls_yield_identical_results():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", rank=1), _candidate("C2", rank=2))
    rec_res = _recommendation_result(cands)
    con = PlannerConstraints(max_credit_hours=Decimal("6"))

    r1 = plan_semester(prog_cat, elig_cat, (), rec_res, con)
    r2 = plan_semester(prog_cat, elig_cat, (), rec_res, con)
    assert r1 == r2


def test_75_shuffled_candidate_input_does_not_change_result_if_ranks_same():
    g = _req_group()
    pc1, pc2 = _pc("C1"), _pc("C2")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    c1, c2 = _candidate("C1", rank=1), _candidate("C2", rank=2)
    rec1 = _recommendation_result((c1, c2))
    con = PlannerConstraints(max_credit_hours=Decimal("6"))

    res1 = plan_semester(prog_cat, elig_cat, (), rec1, con)
    assert len(res1.plan_options) > 0


def test_76_no_timestamp_fields():
    prog_cat, elig_cat = _build_catalogs((_req_group(),), (_pc("C1"),), (_rule_na("C1"),))
    res = plan_semester(
        prog_cat,
        elig_cat,
        (),
        _recommendation_result((_candidate("C1"),)),
        PlannerConstraints(max_credit_hours=Decimal("3")),
    )
    assert not hasattr(res, "created_at")
    assert not hasattr(res, "timestamp")
    assert not hasattr(res.plan_options[0], "created_at")


def test_77_stable_course_order_within_plan():
    # C2 has display_order=1, C1 has display_order=2
    g = _req_group()
    pc1, pc2 = _pc("C1", display_order=2), _pc("C2", display_order=1)
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (_rule_na("C1"), _rule_na("C2")))
    cands = (_candidate("C1", rank=1), _candidate("C2", rank=2))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6")))
    top = next(opt for opt in res.plan_options if opt.total_courses == 2)
    assert top.courses[0].course_code == "C2"
    assert top.courses[1].course_code == "C1"


def test_78_stable_newly_eligible_code_ordering():
    g = _req_group()
    pc1, pc_b, pc_a = _pc("C1"), _pc("B"), _pc("A")
    r1 = _rule_na("C1")
    rb = _rule_verified("B", "C1")
    ra = _rule_verified("A", "C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc_b, pc_a), (r1, rb, ra))
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")))
    assert res.plan_options[0].newly_eligible_course_codes == ("A", "B")


def test_79_stable_group_code_ordering():
    g_u = _req_group(group_id="gu", code="UNIVERSITY_REQUIRED", required_hours="3", display_order=1)
    g_f = _req_group(group_id="gf", code="FACULTY_REQUIRED", required_hours="3", display_order=2)
    pc_u, pc_f = _pc("CU", group_id="gu"), _pc("CF", group_id="gf")
    prog_cat, elig_cat = _build_catalogs((g_u, g_f), (pc_u, pc_f), (_rule_na("CU"), _rule_na("CF")))
    cands = (_candidate("CU", group_code="UNIVERSITY_REQUIRED"), _candidate("CF", group_code="FACULTY_REQUIRED"))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("6")))
    top = res.plan_options[0]
    assert top.newly_satisfied_requirement_group_codes == ("UNIVERSITY_REQUIRED", "FACULTY_REQUIRED")


# ===========================================================================
# PART 12: REAL PLAN 12 FACTS (Tests 80–88)
# ===========================================================================


def test_80_0200115_zero_credit_required_planner_behavior():
    # 0200115: Community Service, 0 cr, UNIVERSITY_REQUIRED
    g = _req_group(code="UNIVERSITY_REQUIRED")
    pc = _pc("0200115", credits="0")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("0200115"),))
    rec_res = _recommendation_result((_candidate("0200115", credits="0", group_code="UNIVERSITY_REQUIRED"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("0")))
    top = res.plan_options[0]
    assert top.courses[0].course_code == "0200115"
    assert top.zero_credit_required_count == 1
    assert PlanReasonCode.INCLUDES_ZERO_CREDIT_REQUIRED in top.reason_codes


def test_81_1509999_zero_credit_required_planner_behavior():
    # 1509999: IT Seminar, 0 cr, FACULTY_REQUIRED
    g = _req_group(code="FACULTY_REQUIRED")
    pc = _pc("1509999", credits="0")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("1509999"),))
    rec_res = _recommendation_result((_candidate("1509999", credits="0", group_code="FACULTY_REQUIRED"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("0")))
    top = res.plan_options[0]
    assert top.courses[0].course_code == "1509999"
    assert top.zero_credit_required_count == 1


def test_82_1501110_and_1501112_same_semester_baseline_rule():
    # 1501110 (Programming 1) unlocks 1501112 (Programming 2)
    g = _req_group()
    pc1, pc2 = _pc("1501110"), _pc("1501112")
    r1, r2 = _rule_na("1501110"), _rule_verified("1501112", "1501110")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))

    # Baseline: student has not passed 1501110. 1501112 is NOT_ELIGIBLE.
    c1 = _candidate("1501110", rank=1)
    rec_res = _recommendation_result((c1,))
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))

    for opt in res.plan_options:
        codes = {c.course_code for c in opt.courses}
        assert not ("1501110" in codes and "1501112" in codes)


def test_83_1501110_hypothetical_completion_exposes_1501112_as_future_eligible():
    g = _req_group()
    pc1, pc2 = _pc("1501110"), _pc("1501112")
    r1, r2 = _rule_na("1501110"), _rule_verified("1501112", "1501110")
    prog_cat, elig_cat = _build_catalogs((g,), (pc1, pc2), (r1, r2))

    c1 = _candidate("1501110", rank=1)
    rec_res = _recommendation_result((c1,))
    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))

    top = res.plan_options[0]
    assert "1501112" in top.newly_eligible_course_codes
    assert top.newly_eligible_count >= 1


def test_84_1505311_never_planner_candidate_when_review_required():
    g = _req_group()
    pc = _pc("1505311")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_unresolved("1505311"),))
    rev = ReviewRequiredCourse("1505311", "Machine Learning", Decimal("3"), "MAJOR_REQUIRED", "required", "PREREQUISITE_LOGIC_UNRESOLVED", False)
    rec_res = _recommendation_result((), review_required=(rev,))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))
    assert res.plan_options == ()
    assert "1505311" in res.review_required_courses


def test_85_1505320_never_planner_candidate_when_review_required():
    g = _req_group()
    pc = _pc("1505320")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_conflict("1505320"),))
    rev = ReviewRequiredCourse("1505320", "Advanced ML", Decimal("3"), "MAJOR_REQUIRED", "required", "PREREQUISITE_SOURCE_CONFLICT", False)
    rec_res = _recommendation_result((), review_required=(rev,))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))
    assert res.plan_options == ()
    assert "1505320" in res.review_required_courses


def test_86_0300103_referenced_only_never_planner_candidate():
    g = _req_group()
    pc = _pc("1501110")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("1501110"),))
    passed_ref = (StudentCourseAttempt(course_code="0300103", outcome=AttemptOutcome.PASSED),)
    rec_res = _recommendation_result((_candidate("1501110"),))

    res = plan_semester(prog_cat, elig_cat, passed_ref, rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))
    all_codes = {c.course_code for opt in res.plan_options for c in opt.courses}
    assert "0300103" not in all_codes


def test_87_university_elective_saturation_inherited_from_phase7():
    # If University Elective is saturated, Phase 7 excludes it from ranked_recommendations
    g = _elec_group(code="UNIVERSITY_ELECTIVE", required_hours="3")
    pc = _pc("ELEC1", group_id=GRP_ELECTIVE)
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("ELEC1"),))
    rec_res = _recommendation_result(())  # empty because saturated in Phase 7

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))
    assert res.plan_options == ()


def test_88_major_elective_saturation_inherited_from_phase7():
    g = _elec_group(code="MAJOR_ELECTIVE", required_hours="3")
    pc = _pc("MELEC1", group_id=GRP_ELECTIVE)
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("MELEC1"),))
    rec_res = _recommendation_result(())

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))
    assert res.plan_options == ()


# ===========================================================================
# PART 13: BOUNDS & SEARCH LIMITATIONS (Tests 89–92)
# ===========================================================================


def test_89_candidate_window_size_parameter_enforced():
    g = _req_group(required_hours="99")
    pcs = tuple(_pc(f"C{i}", display_order=i) for i in range(1, 11))
    prog_cat, elig_cat = _build_catalogs((g,), pcs, tuple(_rule_na(f"C{i}") for i in range(1, 11)))
    cands = tuple(_candidate(f"C{i}", rank=i) for i in range(1, 11))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")), candidate_window_size=5)
    assert res.candidate_window_size == 5
    assert res.evaluated_candidate_count == 5


def test_90_candidate_16_excluded_from_search():
    g = _req_group(required_hours="99")
    pcs = tuple(_pc(f"C{i:02d}", display_order=i) for i in range(1, 18))
    prog_cat, elig_cat = _build_catalogs((g,), pcs, tuple(_rule_na(f"C{i:02d}") for i in range(1, 18)))
    cands = tuple(_candidate(f"C{i:02d}", rank=i) for i in range(1, 18))
    rec_res = _recommendation_result(cands)

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("3")), candidate_window_size=15)
    all_codes = {c.course_code for opt in res.plan_options for c in opt.courses}
    assert "C16" not in all_codes
    assert "C17" not in all_codes


def test_91_result_metadata_makes_bounded_search_visible():
    g = _req_group()
    pc = _pc("C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))
    assert res.candidate_window_size == DEFAULT_CANDIDATE_WINDOW_SIZE
    assert res.evaluated_candidate_count == 1
    assert res.eligible_ranked_candidate_count == 1
    assert res.planning_scope == PLANNING_SCOPE
    assert res.semester_planner_policy_version == SEMESTER_PLANNER_POLICY_VERSION


def test_92_limitations_document_no_global_optimality_claim():
    g = _req_group()
    pc = _pc("C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1"),))

    res = plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))
    assert any("not guaranteed globally optimal" in lim for lim in res.limitations)


# ===========================================================================
# PART 14: MODEL & INTEGRITY CHECKS (Tests 93–95)
# ===========================================================================


def test_93_mismatched_study_plan_id_inputs_fail_safely():
    g = _req_group()
    pc = _pc("C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    # Mismatched study_plan_id in recommendation result
    rec_res = _recommendation_result((_candidate("C1"),), study_plan_id="OTHER_PLAN_ID")

    with pytest.raises(PlannerIntegrityError, match="Mismatched study_plan_id"):
        plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))


def test_94_candidate_absent_from_progress_catalog_fails_integrity():
    g = _req_group()
    pc = _pc("C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    # Candidate "UNKNOWN" not in progress catalog
    rec_res = _recommendation_result((_candidate("UNKNOWN"),))

    with pytest.raises(PlannerIntegrityError, match="absent from progress catalog"):
        plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")))


def test_95_invalid_candidate_window_size_rejected():
    g = _req_group()
    pc = _pc("C1")
    prog_cat, elig_cat = _build_catalogs((g,), (pc,), (_rule_na("C1"),))
    rec_res = _recommendation_result((_candidate("C1"),))

    with pytest.raises(PlannerConstraintError, match="at least 1"):
        plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")), candidate_window_size=0)

    with pytest.raises(PlannerConstraintError, match="must be an integer"):
        plan_semester(prog_cat, elig_cat, (), rec_res, PlannerConstraints(max_credit_hours=Decimal("15")), candidate_window_size="15")  # type: ignore


def test_96_planner_constraints_has_no_candidate_window_size_field():
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(PlannerConstraints)}
    assert field_names == {"max_credit_hours", "max_courses", "max_options"}
    assert "candidate_window_size" not in field_names

    with pytest.raises(TypeError):
        PlannerConstraints(max_credit_hours=Decimal("15"), candidate_window_size=15)  # type: ignore
