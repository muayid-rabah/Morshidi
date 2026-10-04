"""Pure deterministic course-recommendation engine (Phase 7.2).

This module has NO FastAPI, Supabase, httpx, or any I/O dependency.
It reuses Phase 5 (evaluate_can_take) and Phase 6 (calculate_academic_progress)
without duplicating any of their logic.

Architecture:

    recommend_courses(progress_catalog, eligibility_catalog, student_attempts)
        -> RecommendationResult

All simulation is in-memory.  Hypothetical PASSED attempts are NEVER persisted.

Ranking uses the lexicographic priority tuple from Phase 7.1 §16:

    (P1, P2, P3, P4, P5, P6, P7)

where the sort direction for each dimension is documented in _sort_key().
"""

from __future__ import annotations

from decimal import Decimal

from app.progress.engine import calculate_academic_progress
from app.progress.models import (
    AcademicProgress,
    AcademicProgressCatalog,
    CourseProgress,
    CourseProgressState,
    RequirementGroupProgress,
    RequirementType,
)
from app.recommendations.models import (
    RECOMMENDATION_POLICY_VERSION,
    RecommendationCandidate,
    RecommendationReason,
    RecommendationResult,
    ReviewRequiredCourse,
)
from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CanTakeDecision,
    CanTakeRequest,
    Decision,
    DecisionReason,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)

ZERO = Decimal("0")

_METHODOLOGY_NOTE = (
    "These recommendations are based on your modeled academic study plan and "
    "verified prerequisite structure. They indicate courses that are academically "
    "useful for your degree progress based on available data. They are not "
    "official registration approval, do not guarantee course availability, and "
    "do not represent institutional academic advice."
)

