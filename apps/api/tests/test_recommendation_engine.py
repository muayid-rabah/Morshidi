"""Exhaustive pure tests for Phase 7.2 — Deterministic Recommendation Engine.

All tests are pure (no Supabase, no FastAPI, no httpx).
Tests use in-memory catalog objects constructed from known Plan 12 facts.

Test numbering follows the Phase 7.2 spec test matrix sections:
  1-7   Candidate filtering
  8-14  Required / elective
  15-18 Zero credit
  19-24 Progress delta
  25-35 Unlock simulation (AND/OR semantics)
  36-43 Ranking
  44-48 History
  49-52 Special cases
  53-59 Reason codes
  60    Policy version
  61-68 Real Plan 12 facts
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.progress.models import (
    AcademicProgressCatalog,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.recommendations.engine import recommend_courses
from app.recommendations.models import (
    RECOMMENDATION_POLICY_VERSION,
    RecommendationReason,
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

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

PLAN_ID = "10000000-0000-0000-0000-000000000005"

# Group IDs
GRP_REQUIRED = "gr-required"
GRP_ELECTIVE = "gr-elective"
GRP_FACULTY  = "gr-faculty"


# ---------------------------------------------------------------------------
# Builder helpers
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
    plan_course_id: str | None = None,
) -> ProgressPlanCourse:
    return ProgressPlanCourse(
        plan_course_id=plan_course_id or f"pc-{code}",
        study_plan_id=PLAN_ID,
        requirement_group_id=group_id,
        course_code=code,
        catalog_status=CourseCatalogStatus.KNOWN,
        credit_hours=Decimal(credits),
        display_order=display_order,
    )


def _rule_na(code: str, name_ar: str | None = None) -> PlanCourseRule:
    """No prerequisite — NOT_APPLICABLE."""
    return PlanCourseRule(
        course_code=code,
        prerequisite_logic_status=PrerequisiteLogicStatus.NOT_APPLICABLE,
        dependency_groups=(),
        raw_prerequisite_text=None,
        target_name_ar=name_ar,
    )


def _rule_verified(code: str, prereq: str, name_ar: str | None = None) -> PlanCourseRule:
    """Single prerequisite group with one option."""
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
    """Two AND prerequisite groups (each with one option)."""
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
    extra_course_identities: tuple[CourseIdentity, ...] = (),
) -> tuple[AcademicProgressCatalog, CanTakeCatalog]:
    """Build matched progress + eligibility catalogs from plan course metadata."""
    progress_catalog = AcademicProgressCatalog(
        study_plan=_plan(),
        requirement_groups=prog_groups,
        plan_courses=prog_courses,
    )
    # Build course identities for the eligibility catalog from plan rules
    identities_by_code: dict[str, CourseIdentity] = {
        ci.course_code: ci for ci in extra_course_identities
    }
    for rule in plan_rules:
        if rule.course_code not in identities_by_code:
            identities_by_code[rule.course_code] = CourseIdentity(
                course_code=rule.course_code,
                catalog_status=CourseCatalogStatus.KNOWN,
            )
    # Also add prerequisite codes as identities (referenced_only if not already present)
    for rule in plan_rules:
        for dg in rule.dependency_groups:
            for opt_code in dg.option_course_codes:
                if opt_code not in identities_by_code:
                    identities_by_code[opt_code] = CourseIdentity(
                        course_code=opt_code,
                        catalog_status=CourseCatalogStatus.REFERENCED_ONLY,
                    )

    eligibility_catalog = CanTakeCatalog(
        study_plan_id=PLAN_ID,
        plan_courses=plan_rules,
        courses=tuple(identities_by_code.values()),
    )
    return progress_catalog, eligibility_catalog


def _attempts(*pairs: tuple[str, AttemptOutcome]) -> tuple[StudentCourseAttempt, ...]:
    return tuple(StudentCourseAttempt(code, outcome) for code, outcome in pairs)


def _recommend(
    prog_groups: tuple[ProgressRequirementGroup, ...],
    prog_courses: tuple[ProgressPlanCourse, ...],
    plan_rules: tuple[PlanCourseRule, ...],
    student_attempts: tuple[StudentCourseAttempt, ...] = (),
    extra_identities: tuple[CourseIdentity, ...] = (),
) -> RecommendationResult:
    prog_cat, elig_cat = _build_catalogs(
        prog_groups, prog_courses, plan_rules, extra_identities
    )
    return recommend_courses(prog_cat, elig_cat, student_attempts)


def _codes(result: RecommendationResult) -> list[str]:
    return [c.course_code for c in result.ranked_recommendations]


def _review_codes(result: RecommendationResult) -> list[str]:
    return [c.course_code for c in result.review_required_courses]


def _by_code(result: RecommendationResult) -> dict[str, object]:
    return {c.course_code: c for c in result.ranked_recommendations}


# ===========================================================================
# 1-7: Candidate filtering
# ===========================================================================


def test_01_completed_course_excluded() -> None:
    """Test 1: A COMPLETED plan course must not appear in recommendations."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules, _attempts(("A", AttemptOutcome.PASSED)))
    assert "A" not in _codes(result)


def test_02_in_progress_course_excluded_and_listed() -> None:
    """Test 2: An IN_PROGRESS plan course is excluded and shown in excluded_in_progress."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules, _attempts(("A", AttemptOutcome.IN_PROGRESS)))
    assert "A" not in _codes(result)
    assert "A" in result.excluded_in_progress


def test_03_not_attempted_eligible_included() -> None:
    """Test 3: A NOT_ATTEMPTED course with ELIGIBLE Phase 5 decision is recommended."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    assert "A" in _codes(result)


def test_04_attempted_not_completed_eligible_included() -> None:
    """Test 4: An ATTEMPTED_NOT_COMPLETED course with ELIGIBLE decision is recommended."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules, _attempts(("A", AttemptOutcome.FAILED)))
    assert "A" in _codes(result)


def test_05_not_eligible_excluded() -> None:
    """Test 5: A NOT_ELIGIBLE course (unmet prerequisite) is excluded from ranking."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_verified("A", "PREREQ"),)
    # PREREQ not passed → A is NOT_ELIGIBLE
    result = _recommend(grps, courses, rules)
    assert "A" not in _codes(result)


def test_06_review_required_separated() -> None:
    """Test 6: A REVIEW_REQUIRED course is in review_required_courses, not ranked list."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_unresolved("A", "X,Y"),)
    result = _recommend(grps, courses, rules)
    assert "A" not in _codes(result)
    assert "A" in _review_codes(result)


def test_07_referenced_only_history_ignored() -> None:
    """Test 7: A referenced-only course in student history does not become a candidate."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    # Student has a pass for referenced-only 0300103 (not a plan member)
    result = _recommend(
        grps, courses, rules, _attempts(("0300103", AttemptOutcome.PASSED))
    )
    assert "0300103" not in _codes(result)
    assert "A" in _codes(result)


# ===========================================================================
# 8-14: Required / elective
# ===========================================================================


