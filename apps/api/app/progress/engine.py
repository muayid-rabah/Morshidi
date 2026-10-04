"""Pure deterministic academic-progress calculation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from app.progress.models import (
    AcademicProgress,
    AcademicProgressCatalog,
    CourseProgress,
    CourseProgressState,
    ProgressIntegrityError,
    RequirementGroupProgress,
    RequirementType,
)
from app.rules.models import AttemptOutcome, StudentCourseAttempt

ZERO = Decimal("0")


@dataclass(frozen=True)
class ProgressProjection:
    """Project selected PASSED plan courses from a validated Phase 6 baseline.

    Semester planning needs only the credited-plan delta and newly satisfied
    groups. Re-evaluating the entire catalog for every combination is redundant:
    PASSED can change only the selected courses' groups.
    """

    baseline: AcademicProgress
    course_by_code: dict[str, CourseProgress]

    def selected_passes(self, selected_codes: set[str]) -> tuple[Decimal, tuple[str, ...]]:
        added_credits: dict[str, Decimal] = defaultdict(lambda: ZERO)
        added_counts: dict[str, int] = defaultdict(int)
        for code in selected_codes:
            course = self.course_by_code.get(code)
            if course is None or course.state is CourseProgressState.COMPLETED:
                continue
            added_credits[course.requirement_group_id] += course.credit_hours
            added_counts[course.requirement_group_id] += 1

        credited_sum = ZERO
        newly_satisfied: list[str] = []
        for group in self.baseline.requirement_groups:
            completed = group.completed_listed_credits + added_credits[group.group_id]
            credited = min(completed, group.required_credits)
            credited_sum += credited
            completed_count = group.completed_course_count + added_counts[group.group_id]
            satisfied = credited >= group.required_credits and (
                group.requirement_type is RequirementType.ELECTIVE
                or completed_count == group.total_listed_course_count
            )
            if satisfied and not group.is_satisfied:
                newly_satisfied.append(group.group_code)

        completed_plan = min(credited_sum, self.baseline.plan_total_required_credits)
        return completed_plan - self.baseline.completed_plan_credits, tuple(newly_satisfied)


def prepare_progress_projection(baseline: AcademicProgress) -> ProgressProjection:
    """Reuse the fully validated progress result for repeated hypothetical passes."""

    return ProgressProjection(
        baseline=baseline,
        course_by_code={course.course_code: course for course in baseline.courses},
    )


def calculate_academic_progress(
    catalog: AcademicProgressCatalog,
    student_attempts: tuple[StudentCourseAttempt, ...],
    *,
    reported_cumulative_gpa: Decimal | None = None,
    reported_gpa_scale: Decimal | None = None,
    reported_earned_credit_hours: Decimal | None = None,
) -> AcademicProgress:
    """Derive plan progress without mutating or interpreting persisted facts."""

    plan = catalog.study_plan
    if plan.total_credit_hours < ZERO:
        raise ProgressIntegrityError("Study plan has negative total credits")

    ordered_groups = tuple(
        sorted(catalog.requirement_groups, key=lambda row: (row.display_order, row.group_code, row.group_id))
    )
    groups_by_id = {group.group_id: group for group in ordered_groups}
    if len(groups_by_id) != len(ordered_groups):
        raise ProgressIntegrityError("Study plan has duplicate requirement group identities")
    for group in ordered_groups:
        if group.study_plan_id != plan.study_plan_id:
            raise ProgressIntegrityError("Requirement group belongs to another study plan")
        if group.required_credit_hours < ZERO:
            raise ProgressIntegrityError("Requirement group has negative required credits")

    outcomes_by_course: dict[str, set[AttemptOutcome]] = defaultdict(set)
    for attempt in student_attempts:
        outcomes_by_course[attempt.course_code].add(attempt.outcome)

    ordered_plan_courses = tuple(
        sorted(
            catalog.plan_courses,
            key=lambda row: (row.display_order, row.course_code, row.plan_course_id),
        )
    )
    course_codes: set[str] = set()
    courses_by_group: dict[str, list[CourseProgress]] = defaultdict(list)
    course_results: list[CourseProgress] = []
    for plan_course in ordered_plan_courses:
        if plan_course.study_plan_id != plan.study_plan_id:
            raise ProgressIntegrityError("Plan course belongs to another study plan")
        if plan_course.requirement_group_id not in groups_by_id:
            raise ProgressIntegrityError("Plan course refers to an unknown requirement group")
        if plan_course.credit_hours < ZERO:
            raise ProgressIntegrityError("Plan course has negative credits")
        if plan_course.course_code in course_codes:
            raise ProgressIntegrityError("Study plan has duplicate course codes")
        course_codes.add(plan_course.course_code)
        group = groups_by_id[plan_course.requirement_group_id]
        result = CourseProgress(
            course_code=plan_course.course_code,
            credit_hours=plan_course.credit_hours,
            requirement_group_id=group.group_id,
            requirement_group_code=group.group_code,
            state=_course_state(outcomes_by_course.get(plan_course.course_code, set())),
            course_name_ar=plan_course.course_name_ar,
            course_name_en=plan_course.course_name_en,
        )
        courses_by_group[group.group_id].append(result)
        course_results.append(result)

    group_results: list[RequirementGroupProgress] = []
    for group in ordered_groups:
        courses = courses_by_group[group.group_id]
        listed = sum((course.credit_hours for course in courses), ZERO)
        completed = sum(
            (course.credit_hours for course in courses if course.state is CourseProgressState.COMPLETED),
            ZERO,
        )
        in_progress = sum(
            (course.credit_hours for course in courses if course.state is CourseProgressState.IN_PROGRESS),
            ZERO,
        )
        credited = min(completed, group.required_credit_hours)
        remaining = max(group.required_credit_hours - credited, ZERO)
        completed_count = _count(courses, CourseProgressState.COMPLETED)
        credit_condition = credited >= group.required_credit_hours
        mandatory_condition = completed_count == len(courses)
        is_satisfied = credit_condition and (
            group.requirement_type is RequirementType.ELECTIVE or mandatory_condition
        )
        group_results.append(
            RequirementGroupProgress(
                group_id=group.group_id,
                group_code=group.group_code,
                name_ar=group.name_ar,
                name_en=group.name_en,
                scope=group.scope,
                requirement_type=group.requirement_type,
                required_credits=group.required_credit_hours,
                listed_credits=listed,
                completed_listed_credits=completed,
                credited_toward_requirement=credited,
                in_progress_listed_credits=in_progress,
                remaining_required_credits=remaining,
                completed_course_count=completed_count,
                in_progress_course_count=_count(courses, CourseProgressState.IN_PROGRESS),
                attempted_not_completed_count=_count(
                    courses, CourseProgressState.ATTEMPTED_NOT_COMPLETED
                ),
                not_attempted_count=_count(courses, CourseProgressState.NOT_ATTEMPTED),
                total_listed_course_count=len(courses),
                is_satisfied=is_satisfied,
            )
        )

    credited_sum = sum((group.credited_toward_requirement for group in group_results), ZERO)
    completed_plan = min(credited_sum, plan.total_credit_hours)
    remaining_plan = max(plan.total_credit_hours - completed_plan, ZERO)
    in_progress_plan = sum(
        (course.credit_hours for course in course_results if course.state is CourseProgressState.IN_PROGRESS),
        ZERO,
    )
    satisfied_count = sum(group.is_satisfied for group in group_results)
    return AcademicProgress(
        study_plan_id=plan.study_plan_id,
        plan_total_required_credits=plan.total_credit_hours,
        completed_plan_credits=completed_plan,
        in_progress_plan_credits=in_progress_plan,
        remaining_plan_credits=remaining_plan,
        satisfied_requirement_group_count=satisfied_count,
        total_requirement_group_count=len(group_results),
        all_modeled_plan_requirements_satisfied=satisfied_count == len(group_results),
        requirement_groups=tuple(group_results),
        courses=tuple(course_results),
        reported_cumulative_gpa=reported_cumulative_gpa,
        reported_gpa_scale=reported_gpa_scale,
        reported_earned_credit_hours=reported_earned_credit_hours,
    )


def _course_state(outcomes: set[AttemptOutcome]) -> CourseProgressState:
    if AttemptOutcome.PASSED in outcomes:
        return CourseProgressState.COMPLETED
    if AttemptOutcome.IN_PROGRESS in outcomes:
        return CourseProgressState.IN_PROGRESS
    if AttemptOutcome.FAILED in outcomes or AttemptOutcome.WITHDRAWN in outcomes:
        return CourseProgressState.ATTEMPTED_NOT_COMPLETED
    return CourseProgressState.NOT_ATTEMPTED


def _count(courses: list[CourseProgress], state: CourseProgressState) -> int:
    return sum(course.state is state for course in courses)