_LIMITATIONS: tuple[str, ...] = (
    "Recommendation quality is bounded by modeled academic structure.",
    "Course offering and section availability are unknown.",
    "Some prerequisite data remains unresolved or has source conflicts; "
    "affected courses appear only in review_required_courses.",
    "No transfer-credit, course equivalency, or substitution model exists.",
    "No course difficulty, workload, or student preference model exists.",
    "Individual course ranking is not a complete semester plan.",
    "No institutional administrative rules (GPA probation, holds, etc.) are modeled.",
    "No official GPA calculation engine exists.",
    "Derived plan progress does not constitute official graduation clearance.",
    "Referenced-only courses in student history contribute no plan credit.",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def recommend_courses(
    progress_catalog: AcademicProgressCatalog,
    eligibility_catalog: CanTakeCatalog,
    student_attempts: tuple[StudentCourseAttempt, ...],
    *,
    reported_cumulative_gpa: Decimal | None = None,
    reported_gpa_scale: Decimal | None = None,
    reported_earned_credit_hours: Decimal | None = None,
) -> RecommendationResult:
    """Compute deterministic course recommendations.

    Parameters
    ----------
    progress_catalog:
        The AcademicProgressCatalog for the student's study plan.
        Used with Phase 6 calculate_academic_progress().
    eligibility_catalog:
        The CanTakeCatalog containing ALL plan-course rules and dependency data.
        Used with Phase 5 evaluate_can_take() for baseline and simulation.
    student_attempts:
        Immutable tuple of the student's persisted course attempts.
        NEVER mutated; synthetic attempts are created via append.
    reported_cumulative_gpa, reported_gpa_scale, reported_earned_credit_hours:
        Passed through to Phase 6 as reported (not modeled) facts.
        Not used for ranking.
    """

    study_plan_id = progress_catalog.study_plan.study_plan_id

    # ------------------------------------------------------------------
    # Step 1: Current progress baseline
    # ------------------------------------------------------------------
    current_progress = calculate_academic_progress(
        progress_catalog,
        student_attempts,
        reported_cumulative_gpa=reported_cumulative_gpa,
        reported_gpa_scale=reported_gpa_scale,
        reported_earned_credit_hours=reported_earned_credit_hours,
    )

    # Build lookup indexes from current progress
    course_progress_by_code: dict[str, CourseProgress] = {
        cp.course_code: cp for cp in current_progress.courses
    }
    group_progress_by_id: dict[str, RequirementGroupProgress] = {
        gp.group_id: gp for gp in current_progress.requirement_groups
    }

    # ------------------------------------------------------------------
    # Step 2: Build plan-course metadata index
    # ------------------------------------------------------------------
    # progress_catalog.plan_courses is the authoritative ordered list of
    # plan courses.  We index by course_code for O(1) lookup.
    plan_course_meta: dict[str, _PlanCourseMeta] = {}
    for pc in progress_catalog.plan_courses:
        group = None
        for rg in progress_catalog.requirement_groups:
            if rg.group_id == pc.requirement_group_id:
                group = rg
                break
        if group is None:
            # Integrity: guarded by Phase 6; should never occur with valid catalog
            continue
        plan_course_meta[pc.course_code] = _PlanCourseMeta(
            course_code=pc.course_code,
            credit_hours=pc.credit_hours,
            display_order=pc.display_order,
            requirement_group_id=pc.requirement_group_id,
            requirement_group_code=group.group_code,
            requirement_type=group.requirement_type,
        )

    # Build name lookup from eligibility_catalog (PlanCourseRule has target_name_ar)
    name_by_code: dict[str, str | None] = {
        rule.course_code: rule.target_name_ar
        for rule in eligibility_catalog.plan_courses
    }
    name_en_by_code = {rule.course_code: rule.target_name_en
                       for rule in eligibility_catalog.plan_courses}
    for course in progress_catalog.plan_courses:
        name_by_code[course.course_code] = name_by_code.get(course.course_code) or course.course_name_ar
        name_en_by_code[course.course_code] = name_en_by_code.get(course.course_code) or course.course_name_en

    # ------------------------------------------------------------------
    # Step 3: Baseline eligibility for all incomplete plan courses
    # ------------------------------------------------------------------
    # Classify each plan course into one of: COMPLETED, IN_PROGRESS, ELIGIBLE,
    # NOT_ELIGIBLE, REVIEW_REQUIRED.
    # We only call Phase 5 for courses that are neither COMPLETED nor IN_PROGRESS.

    completed_codes: set[str] = set()
    in_progress_codes: set[str] = set()
    for code, cp in course_progress_by_code.items():
        if cp.state is CourseProgressState.COMPLETED:
            completed_codes.add(code)
        elif cp.state is CourseProgressState.IN_PROGRESS:
            in_progress_codes.add(code)

    # Courses that need Phase 5 evaluation
    incomplete_codes: list[str] = sorted(
        code
        for code in course_progress_by_code
        if code not in completed_codes and code not in in_progress_codes
    )

    baseline_decisions: dict[str, _EligibilityClass] = {}
    baseline_review_reasons: dict[str, str] = {}

    for code in incomplete_codes:
        result = evaluate_can_take(
            eligibility_catalog,
            CanTakeRequest(
                study_plan_id=eligibility_catalog.study_plan_id,
                target_course_code=code,
                student_attempts=student_attempts,
            ),
        )
        if isinstance(result, CanTakeDecision):
            if result.decision is Decision.ELIGIBLE:
                baseline_decisions[code] = _EligibilityClass.ELIGIBLE
            elif result.decision is Decision.REVIEW_REQUIRED:
                baseline_decisions[code] = _EligibilityClass.REVIEW_REQUIRED
                # Capture the primary review reason for the response model
                review_reason_str = (
                    result.review_reasons[0].value
                    if result.review_reasons
                    else DecisionReason.PREREQUISITE_LOGIC_UNRESOLVED.value
                )
                baseline_review_reasons[code] = review_reason_str
            else:
                baseline_decisions[code] = _EligibilityClass.NOT_ELIGIBLE
        else:
            # CanTakeError: target not found or not in plan — treat as not eligible
            # (should not occur for valid plan courses)
            baseline_decisions[code] = _EligibilityClass.NOT_ELIGIBLE

    # ------------------------------------------------------------------
    # Step 4: Partition into candidate lists
    # ------------------------------------------------------------------
    eligible_candidate_codes: list[str] = []
    review_required_codes: list[str] = []

    for code in incomplete_codes:
        cls = baseline_decisions.get(code, _EligibilityClass.NOT_ELIGIBLE)
        if cls is _EligibilityClass.ELIGIBLE:
            eligible_candidate_codes.append(code)
        elif cls is _EligibilityClass.REVIEW_REQUIRED:
            review_required_codes.append(code)
        # NOT_ELIGIBLE: silently excluded

    # ------------------------------------------------------------------
    # Step 5: Build review_required_courses
    # ------------------------------------------------------------------
    review_required_courses: list[ReviewRequiredCourse] = []
    for code in sorted(review_required_codes):
        meta = plan_course_meta.get(code)
        if meta is None:
            continue
        cp = course_progress_by_code.get(code)
        prev_attempted = (
            cp is not None and cp.state is CourseProgressState.ATTEMPTED_NOT_COMPLETED
        )
        review_required_courses.append(
            ReviewRequiredCourse(
                course_code=code,
                course_name_ar=name_by_code.get(code),
                course_name_en=name_en_by_code.get(code),
                credit_hours=meta.credit_hours,
                requirement_group_code=meta.requirement_group_code,
                requirement_type=meta.requirement_type.value,
                review_reason=baseline_review_reasons.get(
                    code, DecisionReason.PREREQUISITE_LOGIC_UNRESOLVED.value
                ),
                previously_attempted=prev_attempted,
            )
        )

    # ------------------------------------------------------------------
    # Step 6: Filter out satisfied-elective candidates
    # ------------------------------------------------------------------
    # Per Phase 7.1 §11.2: elective candidates in a group with
    # remaining_required_credits == 0 are excluded from ranked_recommendations.
    active_candidate_codes: list[str] = []
    for code in eligible_candidate_codes:
        meta = plan_course_meta.get(code)
        if meta is None:
            continue
        gp = group_progress_by_id.get(meta.requirement_group_id)
        if gp is None:
            continue
        # Exclude elective candidates whose group is already satisfied
        if (
            meta.requirement_type is RequirementType.ELECTIVE
            and gp.remaining_required_credits == ZERO
        ):
            continue
        active_candidate_codes.append(code)

    # ------------------------------------------------------------------
    # Step 7: Per-candidate simulation
    # ------------------------------------------------------------------
    candidates: list[RecommendationCandidate] = []

    for code in active_candidate_codes:
        meta = plan_course_meta[code]
        cp = course_progress_by_code[code]
        gp_before = group_progress_by_id[meta.requirement_group_id]

        # Build hypothetical attempt tuple (immutable; never persisted)
        hypothetical_attempts = student_attempts + (
            StudentCourseAttempt(
                course_code=code,
                outcome=AttemptOutcome.PASSED,
            ),
        )

        # Progress delta
        hyp_progress = calculate_academic_progress(
            progress_catalog,
            hypothetical_attempts,
            reported_cumulative_gpa=reported_cumulative_gpa,
            reported_gpa_scale=reported_gpa_scale,
            reported_earned_credit_hours=reported_earned_credit_hours,
        )
        hyp_group_by_id: dict[str, RequirementGroupProgress] = {
            gp.group_id: gp for gp in hyp_progress.requirement_groups
        }
        gp_after = hyp_group_by_id[meta.requirement_group_id]

        # Effective credit contribution — delta in credited_toward_requirement
        effective_contribution = (
            gp_after.credited_toward_requirement - gp_before.credited_toward_requirement
        )
        # Clamp to non-negative (should always be >= 0 by Phase 6 invariants)
        if effective_contribution < ZERO:
            effective_contribution = ZERO

        completes_group = (not gp_before.is_satisfied) and gp_after.is_satisfied

        # Eligibility simulation — newly eligible count
        newly_eligible_codes: list[str] = []
        for other_code in incomplete_codes:
            if other_code == code:
                continue
            before_cls = baseline_decisions.get(other_code, _EligibilityClass.NOT_ELIGIBLE)
            if before_cls is _EligibilityClass.ELIGIBLE:
                # Already eligible: not a "newly eligible" transition
                continue
            after_result = evaluate_can_take(
                eligibility_catalog,
                CanTakeRequest(
                    study_plan_id=eligibility_catalog.study_plan_id,
                    target_course_code=other_code,
                    student_attempts=hypothetical_attempts,
                ),
            )
            if (
                isinstance(after_result, CanTakeDecision)
                and after_result.decision is Decision.ELIGIBLE
            ):
                newly_eligible_codes.append(other_code)

        newly_eligible_codes.sort()
        newly_eligible_count = len(newly_eligible_codes)

        # P1: required_mandatory_priority
        if meta.requirement_type is RequirementType.REQUIRED:
            p1 = 2 if meta.credit_hours > ZERO else 1
        else:
            p1 = 0

        # P2: group_has_remaining_need
        p2 = 1 if gp_before.remaining_required_credits > ZERO else 0

        # P3: effective_credit_contribution (Decimal — compare as-is, higher is better)
        p3 = effective_contribution

        # P4: completes_requirement_group
        p4 = 1 if completes_group else 0

        # P5: newly_eligible_count
        p5 = newly_eligible_count

        # P6: -display_order (lower display_order ranks higher → negate for tuple sort)
        p6 = -meta.display_order

        # P7: course_code (ascending string — compare as-is; tuple sort is ascending)
        p7 = code

        priority_tuple = (p1, p2, p3, p4, p5, p6, p7)

        # Reason codes
        reason_codes = _compute_reason_codes(
            requirement_type=meta.requirement_type,
            credit_hours=meta.credit_hours,
            gp_before=gp_before,
            completes_group=completes_group,
            newly_eligible_count=newly_eligible_count,
            course_state=cp.state,
        )

        previously_attempted = cp.state is CourseProgressState.ATTEMPTED_NOT_COMPLETED

        candidates.append(
            RecommendationCandidate(
                course_code=code,
                course_name_ar=name_by_code.get(code),
                course_name_en=name_en_by_code.get(code),
                credit_hours=meta.credit_hours,
                requirement_group_code=meta.requirement_group_code,
                requirement_type=meta.requirement_type.value,
                course_state=cp.state.value,
                eligibility_decision=Decision.ELIGIBLE.value,
                effective_credit_contribution=effective_contribution,
                group_remaining_credits_before=gp_before.remaining_required_credits,
                group_remaining_credits_after=gp_after.remaining_required_credits,
                completes_requirement_group=completes_group,
                newly_eligible_count=newly_eligible_count,
                newly_eligible_course_codes=tuple(newly_eligible_codes),
                priority_tuple=priority_tuple,
                rank=0,  # Assigned after sort
                reason_codes=reason_codes,
                previously_attempted=previously_attempted,
            )
        )

    # ------------------------------------------------------------------
    # Step 8: Sort by priority tuple
    # ------------------------------------------------------------------
    # Sort key: negate P1, P2, P4, P5 and P6 is already negated, so that
    # Python's default ascending tuple sort produces the desired order
    # (higher P1 first, higher P2 first, higher P3 first, ...).
    #
    # P7 (course_code) must be ascending, so it is left as-is.
    #
    # Explicit key avoids accidental reversal of any dimension.

    def _sort_key(c: RecommendationCandidate) -> tuple:
        p1, p2, p3, p4, p5, p6, p7 = c.priority_tuple
        return (
            -p1,   # higher P1 first → negate for ascending sort
            -p2,   # higher P2 first
            -p3,   # higher P3 first (Decimal negation)
            -p4,   # completes group first
            -p5,   # higher newly_eligible_count first
            -p6,   # p6 is already -display_order; negating gives +display_order → lower display_order first ✓
            p7,    # ascending course_code
        )

    candidates.sort(key=_sort_key)

    # Assign 1-based ranks (must rebuild since dataclass is frozen)
    ranked: list[RecommendationCandidate] = []
    for rank, c in enumerate(candidates, start=1):
        ranked.append(
            RecommendationCandidate(
                course_code=c.course_code,
                course_name_ar=c.course_name_ar,
                course_name_en=c.course_name_en,
                credit_hours=c.credit_hours,
                requirement_group_code=c.requirement_group_code,
                requirement_type=c.requirement_type,
                course_state=c.course_state,
                eligibility_decision=c.eligibility_decision,
                effective_credit_contribution=c.effective_credit_contribution,
                group_remaining_credits_before=c.group_remaining_credits_before,
                group_remaining_credits_after=c.group_remaining_credits_after,
                completes_requirement_group=c.completes_requirement_group,
                newly_eligible_count=c.newly_eligible_count,
                newly_eligible_course_codes=c.newly_eligible_course_codes,
                priority_tuple=c.priority_tuple,
                rank=rank,
                reason_codes=c.reason_codes,
                previously_attempted=c.previously_attempted,
            )
        )

    # ------------------------------------------------------------------
    # Step 9: excluded_in_progress (informational, sorted)
    # ------------------------------------------------------------------
    excluded_in_progress = tuple(sorted(in_progress_codes))

    return RecommendationResult(
        study_plan_id=study_plan_id,
        recommendation_policy_version=RECOMMENDATION_POLICY_VERSION,
        ranked_recommendations=tuple(ranked),
        review_required_courses=tuple(review_required_courses),
        excluded_in_progress=excluded_in_progress,
        methodology_note=_METHODOLOGY_NOTE,
        limitations=_LIMITATIONS,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _EligibilityClass:
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class _PlanCourseMeta:
    """Lightweight metadata bundle for a single plan course."""

    __slots__ = (
        "course_code",
        "credit_hours",
        "display_order",
        "requirement_group_id",
        "requirement_group_code",
        "requirement_type",
    )

    def __init__(
        self,
        course_code: str,
        credit_hours: Decimal,
        display_order: int,
        requirement_group_id: str,
        requirement_group_code: str,
        requirement_type: RequirementType,
    ) -> None:
        self.course_code = course_code
        self.credit_hours = credit_hours
        self.display_order = display_order
        self.requirement_group_id = requirement_group_id
        self.requirement_group_code = requirement_group_code
        self.requirement_type = requirement_type


def _compute_reason_codes(
    *,
    requirement_type: RequirementType,
    credit_hours: Decimal,
    gp_before: RequirementGroupProgress,
    completes_group: bool,
    newly_eligible_count: int,
    course_state: CourseProgressState,
) -> tuple[RecommendationReason, ...]:
    """Derive the ordered, deterministic set of reason codes for a candidate."""

    codes: list[RecommendationReason] = []

    # Required course marker
    if requirement_type is RequirementType.REQUIRED:
        codes.append(RecommendationReason.REQUIRED_PLAN_COURSE)
        if credit_hours == ZERO:
            codes.append(RecommendationReason.MANDATORY_ZERO_CREDIT_COURSE)

    # Group progress reason
    if gp_before.remaining_required_credits > ZERO:
        if requirement_type is RequirementType.REQUIRED:
            codes.append(RecommendationReason.ADVANCES_REQUIRED_GROUP)
        else:
            codes.append(RecommendationReason.ADVANCES_ELECTIVE_REQUIREMENT)

    # Group completion
    if completes_group:
        codes.append(RecommendationReason.COMPLETES_REQUIREMENT_GROUP)

    # Unlock impact
    if newly_eligible_count == 0:
        codes.append(RecommendationReason.NO_DIRECT_PREREQUISITE_IMPACT)
    elif newly_eligible_count == 1:
        codes.append(RecommendationReason.UNLOCKS_FUTURE_COURSE)
    else:
        codes.append(RecommendationReason.UNLOCKS_MULTIPLE_FUTURE_COURSES)

    # Previous attempt context
    if course_state is CourseProgressState.ATTEMPTED_NOT_COMPLETED:
        codes.append(RecommendationReason.PREVIOUSLY_ATTEMPTED)

    return tuple(codes)