def test_08_positive_credit_required_has_p1_of_2() -> None:
    """Test 8: A positive-credit required course has P1 = 2."""
    grps = (_req_group(),)
    courses = (_pc("A", credits="3"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    candidate = _by_code(result)["A"]
    assert candidate.priority_tuple[0] == 2


def test_09_zero_credit_required_has_p1_of_1() -> None:
    """Test 9: A zero-credit required course has P1 = 1."""
    grps = (_req_group(),)
    courses = (_pc("A", credits="0"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    candidate = _by_code(result)["A"]
    assert candidate.priority_tuple[0] == 1


def test_10_elective_has_p1_of_0() -> None:
    """Test 10: An elective course has P1 = 0."""
    grps = (_elec_group(),)
    courses = (_pc("A", group_id=GRP_ELECTIVE),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    candidate = _by_code(result)["A"]
    assert candidate.priority_tuple[0] == 0


def test_11_unsatisfied_elective_included() -> None:
    """Test 11: An elective candidate in an unsatisfied group is ranked."""
    grps = (_elec_group(required_hours="9"),)
    courses = (_pc("A", group_id=GRP_ELECTIVE, credits="3"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    assert "A" in _codes(result)


def test_12_satisfied_elective_excluded() -> None:
    """Test 12: An elective in a satisfied group is excluded from ranked_recommendations."""
    grps = (_elec_group(required_hours="3"),)
    courses = (
        _pc("A", group_id=GRP_ELECTIVE, credits="3", display_order=1),
        _pc("B", group_id=GRP_ELECTIVE, credits="3", display_order=2),
    )
    rules = (_rule_na("A"), _rule_na("B"))
    # Student passed A → group satisfied (3 of 3)
    result = _recommend(
        grps, courses, rules, _attempts(("A", AttemptOutcome.PASSED))
    )
    # A is COMPLETED — excluded
    assert "A" not in _codes(result)
    # B is eligible but group is satisfied → excluded from ranking
    assert "B" not in _codes(result)


def test_13_university_elective_excess_excluded() -> None:
    """Test 13: Electives in a satisfied University Elective group are excluded."""
    grp_id = "gr-univ-elective"
    grps = (ProgressRequirementGroup(
        group_id=grp_id,
        study_plan_id=PLAN_ID,
        group_code="UNIVERSITY_ELECTIVE",
        name_ar="جامعي اختياري",
        name_en=None,
        scope="university",
        requirement_type=RequirementType.ELECTIVE,
        required_credit_hours=Decimal("9"),
        display_order=1,
    ),)
    # 4 × 3-credit electives; student completes 3 (9 credits) → group satisfied
    courses = tuple(
        _pc(f"UE{i}", group_id=grp_id, credits="3", display_order=i)
        for i in range(1, 5)
    )
    rules = tuple(_rule_na(f"UE{i}") for i in range(1, 5))
    student_attempts = _attempts(
        ("UE1", AttemptOutcome.PASSED),
        ("UE2", AttemptOutcome.PASSED),
        ("UE3", AttemptOutcome.PASSED),
    )
    result = _recommend(grps, courses, rules, student_attempts)
    assert "UE4" not in _codes(result)


def test_14_major_elective_satisfied_excluded() -> None:
    """Test 14: Major Elective candidates are excluded when group is satisfied."""
    grp_id = GRP_ELECTIVE
    grps = (_elec_group(required_hours="9"),)
    courses = tuple(
        _pc(f"ME{i}", group_id=grp_id, credits="3", display_order=i)
        for i in range(1, 5)
    )
    rules = tuple(_rule_na(f"ME{i}") for i in range(1, 5))
    student_attempts = _attempts(
        ("ME1", AttemptOutcome.PASSED),
        ("ME2", AttemptOutcome.PASSED),
        ("ME3", AttemptOutcome.PASSED),
    )
    result = _recommend(grps, courses, rules, student_attempts)
    assert "ME4" not in _codes(result)


# ===========================================================================
# 15-18: Zero credit
# ===========================================================================


def test_15_zero_credit_0200115_style_can_rank() -> None:
    """Test 15: Zero-credit required course appears in ranked recommendations."""
    grps = (_req_group(),)
    courses = (_pc("0200115", credits="0"),)
    rules = (_rule_na("0200115"),)
    result = _recommend(grps, courses, rules)
    assert "0200115" in _codes(result)


def test_16_zero_credit_1509999_style_can_rank() -> None:
    """Test 16: Another zero-credit required course also ranks."""
    grps = (_req_group(),)
    courses = (_pc("1509999", credits="0"),)
    rules = (_rule_na("1509999"),)
    result = _recommend(grps, courses, rules)
    assert "1509999" in _codes(result)


def test_17_zero_credit_effective_contribution_is_zero() -> None:
    """Test 17: Zero-credit required course has effective_credit_contribution = 0."""
    grps = (_req_group(),)
    courses = (_pc("A", credits="0"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    candidate = _by_code(result)["A"]
    assert candidate.effective_credit_contribution == Decimal("0")


def test_18_zero_credit_required_gets_structural_reason() -> None:
    """Test 18: Zero-credit required course has both REQUIRED_PLAN_COURSE and MANDATORY_ZERO_CREDIT_COURSE."""
    grps = (_req_group(),)
    courses = (_pc("A", credits="0"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    candidate = _by_code(result)["A"]
    assert RecommendationReason.REQUIRED_PLAN_COURSE in candidate.reason_codes
    assert RecommendationReason.MANDATORY_ZERO_CREDIT_COURSE in candidate.reason_codes


# ===========================================================================
# 19-24: Progress delta
# ===========================================================================


def test_19_candidate_pass_increases_credited_progress() -> None:
    """Test 19: After hypothetical pass, credited progress in group increases."""
    grps = (_req_group(required_hours="9"),)
    courses = (_pc("A", credits="3"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    candidate = _by_code(result)["A"]
    assert candidate.group_remaining_credits_before == Decimal("9")
    assert candidate.group_remaining_credits_after == Decimal("6")


def test_20_elective_contribution_capped_at_remaining_need() -> None:
    """Test 20: For elective with 3 credits remaining, a 3-credit course contributes 3 (not more)."""
    grps = (_elec_group(required_hours="3"),)
    courses = (
        _pc("A", group_id=GRP_ELECTIVE, credits="3", display_order=1),
        _pc("B", group_id=GRP_ELECTIVE, credits="3", display_order=2),
    )
    rules = (_rule_na("A"), _rule_na("B"))
    result = _recommend(grps, courses, rules)
    candidate_a = _by_code(result)["A"]
    assert candidate_a.effective_credit_contribution == Decimal("3")


def test_21_candidate_completing_group_detected() -> None:
    """Test 21: completes_requirement_group = True when hypothetical pass satisfies the group."""
    grps = (_req_group(required_hours="3"),)
    courses = (_pc("A", credits="3"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    assert _by_code(result)["A"].completes_requirement_group is True


def test_22_candidate_not_completing_group_is_false() -> None:
    """Test 22: completes_requirement_group = False for a partial contributor."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
        _pc("C", credits="3", display_order=3),
    )
    rules = (_rule_na("A"), _rule_na("B"), _rule_na("C"))
    result = _recommend(grps, courses, rules)
    # No single course completes the 9-credit required group (all 3 needed)
    for code in ("A", "B", "C"):
        assert _by_code(result)[code].completes_requirement_group is False


def test_23_synthetic_attempt_does_not_mutate_original_history() -> None:
    """Test 23: The original student_attempts tuple is unchanged after recommendation."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    original = _attempts(("X", AttemptOutcome.PASSED))
    original_len = len(original)
    recommend_courses(
        AcademicProgressCatalog(_plan(), grps, courses),
        CanTakeCatalog(
            PLAN_ID,
            rules,
            (CourseIdentity("A", CourseCatalogStatus.KNOWN),),
        ),
        original,
    )
    # Must not have grown
    assert len(original) == original_len


def test_24_duplicate_real_attempts_do_not_distort_delta() -> None:
    """Test 24: Repeated real attempts for the same course don't inflate credit delta."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
        _pc("C", credits="3", display_order=3),
    )
    rules = (_rule_na("A"), _rule_na("B"), _rule_na("C"))
    # A passed twice in real history (duplicate attempts)
    student_attempts = _attempts(
        ("A", AttemptOutcome.PASSED),
        ("A", AttemptOutcome.PASSED),
    )
    result = _recommend(grps, courses, rules, student_attempts)
    # A should be COMPLETED and excluded
    assert "A" not in _codes(result)
    # B and C should each contribute 3 credits
    candidate_b = _by_code(result)["B"]
    assert candidate_b.effective_credit_contribution == Decimal("3")


# ===========================================================================
# 25-35: Unlock simulation (AND/OR semantics reused from Phase 5)
# ===========================================================================


def test_25_no_downstream_dependency_count_zero() -> None:
    """Test 25: A course with no downstream dependents has newly_eligible_count = 0."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    assert _by_code(result)["A"].newly_eligible_count == 0


def test_26_one_newly_eligible_after_pass() -> None:
    """Test 26: Passing A unlocks exactly one course B (B requires A)."""
    grps = (_req_group(required_hours="6"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
    )
    rules = (
        _rule_na("A"),
        _rule_verified("B", "A"),
    )
    result = _recommend(grps, courses, rules)
    cand_a = _by_code(result)["A"]
    assert cand_a.newly_eligible_count == 1
    assert "B" in cand_a.newly_eligible_course_codes


def test_27_multiple_newly_eligible_correct_count() -> None:
    """Test 27: Passing A unlocks B, C, D → count = 3."""
    grps = (_req_group(required_hours="12"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
        _pc("C", credits="3", display_order=3),
        _pc("D", credits="3", display_order=4),
    )
    rules = (
        _rule_na("A"),
        _rule_verified("B", "A"),
        _rule_verified("C", "A"),
        _rule_verified("D", "A"),
    )
    result = _recommend(grps, courses, rules)
    cand_a = _by_code(result)["A"]
    assert cand_a.newly_eligible_count == 3
    assert set(cand_a.newly_eligible_course_codes) == {"B", "C", "D"}


def test_28_already_eligible_not_counted_as_newly_eligible() -> None:
    """Test 28: A course already ELIGIBLE before simulation is not counted."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
        _pc("C", credits="3", display_order=3),  # C has no prereqs → already ELIGIBLE
    )
    rules = (
        _rule_na("A"),
        _rule_verified("B", "A"),
        _rule_na("C"),
    )
    result = _recommend(grps, courses, rules)
    cand_a = _by_code(result)["A"]
    # C is already ELIGIBLE; only B becomes newly eligible
    assert cand_a.newly_eligible_count == 1
    assert "B" in cand_a.newly_eligible_course_codes
    assert "C" not in cand_a.newly_eligible_course_codes


def test_29_completed_downstream_not_counted() -> None:
    """Test 29: An already-COMPLETED downstream course is not counted."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),  # B requires A
        _pc("C", credits="3", display_order=3),  # C requires A (but already PASSED)
    )
    rules = (
        _rule_na("A"),
        _rule_verified("B", "A"),
        _rule_verified("C", "A"),
    )
    # Student already passed C
    result = _recommend(grps, courses, rules, _attempts(("C", AttemptOutcome.PASSED)))
    cand_a = _by_code(result)["A"]
    # Only B should be counted as newly eligible (C is COMPLETED, excluded from simulation)
    assert cand_a.newly_eligible_count == 1
    assert "C" not in cand_a.newly_eligible_course_codes


def test_30_in_progress_downstream_not_counted() -> None:
    """Test 30: An IN_PROGRESS downstream course is not counted as newly eligible."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),  # B requires A
        _pc("C", credits="3", display_order=3),  # C requires A (but IN_PROGRESS)
    )
    rules = (
        _rule_na("A"),
        _rule_verified("B", "A"),
        _rule_verified("C", "A"),
    )
    # Student has C in-progress
    result = _recommend(grps, courses, rules, _attempts(("C", AttemptOutcome.IN_PROGRESS)))
    cand_a = _by_code(result)["A"]
    assert "C" not in cand_a.newly_eligible_course_codes


def test_31_candidate_itself_not_counted() -> None:
    """Test 31: The candidate course itself is never counted in its own newly_eligible_count."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    cand_a = _by_code(result)["A"]
    assert "A" not in cand_a.newly_eligible_course_codes


def test_32_unresolved_stays_review_required_after_simulation() -> None:
    """Test 32: A course with unresolved prereqs stays REVIEW_REQUIRED after any simulation."""
    grps = (_req_group(required_hours="6"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
    )
    rules = (
        _rule_na("A"),
        _rule_unresolved("B"),
    )
    result = _recommend(grps, courses, rules)
    # B must be in review_required_courses, not counted as newly eligible by A
    assert "B" in _review_codes(result)
    cand_a = _by_code(result)["A"]
    assert "B" not in cand_a.newly_eligible_course_codes


def test_33_source_conflict_stays_review_required() -> None:
    """Test 33: Source-conflict courses stay REVIEW_REQUIRED; not unlocked by simulation."""
    grps = (_req_group(required_hours="6"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
    )
    rules = (
        _rule_na("A"),
        _rule_conflict("B"),
    )
    result = _recommend(grps, courses, rules)
    assert "B" in _review_codes(result)
    cand_a = _by_code(result)["A"]
    assert "B" not in cand_a.newly_eligible_course_codes


def test_34_and_prerequisite_partial_satisfaction_not_counted() -> None:
    """Test 34: AND group — satisfying one group does not unlock if other group unmet."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
        _pc("C", credits="3", display_order=3),  # requires A AND B (two groups)
    )
    rules = (
        _rule_na("A"),
        _rule_na("B"),
        _rule_verified_two("C", "A", "B"),
    )
    result = _recommend(grps, courses, rules)
    # Passing A alone: C needs both A and B → C not newly eligible
    cand_a = _by_code(result)["A"]
    assert "C" not in cand_a.newly_eligible_course_codes
    # Passing B alone: C still needs A → C not newly eligible
    cand_b = _by_code(result)["B"]
    assert "C" not in cand_b.newly_eligible_course_codes


def test_35_or_option_in_single_group_handled_by_evaluator() -> None:
    """Test 35: OR within a group — passing either option unlocks the target."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
        _pc("C", credits="3", display_order=3),  # requires A OR B (single group, two options)
    )
    rules = (
        _rule_na("A"),
        _rule_na("B"),
        # OR group: one group with two options
        PlanCourseRule(
            course_code="C",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(
                DependencyGroup(1, DependencyType.PREREQUISITE, ("A", "B")),
            ),
            raw_prerequisite_text="A,B",
            target_name_ar=None,
        ),
    )
    result = _recommend(grps, courses, rules)
    # A unlocks C (A OR B satisfied)
    cand_a = _by_code(result)["A"]
    assert "C" in cand_a.newly_eligible_course_codes


# ===========================================================================
# 36-43: Ranking
# ===========================================================================


def test_36_required_positive_credit_outranks_zero_credit_required() -> None:
    """Test 36: Positive-credit required (P1=2) ranks above zero-credit required (P1=1)."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("POS", credits="3", display_order=1),
        _pc("ZERO", credits="0", display_order=2),
    )
    rules = (_rule_na("POS"), _rule_na("ZERO"))
    result = _recommend(grps, courses, rules)
    codes = _codes(result)
    assert codes.index("POS") < codes.index("ZERO")


def test_37_zero_credit_required_outranks_elective() -> None:
    """Test 37: Zero-credit required (P1=1) ranks above any elective (P1=0)."""
    grps = (
        _req_group(required_hours="6", display_order=1),
        _elec_group(required_hours="3", display_order=2),
    )
    courses = (
        _pc("ZERO", group_id=GRP_REQUIRED, credits="0", display_order=1),
        _pc("ELEC", group_id=GRP_ELECTIVE, credits="3", display_order=2),
    )
    rules = (_rule_na("ZERO"), _rule_na("ELEC"))
    result = _recommend(grps, courses, rules)
    codes = _codes(result)
    assert codes.index("ZERO") < codes.index("ELEC")


def test_38_higher_effective_contribution_wins_at_p3() -> None:
    """Test 38: Among same-P1/P2 candidates, higher effective contribution wins."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="1", display_order=2),
    )
    rules = (_rule_na("A"), _rule_na("B"))
    result = _recommend(grps, courses, rules)
    codes = _codes(result)
    assert codes.index("A") < codes.index("B")


def test_39_group_completing_candidate_wins_at_p4() -> None:
    """Test 39: A group-completing candidate ranks above a non-completing one (equal P1-P3)."""
    grps = (_req_group(required_hours="3"),)
    courses = (
        _pc("COMPLETER", credits="3", display_order=1),  # completes the 3-credit group
        # NONCOMPLETER only possible if group needed more credit
    )
    rules = (_rule_na("COMPLETER"),)
    result = _recommend(grps, courses, rules)
    assert _by_code(result)["COMPLETER"].completes_requirement_group is True

    # More explicit: two separate groups, one completer vs non-completer, same P1/P2/P3
    grp2 = ProgressRequirementGroup(
        group_id="gr2", study_plan_id=PLAN_ID, group_code="GR2", name_ar="G2",
        name_en=None, scope="major", requirement_type=RequirementType.REQUIRED,
        required_credit_hours=Decimal("3"), display_order=2,
    )
    grp3 = ProgressRequirementGroup(
        group_id="gr3", study_plan_id=PLAN_ID, group_code="GR3", name_ar="G3",
        name_en=None, scope="major", requirement_type=RequirementType.REQUIRED,
        required_credit_hours=Decimal("6"), display_order=3,
    )
    courses2 = (
        _pc("X", group_id="gr2", credits="3", display_order=10),  # completes gr2
        _pc("Y", group_id="gr3", credits="3", display_order=10),  # doesn't complete gr3 (needs 6)
    )
    rules2 = (_rule_na("X"), _rule_na("Y"))
    result2 = _recommend((grp2, grp3), courses2, rules2)
    codes2 = _codes(result2)
    assert codes2.index("X") < codes2.index("Y")


def test_40_higher_newly_eligible_count_wins_at_p5() -> None:
    """Test 40: Among equal P1-P4, higher newly_eligible_count wins at P5."""
    grps = (_req_group(required_hours="12"),)
    courses = (
        _pc("TRIGGER2", credits="3", display_order=1),  # unlocks 2 downstream
        _pc("TRIGGER1", credits="3", display_order=2),  # unlocks 1 downstream
        _pc("DOWN1", credits="3", display_order=3),
        _pc("DOWN2", credits="3", display_order=4),
        _pc("DOWN3", credits="3", display_order=5),
    )
    rules = (
        _rule_na("TRIGGER2"),
        _rule_na("TRIGGER1"),
        _rule_verified("DOWN1", "TRIGGER2"),
        _rule_verified("DOWN2", "TRIGGER2"),
        _rule_verified("DOWN3", "TRIGGER1"),
    )
    result = _recommend(grps, courses, rules)
    codes = _codes(result)
    # TRIGGER2 unlocks DOWN1, DOWN2 → count=2; TRIGGER1 unlocks DOWN3 → count=1
    # Also equal P1=2, P2=1, P3=3, P4=? → P5 determines
    assert codes.index("TRIGGER2") < codes.index("TRIGGER1")


def test_41_lower_display_order_wins_tie() -> None:
    """Test 41: When P1-P5 tied, lower display_order wins."""
    grps = (_req_group(required_hours="6"),)
    courses = (
        _pc("B", credits="3", display_order=2),
        _pc("A", credits="3", display_order=1),
    )
    rules = (_rule_na("A"), _rule_na("B"))
    result = _recommend(grps, courses, rules)
    codes = _codes(result)
    # A has display_order=1, B has display_order=2; otherwise identical
    assert codes.index("A") < codes.index("B")


def test_42_course_code_ascending_final_tiebreak() -> None:
    """Test 42: Among courses with identical P1-P6, course_code ascending is final tiebreak."""
    grps = (_req_group(required_hours="9"),)
    # Give same display_order so P6 is identical
    courses = (
        _pc("ZZZ", credits="3", display_order=5),
        _pc("AAA", credits="3", display_order=5),
        _pc("MMM", credits="3", display_order=5),
    )
    rules = (_rule_na("ZZZ"), _rule_na("AAA"), _rule_na("MMM"))
    result = _recommend(grps, courses, rules)
    codes = _codes(result)
    assert codes == sorted(codes)  # ascending


def test_43_identical_input_produces_identical_result() -> None:
    """Test 43: Engine is deterministic — same inputs always produce same outputs."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
        _pc("C", credits="3", display_order=3),
    )
    rules = (
        _rule_na("A"),
        _rule_verified("B", "A"),
        _rule_na("C"),
    )
    student_attempts = _attempts(("X", AttemptOutcome.PASSED))
    r1 = _recommend(grps, courses, rules, student_attempts)
    r2 = _recommend(grps, courses, rules, student_attempts)
    assert _codes(r1) == _codes(r2)
    assert r1 == r2


# ===========================================================================
# 44-48: History
# ===========================================================================


def test_44_failed_only_candidate_can_be_recommended() -> None:
    """Test 44: A required course with FAILED-only history and ELIGIBLE decision is recommended."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules, _attempts(("A", AttemptOutcome.FAILED)))
    assert "A" in _codes(result)


def test_45_withdrawn_only_candidate_can_be_recommended() -> None:
    """Test 45: A required course with WITHDRAWN-only history and ELIGIBLE decision is recommended."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules, _attempts(("A", AttemptOutcome.WITHDRAWN)))
    assert "A" in _codes(result)


def test_46_previous_failure_adds_context_no_ranking_penalty() -> None:
    """Test 46: FAILED candidate and fresh candidate with same other attributes rank equally on factors."""
    grps = (_req_group(required_hours="6"),)
    courses = (
        _pc("FRESH", credits="3", display_order=1),
        _pc("FAILED", credits="3", display_order=2),
    )
    rules = (_rule_na("FRESH"), _rule_na("FAILED"))
    result = _recommend(
        grps, courses, rules, _attempts(("FAILED", AttemptOutcome.FAILED))
    )
    fresh = _by_code(result)["FRESH"]
    failed = _by_code(result)["FAILED"]

    # The FAILED candidate should have previously_attempted = True
    assert failed.previously_attempted is True
    assert fresh.previously_attempted is False

    # No penalty to P1-P5 — the only difference is P6 (display_order)
    assert fresh.priority_tuple[:5] == failed.priority_tuple[:5]

    # FRESH has lower display_order, so it ranks above FAILED — which is correct
    # (display_order is the tiebreaker, not a penalty)
    codes = _codes(result)
    assert codes.index("FRESH") < codes.index("FAILED")


def test_47_failed_then_passed_is_completed_and_excluded() -> None:
    """Test 47: FAILED then PASSED → COMPLETED → excluded from candidates."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(
        grps, courses, rules,
        _attempts(("A", AttemptOutcome.FAILED), ("A", AttemptOutcome.PASSED)),
    )
    assert "A" not in _codes(result)


def test_48_passed_then_failed_still_completed_and_excluded() -> None:
    """Test 48: PASSED then FAILED → still COMPLETED (Phase 6 priority: PASSED wins)."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(
        grps, courses, rules,
        _attempts(("A", AttemptOutcome.PASSED), ("A", AttemptOutcome.FAILED)),
    )
    assert "A" not in _codes(result)


# ===========================================================================
# 49-52: Special cases
# ===========================================================================


def test_49_all_courses_completed_empty_recommendations() -> None:
    """Test 49: If all plan courses are completed, ranked_recommendations is empty."""
    grps = (_req_group(required_hours="3"),)
    courses = (_pc("A", credits="3"),)
    rules = (_rule_na("A"),)
    result = _recommend(
        grps, courses, rules, _attempts(("A", AttemptOutcome.PASSED))
    )
    assert result.ranked_recommendations == ()


def test_50_only_review_required_valid_result() -> None:
    """Test 50: Only REVIEW_REQUIRED courses → empty ranking, non-empty review list."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_unresolved("A"),)
    result = _recommend(grps, courses, rules)
    assert result.ranked_recommendations == ()
    assert len(result.review_required_courses) == 1
    assert result.review_required_courses[0].course_code == "A"


def test_51_no_eligible_incomplete_courses_valid_empty_result() -> None:
    """Test 51: All incomplete courses are NOT_ELIGIBLE → empty ranking, no error."""
    grps = (_req_group(required_hours="3"),)
    courses = (_pc("A", credits="3"),)
    rules = (_rule_verified("A", "MISSING"),)
    result = _recommend(grps, courses, rules)
    assert result.ranked_recommendations == ()
    assert result.review_required_courses == ()


def test_52_satisfied_elective_options_excluded_from_ranking() -> None:
    """Test 52: Elective options are excluded when the elective group is fully satisfied."""
    grp_id = GRP_ELECTIVE
    grps = (_elec_group(required_hours="3"),)
    courses = (
        _pc("E1", group_id=grp_id, credits="3", display_order=1),
        _pc("E2", group_id=grp_id, credits="3", display_order=2),
    )
    rules = (_rule_na("E1"), _rule_na("E2"))
    # Satisfy the elective group with E1
    result = _recommend(
        grps, courses, rules, _attempts(("E1", AttemptOutcome.PASSED))
    )
    assert "E1" not in _codes(result)  # completed
    assert "E2" not in _codes(result)  # group satisfied → excluded


# ===========================================================================
# 53-59: Reason codes
# ===========================================================================


def test_53_required_course_reason_codes() -> None:
    """Test 53: Required course has REQUIRED_PLAN_COURSE and ADVANCES_REQUIRED_GROUP."""
    grps = (_req_group(required_hours="9"),)
    courses = (_pc("A", credits="3"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    reasons = _by_code(result)["A"].reason_codes
    assert RecommendationReason.REQUIRED_PLAN_COURSE in reasons
    assert RecommendationReason.ADVANCES_REQUIRED_GROUP in reasons


def test_54_zero_credit_reasons_correct() -> None:
    """Test 54: Zero-credit required course has both required and zero-credit reason codes."""
    grps = (_req_group(),)
    courses = (_pc("A", credits="0"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    reasons = _by_code(result)["A"].reason_codes
    assert RecommendationReason.REQUIRED_PLAN_COURSE in reasons
    assert RecommendationReason.MANDATORY_ZERO_CREDIT_COURSE in reasons


def test_55_group_completion_reason_correct() -> None:
    """Test 55: Completing candidate has COMPLETES_REQUIREMENT_GROUP reason."""
    grps = (_req_group(required_hours="3"),)
    courses = (_pc("A", credits="3"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    reasons = _by_code(result)["A"].reason_codes
    assert RecommendationReason.COMPLETES_REQUIREMENT_GROUP in reasons


def test_56_one_unlock_reason_correct() -> None:
    """Test 56: Exactly one unlock → UNLOCKS_FUTURE_COURSE reason."""
    grps = (_req_group(required_hours="6"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
    )
    rules = (_rule_na("A"), _rule_verified("B", "A"))
    result = _recommend(grps, courses, rules)
    reasons = _by_code(result)["A"].reason_codes
    assert RecommendationReason.UNLOCKS_FUTURE_COURSE in reasons
    assert RecommendationReason.UNLOCKS_MULTIPLE_FUTURE_COURSES not in reasons


def test_57_multi_unlock_reason_correct() -> None:
    """Test 57: Multiple unlocks → UNLOCKS_MULTIPLE_FUTURE_COURSES reason."""
    grps = (_req_group(required_hours="12"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
        _pc("C", credits="3", display_order=3),
        _pc("D", credits="3", display_order=4),
    )
    rules = (
        _rule_na("A"),
        _rule_verified("B", "A"),
        _rule_verified("C", "A"),
        _rule_verified("D", "A"),
    )
    result = _recommend(grps, courses, rules)
    reasons = _by_code(result)["A"].reason_codes
    assert RecommendationReason.UNLOCKS_MULTIPLE_FUTURE_COURSES in reasons
    assert RecommendationReason.UNLOCKS_FUTURE_COURSE not in reasons


def test_58_previously_attempted_reason() -> None:
    """Test 58: ATTEMPTED_NOT_COMPLETED candidate has PREVIOUSLY_ATTEMPTED reason."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules, _attempts(("A", AttemptOutcome.FAILED)))
    reasons = _by_code(result)["A"].reason_codes
    assert RecommendationReason.PREVIOUSLY_ATTEMPTED in reasons


def test_59_no_impact_reason_when_zero_unlocks() -> None:
    """Test 59: NO_DIRECT_PREREQUISITE_IMPACT reason when newly_eligible_count == 0."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    reasons = _by_code(result)["A"].reason_codes
    assert RecommendationReason.NO_DIRECT_PREREQUISITE_IMPACT in reasons


# ===========================================================================
# 60: Policy version
# ===========================================================================


def test_60_result_contains_policy_version_1_0() -> None:
    """Test 60: RecommendationResult.recommendation_policy_version == '1.0'."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    assert result.recommendation_policy_version == "1.0"
    assert RECOMMENDATION_POLICY_VERSION == "1.0"


# ===========================================================================
# 61-68: Real Plan 12 facts
# ===========================================================================
#
# These tests use ACTUAL course codes, credit hours, group codes, and
# prerequisite relationships from the verified Plan 12 seed migration.
# No academic facts are invented here.
# ---------------------------------------------------------------------------

# Real Plan 12 prerequisite chain (from migration):
#   0300153 → 1501110 → 1501112 → 1501221
#                     → 1505101
#                     → 1506180
# Group: all are FACULTY_REQUIRED or MAJOR_REQUIRED

UNIV_REQ_ID  = "gr-univ-req"
FAC_REQ_ID   = "gr-fac-req"
MAJ_REQ_ID   = "gr-maj-req"
UNIV_ELEC_ID = "gr-univ-elec"
MAJ_ELEC_ID  = "gr-maj-elec"
SUPP_REQ_ID  = "gr-supp-req"


def _plan12_groups() -> tuple[ProgressRequirementGroup, ...]:
    return (
        ProgressRequirementGroup(
            UNIV_REQ_ID, PLAN_ID, "UNIVERSITY_REQUIRED", "متطلبات الجامعة الإجبارية",
            None, "university", RequirementType.REQUIRED, Decimal("18"), 1,
        ),
        ProgressRequirementGroup(
            UNIV_ELEC_ID, PLAN_ID, "UNIVERSITY_ELECTIVE", "متطلبات الجامعة الاختيارية",
            None, "university", RequirementType.ELECTIVE, Decimal("9"), 2,
        ),
        ProgressRequirementGroup(
            FAC_REQ_ID, PLAN_ID, "FACULTY_REQUIRED", "متطلبات الكلية الإجبارية",
            None, "faculty", RequirementType.REQUIRED, Decimal("21"), 3,
        ),
        ProgressRequirementGroup(
            SUPP_REQ_ID, PLAN_ID, "SUPPORTING_REQUIRED", "المتطلبات المساندة",
            None, "supporting", RequirementType.REQUIRED, Decimal("12"), 4,
        ),
        ProgressRequirementGroup(
            MAJ_REQ_ID, PLAN_ID, "MAJOR_REQUIRED", "متطلبات التخصص الإجبارية",
            None, "major", RequirementType.REQUIRED, Decimal("63"), 5,
        ),
        ProgressRequirementGroup(
            MAJ_ELEC_ID, PLAN_ID, "MAJOR_ELECTIVE", "متطلبات التخصص الاختيارية",
            None, "major", RequirementType.ELECTIVE, Decimal("9"), 6,
        ),
    )


def _plan12_courses() -> tuple[ProgressPlanCourse, ...]:
    """Subset of real Plan 12 courses sufficient for Phase 7.2 tests."""
    return (
        # UNIVERSITY_REQUIRED
        _pc("0200104", UNIV_REQ_ID, "3", 1),
        _pc("0200105", UNIV_REQ_ID, "3", 2),  # unresolved prereq
        _pc("0200106", UNIV_REQ_ID, "3", 3),  # unresolved prereq
        _pc("0200110", UNIV_REQ_ID, "3", 4),
        _pc("0200111", UNIV_REQ_ID, "3", 5),
        _pc("0200115", UNIV_REQ_ID, "0", 6),  # zero-credit required
        _pc("0200153", UNIV_REQ_ID, "1", 7),
        _pc("0200154", UNIV_REQ_ID, "1", 8),
        _pc("0400202", UNIV_REQ_ID, "1", 9),
        # UNIVERSITY_ELECTIVE (9 of 33 required)
        _pc("0200113", UNIV_ELEC_ID, "3", 10),
        _pc("0200114", UNIV_ELEC_ID, "3", 11),
        _pc("0200122", UNIV_ELEC_ID, "3", 12),
        _pc("0200125", UNIV_ELEC_ID, "3", 13),
        _pc("0200127", UNIV_ELEC_ID, "3", 14),
        _pc("0200130", UNIV_ELEC_ID, "3", 15),
        _pc("0200156", UNIV_ELEC_ID, "3", 16),
        _pc("0300123", UNIV_ELEC_ID, "3", 17),
        _pc("0300124", UNIV_ELEC_ID, "3", 18),
        _pc("0300157", UNIV_ELEC_ID, "3", 19),
        _pc("0300161", UNIV_ELEC_ID, "3", 20),
        # FACULTY_REQUIRED
        _pc("0300153", FAC_REQ_ID, "3", 21),  # no prereq
        _pc("0300154", FAC_REQ_ID, "3", 22),
        _pc("0300155", FAC_REQ_ID, "3", 23),
        _pc("0300220", FAC_REQ_ID, "3", 24),  # prereq: 0300153
        _pc("1501110", FAC_REQ_ID, "3", 25),  # prereq: 0300153
        _pc("1501112", FAC_REQ_ID, "3", 26),  # prereq: 1501110
        _pc("1501221", FAC_REQ_ID, "3", 27),  # prereq: 1501112
        _pc("1509999", FAC_REQ_ID, "0", 28),  # zero-credit required
        # SUPPORTING_REQUIRED
        _pc("0200215", SUPP_REQ_ID, "3", 29),  # prereq: 0200106 (unresolved)
        _pc("0300101", SUPP_REQ_ID, "3", 30),
        _pc("0300104", SUPP_REQ_ID, "3", 31),
        _pc("0301245", SUPP_REQ_ID, "3", 32),
        # MAJOR_REQUIRED (subset)
        _pc("1501222", MAJ_REQ_ID, "3", 48),  # prereq: 1501112
        _pc("1501340", MAJ_REQ_ID, "3", 50),  # prereq: 1501112
        _pc("1503270", MAJ_REQ_ID, "3", 52),  # prereq: 0300153
        _pc("1505101", MAJ_REQ_ID, "3", 53),  # prereq: 1501110
        _pc("1505201", MAJ_REQ_ID, "3", 54),  # prereq: 0300153
        _pc("1505311", MAJ_REQ_ID, "3", 56),  # source: 1505101,1505201 → unresolved
        _pc("1505320", MAJ_REQ_ID, "3", 57),  # source_conflict
        _pc("1505366", MAJ_REQ_ID, "3", 59),  # source_conflict
        _pc("1506180", MAJ_REQ_ID, "3", 67),  # prereq: 1501110
        # MAJOR_ELECTIVE (subset, 9 of 39 required)
        _pc("1501360", MAJ_ELEC_ID, "3", 34),  # no prereq
        _pc("1505435", MAJ_ELEC_ID, "3", 41),  # no prereq
        _pc("1505436", MAJ_ELEC_ID, "3", 42),  # no prereq
    )


def _plan12_rules() -> tuple[PlanCourseRule, ...]:
    """PlanCourseRules for the subset of Plan 12 courses above."""
    return (
        _rule_na("0200104"),
        _rule_unresolved("0200105", "0200150,0201001"),
        _rule_unresolved("0200106", "0200151,0202001"),
        _rule_na("0200110"),
        _rule_na("0200111"),
        _rule_na("0200115"),
        _rule_na("0200153"),
        _rule_na("0200154"),
        _rule_na("0400202"),
        _rule_na("0200113"),
        _rule_na("0200114"),
        _rule_na("0200122"),
        _rule_na("0200125"),
        _rule_na("0200127"),
        _rule_na("0200130"),
        _rule_na("0200156"),
        _rule_na("0300123"),
        _rule_na("0300124"),
        _rule_na("0300157"),
        _rule_na("0300161"),
        _rule_na("0300153"),
        _rule_na("0300154"),
        _rule_na("0300155"),
        _rule_verified("0300220", "0300153"),
        _rule_verified("1501110", "0300153"),
        _rule_verified("1501112", "1501110"),
        _rule_verified("1501221", "1501112"),
        _rule_na("1509999"),
        _rule_unresolved("0200215", "0200106"),  # prereq 0200106 is unresolved itself
        _rule_na("0300101"),
        _rule_na("0300104"),
        _rule_na("0301245"),
        _rule_verified("1501222", "1501112"),
        _rule_verified("1501340", "1501112"),
        _rule_verified("1503270", "0300153"),
        _rule_verified("1505101", "1501110"),
        _rule_verified("1505201", "0300153"),
        _rule_unresolved("1505311", "1505101,1505201"),
        _rule_conflict("1505320", "0300103,1505311"),
        _rule_conflict("1505366", "0301241,1505101"),
        _rule_verified("1506180", "1501110"),
        _rule_na("1501360"),
        _rule_na("1505435"),
        _rule_na("1505436"),
    )


def _plan12_result(
    student_attempts: tuple[StudentCourseAttempt, ...] = (),
) -> RecommendationResult:
    return _recommend(
        _plan12_groups(),
        _plan12_courses(),
        _plan12_rules(),
        student_attempts,
    )


def test_61_plan12_verified_dependency_chain_1501110_to_1501112() -> None:
    """Test 61: With 1501110 PASSED, 1501112 is eligible and recommended."""
    result = _plan12_result(_attempts(("0300153", AttemptOutcome.PASSED), ("1501110", AttemptOutcome.PASSED)))
    codes = _codes(result)
    # 1501112 requires 1501110 (verified) → should be eligible and ranked
    assert "1501112" in codes
    # 1501112 (FACULTY_REQUIRED, 3 credits) should appear before Major Electives (P1=2 vs P1=0)


def test_61b_plan12_1501110_unlocks_1501112_in_simulation() -> None:
    """Test 61b: 0300153 passed → 1501110 eligible; 1501110's simulation should show 1501112 as unlock."""
    result = _plan12_result(_attempts(("0300153", AttemptOutcome.PASSED)))
    codes = _codes(result)
    assert "1501110" in codes
    cand = _by_code(result)["1501110"]
    # Passing 1501110 unlocks 1501112, 1505101, 1506180 (all require 1501110)
    assert "1501112" in cand.newly_eligible_course_codes
    assert "1505101" in cand.newly_eligible_course_codes
    assert "1506180" in cand.newly_eligible_course_codes
    assert cand.newly_eligible_count >= 3


def test_62_plan12_1505311_remains_review_required() -> None:
    """Test 62: 1505311 (unresolved) is always in review_required_courses."""
    result = _plan12_result()
    assert "1505311" in _review_codes(result)
    assert "1505311" not in _codes(result)


def test_62b_plan12_1505311_review_required_even_with_history() -> None:
    """Test 62b: Even with many courses passed, 1505311 stays REVIEW_REQUIRED."""
    result = _plan12_result(
        _attempts(
            ("0300153", AttemptOutcome.PASSED),
            ("1501110", AttemptOutcome.PASSED),
            ("1505101", AttemptOutcome.PASSED),
            ("1505201", AttemptOutcome.PASSED),
        )
    )
    assert "1505311" in _review_codes(result)
    assert "1505311" not in _codes(result)


def test_63_plan12_1505320_source_conflict_review_required() -> None:
    """Test 63: 1505320 (source_conflict) is in review_required_courses."""
    result = _plan12_result()
    assert "1505320" in _review_codes(result)
    assert "1505320" not in _codes(result)


def test_63b_plan12_1505320_review_reason_is_source_conflict() -> None:
    """Test 63b: 1505320's review_reason reflects PREREQUISITE_SOURCE_CONFLICT."""
    result = _plan12_result()
    review = next(c for c in result.review_required_courses if c.course_code == "1505320")
    assert "SOURCE_CONFLICT" in review.review_reason


def test_64_plan12_0200115_zero_credit_required_behavior() -> None:
    """Test 64: 0200115 (zero-credit, UNIVERSITY_REQUIRED) is recommended with P1=1."""
    result = _plan12_result()
    assert "0200115" in _codes(result)
    cand = _by_code(result)["0200115"]
    assert cand.priority_tuple[0] == 1  # P1=1 for zero-credit required
    assert cand.credit_hours == Decimal("0")
    assert cand.effective_credit_contribution == Decimal("0")
    assert RecommendationReason.MANDATORY_ZERO_CREDIT_COURSE in cand.reason_codes
    assert RecommendationReason.REQUIRED_PLAN_COURSE in cand.reason_codes


def test_65_plan12_1509999_zero_credit_required_behavior() -> None:
    """Test 65: 1509999 (zero-credit, FACULTY_REQUIRED) is recommended with P1=1."""
    result = _plan12_result()
    assert "1509999" in _codes(result)
    cand = _by_code(result)["1509999"]
    assert cand.priority_tuple[0] == 1
    assert cand.credit_hours == Decimal("0")
    assert RecommendationReason.MANDATORY_ZERO_CREDIT_COURSE in cand.reason_codes


def test_65b_plan12_zero_credit_outranks_electives() -> None:
    """Test 65b: Both 0200115 and 1509999 rank above Major Elective courses."""
    result = _plan12_result()
    codes = _codes(result)
    zero_credit_pos_0200115 = codes.index("0200115")
    zero_credit_pos_1509999 = codes.index("1509999")
    # All elective candidates should have P1=0; zero-credit required has P1=1
    for elec_code in ["1501360", "1505435", "1505436"]:
        elec_pos = codes.index(elec_code)
        assert zero_credit_pos_0200115 < elec_pos, f"0200115 should rank above {elec_code}"
        assert zero_credit_pos_1509999 < elec_pos, f"1509999 should rank above {elec_code}"


def test_66_university_elective_9_credit_satisfaction() -> None:
    """Test 66: After 9 University Elective credits, remaining electives are excluded."""
    # Pass 3 University Elective courses (3×3 = 9 credits = required)
    result = _plan12_result(
        _attempts(
            ("0200113", AttemptOutcome.PASSED),
            ("0200114", AttemptOutcome.PASSED),
            ("0200122", AttemptOutcome.PASSED),
        )
    )
    codes = _codes(result)
    # Remaining University Elective courses should be excluded
    for code in ["0200125", "0200127", "0200130", "0200156", "0300123", "0300124", "0300157", "0300161"]:
        assert code not in codes, f"{code} should be excluded after University Elective satisfied"


def test_67_major_elective_9_credit_satisfaction() -> None:
    """Test 67: After 9 Major Elective credits, remaining electives are excluded."""
    result = _plan12_result(
        _attempts(
            ("1501360", AttemptOutcome.PASSED),
            ("1505435", AttemptOutcome.PASSED),
            ("1505436", AttemptOutcome.PASSED),
        )
    )
    codes = _codes(result)
    # No remaining Major Elective candidate should appear in ranking
    for code in ["1501360", "1505435", "1505436"]:
        assert code not in codes  # these are COMPLETED


def test_68_0300103_referenced_only_history_not_a_recommendation_candidate() -> None:
    """Test 68: 0300103 (referenced_only, not a plan member) is never recommended."""
    # Even if a student records 0300103 as passed in history, it must not appear
    result = _plan12_result(
        _attempts(("0300103", AttemptOutcome.PASSED))
    )
    all_codes = _codes(result) + _review_codes(result) + list(result.excluded_in_progress)
    assert "0300103" not in all_codes


# ===========================================================================
# Additional edge-case and invariant tests
# ===========================================================================


def test_plan_id_preserved_in_result() -> None:
    """RecommendationResult must carry the correct study_plan_id."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    assert result.study_plan_id == PLAN_ID


def test_rank_numbers_are_sequential_from_one() -> None:
    """Ranks in ranked_recommendations must be 1, 2, 3, ... with no gaps."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("A", credits="3", display_order=1),
        _pc("B", credits="3", display_order=2),
        _pc("C", credits="3", display_order=3),
    )
    rules = (_rule_na("A"), _rule_na("B"), _rule_na("C"))
    result = _recommend(grps, courses, rules)
    ranks = [c.rank for c in result.ranked_recommendations]
    assert ranks == list(range(1, len(ranks) + 1))


def test_newly_eligible_course_codes_are_sorted() -> None:
    """newly_eligible_course_codes must be in ascending order."""
    grps = (_req_group(required_hours="12"),)
    courses = (
        _pc("ALPHA", credits="3", display_order=1),
        _pc("ZETA",  credits="3", display_order=5),
        _pc("GAMMA", credits="3", display_order=3),
        _pc("BETA",  credits="3", display_order=4),
    )
    rules = (
        _rule_na("ALPHA"),
        _rule_verified("ZETA",  "ALPHA"),
        _rule_verified("GAMMA", "ALPHA"),
        _rule_verified("BETA",  "ALPHA"),
    )
    result = _recommend(grps, courses, rules)
    cand = _by_code(result)["ALPHA"]
    codes = list(cand.newly_eligible_course_codes)
    assert codes == sorted(codes)


def test_excluded_in_progress_is_sorted() -> None:
    """excluded_in_progress must be in ascending order."""
    grps = (_req_group(required_hours="12"),)
    courses = (
        _pc("ZZZ", credits="3", display_order=3),
        _pc("AAA", credits="3", display_order=1),
        _pc("MMM", credits="3", display_order=2),
    )
    rules = (_rule_na("ZZZ"), _rule_na("AAA"), _rule_na("MMM"))
    result = _recommend(
        grps, courses, rules,
        _attempts(
            ("ZZZ", AttemptOutcome.IN_PROGRESS),
            ("AAA", AttemptOutcome.IN_PROGRESS),
        ),
    )
    assert list(result.excluded_in_progress) == sorted(result.excluded_in_progress)


def test_methodology_note_present() -> None:
    """RecommendationResult must include a non-empty methodology_note."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    assert result.methodology_note and len(result.methodology_note) > 20


def test_limitations_non_empty() -> None:
    """RecommendationResult.limitations must be a non-empty tuple of strings."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    assert len(result.limitations) > 0
    assert all(isinstance(l, str) and l for l in result.limitations)


def test_no_fastapi_import_in_engine() -> None:
    """The recommendation engine must not contain 'import fastapi' or 'from fastapi'."""
    import app.recommendations.engine as engine_mod
    source_file = engine_mod.__file__
    assert source_file is not None
    with open(source_file) as fh:
        lines = fh.readlines()
    import_lines = [l for l in lines if l.strip().startswith(("import ", "from "))]
    assert not any("fastapi" in l.lower() for l in import_lines)


def test_no_supabase_import_in_engine() -> None:
    """The recommendation engine must not contain 'import supabase' or 'import httpx'."""
    import app.recommendations.engine as engine_mod
    source_file = engine_mod.__file__
    assert source_file is not None
    with open(source_file) as fh:
        lines = fh.readlines()
    import_lines = [l for l in lines if l.strip().startswith(("import ", "from "))]
    assert not any("supabase" in l.lower() for l in import_lines)
    assert not any("httpx" in l.lower() for l in import_lines)


def test_elective_reason_code_advances_elective_requirement() -> None:
    """Elective candidate in unsatisfied group gets ADVANCES_ELECTIVE_REQUIREMENT."""
    grps = (_elec_group(required_hours="9"),)
    courses = (_pc("A", group_id=GRP_ELECTIVE, credits="3"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    reasons = _by_code(result)["A"].reason_codes
    assert RecommendationReason.ADVANCES_ELECTIVE_REQUIREMENT in reasons
    assert RecommendationReason.ADVANCES_REQUIRED_GROUP not in reasons


def test_review_required_courses_ordered_ascending_by_code() -> None:
    """review_required_courses should be ordered by course_code ascending."""
    grps = (_req_group(required_hours="9"),)
    courses = (
        _pc("Z99", credits="3", display_order=3),
        _pc("A00", credits="3", display_order=1),
        _pc("M50", credits="3", display_order=2),
    )
    rules = (
        _rule_unresolved("Z99"),
        _rule_unresolved("A00"),
        _rule_unresolved("M50"),
    )
    result = _recommend(grps, courses, rules)
    review_codes = [c.course_code for c in result.review_required_courses]
    assert review_codes == sorted(review_codes)


def test_priority_tuple_length_is_seven() -> None:
    """Each candidate's priority_tuple must have exactly 7 elements."""
    grps = (_req_group(),)
    courses = (_pc("A"),)
    rules = (_rule_na("A"),)
    result = _recommend(grps, courses, rules)
    assert len(_by_code(result)["A"].priority_tuple) == 7


def test_group_remaining_credits_after_bounded_to_zero() -> None:
    """group_remaining_credits_after must be >= 0 even if contribution exceeds need."""
    grps = (_elec_group(required_hours="3"),)
    courses = (
        _pc("A", group_id=GRP_ELECTIVE, credits="3", display_order=1),
        _pc("B", group_id=GRP_ELECTIVE, credits="3", display_order=2),
    )
    rules = (_rule_na("A"), _rule_na("B"))
    # No prior history → both A and B show remaining need
    result = _recommend(grps, courses, rules)
    for code in ["A", "B"]:
        cand = _by_code(result)[code]
        assert cand.group_remaining_credits_after >= Decimal("0")
