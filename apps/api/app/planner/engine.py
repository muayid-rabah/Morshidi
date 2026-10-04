"""Pure deterministic semester planning engine (Phase 8.2).

No FastAPI, Starlette, Supabase, httpx, or I/O dependency is permitted in this module.
It reuses Phase 5 (evaluate_can_take), Phase 6 (calculate_academic_progress),
and Phase 7 (RecommendationResult) without mutating any state or duplicating logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from time import monotonic
from typing import Callable, Mapping
from app.planner.learning_profile import CourseLearningProfile, MAX_MEMORIZATION_HEAVY

from app.planner.models import (
    DEFAULT_CANDIDATE_WINDOW_SIZE,
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
from app.progress.engine import calculate_academic_progress, prepare_progress_projection
from app.progress.models import (
    AcademicProgressCatalog,
    CourseProgressState,
    RequirementType,
)
from app.recommendations.models import (
    RecommendationCandidate,
    RecommendationResult,
)
from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CanTakeDecision,
    CanTakeRequest,
    Decision,
    DependencyType,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)

# ---------------------------------------------------------------------------
# Metadata & Disclaimers
# ---------------------------------------------------------------------------

_METHODOLOGY_NOTE = (
    "These semester plan options are deterministic course combinations generated from "
    "your verified academic study plan, degree progress state, and planning preferences. "
    "They indicate combinations of courses that are academically coherent to register together "
    "in your next registration period. They do not constitute official university registration approval, "
    "do not guarantee timetable compatibility or course availability, and do not reflect "
    "institutional academic advising."
)

_LIMITATIONS: tuple[str, ...] = (
    "Planning is bounded strictly by modeled academic study plan structure.",
    "Search is exact within the candidate window (top M eligible candidates under the supplied ranking); results are not guaranteed globally optimal across unexamined eligible courses outside this window.",
    "Course offering schedules, section capacities, and timetable time conflicts are unmodeled.",
    "Midterm and final examination clash detection is unmodeled.",
    "No course equivalency, substitution, or transfer-credit model exists.",
    "Modeled course difficulty may reorder eligible candidates when supplied; it is not trained historical outcome evidence, instructor rating, or grading-leniency evidence.",
    "No GPA calculation, GPA probation rules, or GPA optimization exists.",
    "max_credit_hours represents a user planning preference, not an authorized university registration limit.",
    "Derived plan options do not constitute official university graduation clearance.",
    "Prerequisite evaluation adheres strictly to verified dependency groups; courses requiring unresolved review are excluded.",
)


@dataclass
class _EvaluatedCombination:
    courses: tuple[PlannedCourseEntry, ...]
    total_credit_hours: Decimal
    total_courses: int
    mandatory_course_count: int
    zero_credit_required_count: int
    modeled_credit_delta: Decimal
    newly_satisfied_requirement_group_codes: tuple[str, ...]
    newly_satisfied_requirement_group_count: int
    newly_eligible_course_codes: tuple[str, ...]
    newly_eligible_count: int
    recommendation_rank_sum: int
    adaptive_score_sum: int
    canonical_course_codes: tuple[str, ...]
    priority_tuple: tuple[int, int, Decimal, int, Decimal, int, tuple[str, ...]]
    has_previously_attempted: bool
    reason_codes: tuple[PlanReasonCode, ...] = ()


# ---------------------------------------------------------------------------
# Public Pure Planner Engine
# ---------------------------------------------------------------------------


def plan_semester(
    progress_catalog: AcademicProgressCatalog,
    eligibility_catalog: CanTakeCatalog,
    student_attempts: tuple[StudentCourseAttempt, ...],
    recommendation_result: RecommendationResult,
    constraints: PlannerConstraints,
    *,
    candidate_window_size: int = DEFAULT_CANDIDATE_WINDOW_SIZE,
    reported_cumulative_gpa: Decimal | None = None,
    reported_gpa_scale: Decimal | None = None,
    reported_earned_credit_hours: Decimal | None = None,
    check_budget: Callable[[], None] | None = None,
    metrics: dict[str, float | int] | None = None,
    adaptive_scores: Mapping[str, int] | None = None,
    learning_profiles: Mapping[str, CourseLearningProfile] | None = None,
    accept_heavy_balance: bool = False,
) -> SemesterPlannerResult:
    """Generate and rank optimal semester course combinations deterministically.

    Parameters
    ----------
    progress_catalog:
        The AcademicProgressCatalog for the student's study plan.
    eligibility_catalog:
        The CanTakeCatalog containing verified plan-course rules.
    student_attempts:
        Immutable tuple of persisted student course attempts.
    recommendation_result:
        Precomputed Phase 7 recommendation result.
    constraints:
        User planning constraints (max_credit_hours, max_courses, max_options).
    candidate_window_size:
        Top M candidates from Phase 7 to consider during combinatorial search.
    """
    if isinstance(candidate_window_size, bool) or not isinstance(candidate_window_size, int):
        raise PlannerConstraintError("candidate_window_size must be an integer")
    if candidate_window_size < 1:
        raise PlannerConstraintError("candidate_window_size must be at least 1")
    if not isinstance(accept_heavy_balance, bool):
        raise PlannerConstraintError("accept_heavy_balance must be boolean")

    def record(name: str, started: float) -> None:
        if metrics is not None:
            metrics[name] = metrics.get(name, 0) + (monotonic() - started) * 1000

    if check_budget is not None:
        check_budget()

    study_plan_id = progress_catalog.study_plan.study_plan_id

    # 1. Structural Integrity Invariant Checks
    if eligibility_catalog.study_plan_id != study_plan_id:
        raise PlannerIntegrityError("Mismatched study_plan_id between progress and eligibility catalogs")
    if recommendation_result.study_plan_id != study_plan_id:
        raise PlannerIntegrityError("Mismatched study_plan_id between catalog and recommendation result")

    plan_courses_by_code = {pc.course_code: pc for pc in progress_catalog.plan_courses}
    if learning_profiles is not None and (
        set(learning_profiles) != set(plan_courses_by_code)
        or any(profile.course_code != code for code, profile in learning_profiles.items())
    ):
        raise PlannerIntegrityError("Incomplete or foreign course learning profiles")
    for cand in recommendation_result.ranked_recommendations:
        if cand.course_code not in plan_courses_by_code:
            raise PlannerIntegrityError(
                f"Recommendation candidate '{cand.course_code}' is absent from progress catalog plan courses"
            )

    names_en_by_code: dict[str, str | None] = {
        rule.course_code: rule.target_name_en for rule in eligibility_catalog.plan_courses
    }

    # 2. Candidate Universe Bounding (Top M).  Adaptive preference never adds
    # an ineligible course; the Phase 7 eligible set remains authoritative.
    if adaptive_scores is not None:
        eligible_codes = {item.course_code for item in recommendation_result.ranked_recommendations}
        if any(code not in eligible_codes or isinstance(score, bool) or not isinstance(score, int)
               or score < 0 or score > 100 for code, score in adaptive_scores.items()):
            raise PlannerIntegrityError("Invalid adaptive scores for eligible candidate set")
    applied_window_size = candidate_window_size
    ranked_candidates = recommendation_result.ranked_recommendations
    if adaptive_scores is not None:
        ranked_candidates = tuple(sorted(ranked_candidates, key=lambda item: (
            -adaptive_scores.get(item.course_code, 0), item.rank, item.course_code,
        )))
    candidate_pool = ranked_candidates[:applied_window_size]
    evaluated_candidate_count = len(candidate_pool)

    # Empty candidate pool edge case
    if evaluated_candidate_count == 0:
        return SemesterPlannerResult(
            study_plan_id=study_plan_id,
            semester_planner_policy_version=SEMESTER_PLANNER_POLICY_VERSION,
            planning_scope=PLANNING_SCOPE,
            constraints=constraints,
            candidate_window_size=applied_window_size,
            eligible_ranked_candidate_count=len(recommendation_result.ranked_recommendations),
            evaluated_candidate_count=0,
            valid_combination_count=0,
            plan_options=(),
            review_required_courses=tuple(rc.course_code for rc in recommendation_result.review_required_courses),
            excluded_in_progress=recommendation_result.excluded_in_progress,
            methodology_note=_METHODOLOGY_NOTE,
            limitations=_LIMITATIONS,
        )

    # 3. Current Academic Baseline
    phase_started = monotonic()
    baseline_progress = calculate_academic_progress(
        progress_catalog,
        student_attempts,
        reported_cumulative_gpa=reported_cumulative_gpa,
        reported_gpa_scale=reported_gpa_scale,
        reported_earned_credit_hours=reported_earned_credit_hours,
    )
    progress_projection = prepare_progress_projection(baseline_progress)

    # Identify incomplete plan courses and baseline eligible courses
    completed_or_ip_codes = {
        cp.course_code
        for cp in baseline_progress.courses
        if cp.state in (CourseProgressState.COMPLETED, CourseProgressState.IN_PROGRESS)
    }

    incomplete_plan_courses = [
        pc.course_code
        for pc in progress_catalog.plan_courses
        if pc.course_code not in completed_or_ip_codes
    ]
    record("remaining_courses_ms", phase_started)

    phase_started = monotonic()
    baseline_eligible_codes: set[str] = set()
    for code in incomplete_plan_courses:
        if check_budget is not None:
            check_budget()
        decision = evaluate_can_take(
            eligibility_catalog,
            CanTakeRequest(
                study_plan_id=study_plan_id,
                target_course_code=code,
                student_attempts=student_attempts,
            ),
        )
        if isinstance(decision, CanTakeDecision) and decision.decision is Decision.ELIGIBLE:
            baseline_eligible_codes.add(code)
    record("baseline_eligibility_ms", phase_started)

    # A selected course can unlock only targets that cite it as a prerequisite.
    # Keep the authoritative evaluator for those targets; this index only avoids
    # repeating decisions that cannot change from the baseline.
    unlock_targets_by_option: dict[str, set[str]] = {}
    incomplete_codes = set(incomplete_plan_courses)
    for rule in eligibility_catalog.plan_courses:
        if (
            rule.course_code not in incomplete_codes
            or rule.course_code in baseline_eligible_codes
            or rule.prerequisite_logic_status is not PrerequisiteLogicStatus.VERIFIED
        ):
            continue
        for group in rule.dependency_groups:
            if group.dependency_type is DependencyType.PREREQUISITE:
                for option_code in group.option_course_codes:
                    unlock_targets_by_option.setdefault(option_code, set()).add(rule.course_code)

    # 4. Deterministic Depth-First Branch-and-Bound Search
    phase_started = monotonic()
    valid_combinations: list[tuple[RecommendationCandidate, ...]] = []
    visited_nodes = 0

    def _dfs(index: int, current_courses: list[RecommendationCandidate], current_credits: Decimal) -> None:
        nonlocal visited_nodes
        visited_nodes += 1
        if check_budget is not None and visited_nodes % 128 == 0:
            check_budget()
        if index == len(candidate_pool):
            if current_courses:
                valid_combinations.append(tuple(current_courses))
            return

        cand = candidate_pool[index]

        # Branch 1: Include candidate if within credit and course constraints
        can_include = True
        if current_credits + cand.credit_hours > constraints.max_credit_hours:
            can_include = False
        if constraints.max_courses is not None and len(current_courses) + 1 > constraints.max_courses:
            can_include = False

        if can_include:
            current_courses.append(cand)
            _dfs(index + 1, current_courses, current_credits + cand.credit_hours)
            current_courses.pop()

        # Branch 2: Exclude candidate
        _dfs(index + 1, current_courses, current_credits)

    _dfs(0, [], Decimal("0"))
    record("combination_generation_ms", phase_started)
    if metrics is not None:
        metrics["valid_combinations"] = metrics.get("valid_combinations", 0) + len(valid_combinations)

    # Empty valid combinations edge case
    if not valid_combinations:
        return SemesterPlannerResult(
            study_plan_id=study_plan_id,
            semester_planner_policy_version=SEMESTER_PLANNER_POLICY_VERSION,
            planning_scope=PLANNING_SCOPE,
            constraints=constraints,
            candidate_window_size=applied_window_size,
            eligible_ranked_candidate_count=len(recommendation_result.ranked_recommendations),
            evaluated_candidate_count=evaluated_candidate_count,
            valid_combination_count=0,
            plan_options=(),
            review_required_courses=tuple(rc.course_code for rc in recommendation_result.review_required_courses),
            excluded_in_progress=recommendation_result.excluded_in_progress,
            methodology_note=_METHODOLOGY_NOTE,
            limitations=_LIMITATIONS,
        )

    # 5. Whole-Plan Simulation for Each Valid Combination
    evaluated_combinations: list[_EvaluatedCombination] = []

    for combination in valid_combinations:
        if check_budget is not None:
            check_budget()
        plan_course_codes = {c.course_code for c in combination}

        # Construct in-memory synthetic PASSED attempts
        synthetic_attempts = tuple(
            StudentCourseAttempt(course_code=c.course_code, outcome=AttemptOutcome.PASSED)
            for c in combination
        )
        combined_attempts = student_attempts + synthetic_attempts

        # Phase 6 Progress Simulation
        phase_started = monotonic()
        credit_delta, newly_satisfied_groups = progress_projection.selected_passes(plan_course_codes)
        newly_satisfied_group_count = len(newly_satisfied_groups)
        record("semester_simulation_ms", phase_started)

        # Phase 5 Eligibility Simulation (Unlocks)
        phase_started = monotonic()
        newly_unlocked: list[str] = []
        affected_targets: set[str] = set()
        for selected_code in plan_course_codes:
            affected_targets.update(unlock_targets_by_option.get(selected_code, ()))
        for target_code in sorted(affected_targets):
            if target_code in plan_course_codes:
                continue

            target_decision = evaluate_can_take(
                eligibility_catalog,
                CanTakeRequest(
                    study_plan_id=study_plan_id,
                    target_course_code=target_code,
                    student_attempts=combined_attempts,
                ),
            )
            if isinstance(target_decision, CanTakeDecision) and target_decision.decision is Decision.ELIGIBLE:
                newly_unlocked.append(target_code)

        newly_eligible_course_codes = tuple(sorted(newly_unlocked))
        newly_eligible_count = len(newly_eligible_course_codes)
        record("eligibility_calculation_ms", phase_started)

        # Plan metric calculations
        phase_started = monotonic()
        total_credit_hours = sum((c.credit_hours for c in combination), Decimal("0"))
        total_courses = len(combination)
        mandatory_course_count = sum(
            1
            for c in combination
            if c.requirement_type in (RequirementType.REQUIRED.value, "required")
        )
        zero_credit_required_count = sum(
            1
            for c in combination
            if c.requirement_type in (RequirementType.REQUIRED.value, "required") and c.credit_hours == Decimal("0")
        )
        recommendation_rank_sum = sum(c.rank for c in combination)
        adaptive_score_sum = sum(adaptive_scores.get(c.course_code, 0) for c in combination) if adaptive_scores else 0
        canonical_course_codes = tuple(sorted(c.course_code for c in combination))
        has_previously_attempted = any(c.previously_attempted for c in combination)

        priority_tuple = (
            mandatory_course_count,
            newly_satisfied_group_count,
            credit_delta,
            newly_eligible_count,
            total_credit_hours,
            recommendation_rank_sum,
            canonical_course_codes,
        )

        # Build PlannedCourseEntry items ordered by display_order, course_code
        ordered_candidates = sorted(
            combination,
            key=lambda c: (plan_courses_by_code[c.course_code].display_order, c.course_code),
        )
        course_entries = tuple(
            PlannedCourseEntry(
                course_code=c.course_code,
                course_name_ar=c.course_name_ar,
                course_name_en=names_en_by_code.get(c.course_code) or c.course_name_en,
                credit_hours=c.credit_hours,
                requirement_group_code=c.requirement_group_code,
                requirement_type=c.requirement_type,
                phase7_rank=c.rank,
                previously_attempted=c.previously_attempted,
                display_order=plan_courses_by_code[c.course_code].display_order,
            )
            for c in ordered_candidates
        )

        evaluated_combinations.append(
            _EvaluatedCombination(
                courses=course_entries,
                total_credit_hours=total_credit_hours,
                total_courses=total_courses,
                mandatory_course_count=mandatory_course_count,
                zero_credit_required_count=zero_credit_required_count,
                modeled_credit_delta=credit_delta,
                newly_satisfied_requirement_group_codes=newly_satisfied_groups,
                newly_satisfied_requirement_group_count=newly_satisfied_group_count,
                newly_eligible_course_codes=newly_eligible_course_codes,
                newly_eligible_count=newly_eligible_count,
                recommendation_rank_sum=recommendation_rank_sum,
                adaptive_score_sum=adaptive_score_sum,
                canonical_course_codes=canonical_course_codes,
                priority_tuple=priority_tuple,
                has_previously_attempted=has_previously_attempted,
            )
        )
        record("scenario_generation_ms", phase_started)

    # 6. Global Maximum Modeled Credit Progress Across ALL Valid Combinations
    phase_started = monotonic()
    max_modeled_credit_delta = max(
        (item.modeled_credit_delta for item in evaluated_combinations),
        default=Decimal("0"),
    )

    # 7. Reason Code Assignment
    for item in evaluated_combinations:
        codes: list[PlanReasonCode] = []

        if item.mandatory_course_count > 0:
            codes.append(PlanReasonCode.CONTAINS_MANDATORY_COURSES)

        if item.zero_credit_required_count > 0:
            codes.append(PlanReasonCode.INCLUDES_ZERO_CREDIT_REQUIRED)

        if item.newly_satisfied_requirement_group_count == 1:
            codes.append(PlanReasonCode.COMPLETES_REQUIREMENT_GROUP)
        elif item.newly_satisfied_requirement_group_count >= 2:
            codes.append(PlanReasonCode.COMPLETES_MULTIPLE_REQUIREMENT_GROUPS)

        if item.modeled_credit_delta == max_modeled_credit_delta:
            codes.append(PlanReasonCode.MAXIMIZES_MODELED_CREDIT_PROGRESS)

        if item.newly_eligible_count == 0:
            codes.append(PlanReasonCode.NO_DIRECT_PREREQUISITE_IMPACT)
        elif item.newly_eligible_count == 1:
            codes.append(PlanReasonCode.UNLOCKS_FUTURE_COURSE)
        else:
            codes.append(PlanReasonCode.UNLOCKS_MULTIPLE_FUTURE_COURSES)

        if item.total_credit_hours == constraints.max_credit_hours:
            codes.append(PlanReasonCode.USES_FULL_CREDIT_PREFERENCE)

        if item.has_previously_attempted:
            codes.append(PlanReasonCode.INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE)

        item.reason_codes = tuple(codes)

    def heavy_count(item: _EvaluatedCombination) -> int:
        return sum(learning_profiles[course.course_code].memorization_heavy
                   for course in item.courses) if learning_profiles is not None else 0

    # 8. Deterministic Lexicographic Sorting
    def _sort_key(item: _EvaluatedCombination) -> tuple:
        return (
            -item.mandatory_course_count,
            -item.newly_satisfied_requirement_group_count,
            -item.modeled_credit_delta,
            -item.newly_eligible_count,
            -item.total_credit_hours,
            -item.adaptive_score_sum,
            item.recommendation_rank_sum,
            heavy_count(item),
            item.canonical_course_codes,
        )

    sorted_combinations = sorted(evaluated_combinations, key=_sort_key)

    balanced = [item for item in sorted_combinations
                if heavy_count(item) <= MAX_MEMORIZATION_HEAVY]
    relaxation_required = bool(learning_profiles and sorted_combinations and
                               (not balanced or max(item.total_credit_hours for item in balanced) <
                                min(constraints.max_credit_hours,
                                    max(item.total_credit_hours for item in sorted_combinations))))
    if learning_profiles is not None and not accept_heavy_balance:
        sorted_combinations = balanced

    # 9. Top-K Selection and Final Option Presentation
    top_k = sorted_combinations[: constraints.max_options]
    plan_options = tuple(
        SemesterPlanOption(
            rank=idx + 1,
            courses=item.courses,
            total_credit_hours=item.total_credit_hours,
            total_courses=item.total_courses,
            mandatory_course_count=item.mandatory_course_count,
            zero_credit_required_count=item.zero_credit_required_count,
            completed_plan_credit_delta=item.modeled_credit_delta,
            newly_satisfied_requirement_group_codes=item.newly_satisfied_requirement_group_codes,
            newly_satisfied_requirement_group_count=item.newly_satisfied_requirement_group_count,
            newly_eligible_course_codes=item.newly_eligible_course_codes,
            newly_eligible_count=item.newly_eligible_count,
            recommendation_rank_sum=item.recommendation_rank_sum,
            priority_tuple=item.priority_tuple,
            reason_codes=item.reason_codes,
            memorization_heavy_count=heavy_count(item),
            learning_type_counts=tuple(sorted((kind, sum(
                learning_profiles[c.course_code].primary_type == kind for c in item.courses))
                for kind in {learning_profiles[c.course_code].primary_type for c in item.courses}))
                if learning_profiles is not None else (),
            estimated_workload=("HIGH" if item.total_credit_hours >= Decimal("18") else
                                "MODERATE" if item.total_credit_hours >= Decimal("12") else "LIGHT")
                if learning_profiles is not None else "UNKNOWN",
            balance_warning=("BALANCE_CONSTRAINT_RELAXATION_REQUIRED: extra heavy course(s) " + ", ".join(
                [f"{course.course_name_ar or course.course_name_en} ({course.course_code})"
                 if course.course_name_ar or course.course_name_en else course.course_code for course in item.courses
                 if learning_profiles[course.course_code].memorization_heavy]
                [MAX_MEMORIZATION_HEAVY:])
                             if heavy_count(item) > MAX_MEMORIZATION_HEAVY else None),
        )
        for idx, item in enumerate(top_k)
    )
    record("path_ranking_ms", phase_started)

    return SemesterPlannerResult(
        study_plan_id=study_plan_id,
        semester_planner_policy_version=SEMESTER_PLANNER_POLICY_VERSION,
        planning_scope=PLANNING_SCOPE,
        constraints=constraints,
        candidate_window_size=applied_window_size,
        eligible_ranked_candidate_count=len(recommendation_result.ranked_recommendations),
        evaluated_candidate_count=evaluated_candidate_count,
        valid_combination_count=len(valid_combinations),
        plan_options=plan_options,
        review_required_courses=tuple(rc.course_code for rc in recommendation_result.review_required_courses),
        excluded_in_progress=recommendation_result.excluded_in_progress,
        methodology_note=_METHODOLOGY_NOTE,
        limitations=_LIMITATIONS,
        balance_relaxation_required=relaxation_required,
    )
