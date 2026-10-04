"""Exhaustive pure tests for deterministic academic-progress semantics."""

from decimal import Decimal

import pytest

from app.progress.engine import calculate_academic_progress, prepare_progress_projection
from app.progress.models import (
    AcademicProgressCatalog,
    CourseProgressState,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.rules.models import AttemptOutcome, CourseCatalogStatus, StudentCourseAttempt

PLAN = "10000000-0000-0000-0000-000000000005"
REQUIRED = "10000000-0000-0000-0000-000000000011"
ELECTIVE = "10000000-0000-0000-0000-000000000012"


def catalog(total: str = "12") -> AcademicProgressCatalog:
    groups = (
        ProgressRequirementGroup(
            REQUIRED, PLAN, "REQUIRED", "إجباري", "Required", "major",
            RequirementType.REQUIRED, Decimal("6"), 2,
        ),
        ProgressRequirementGroup(
            ELECTIVE, PLAN, "ELECTIVE", "اختياري", "Elective", "major",
            RequirementType.ELECTIVE, Decimal("6"), 1,
        ),
    )
    courses = (
        ProgressPlanCourse("pc-r2", PLAN, REQUIRED, "R-ZERO", CourseCatalogStatus.KNOWN, Decimal("0"), 4),
        ProgressPlanCourse("pc-e3", PLAN, ELECTIVE, "E3", CourseCatalogStatus.KNOWN, Decimal("3"), 3),
        ProgressPlanCourse("pc-r1", PLAN, REQUIRED, "R1", CourseCatalogStatus.KNOWN, Decimal("3"), 1),
        ProgressPlanCourse("pc-e1", PLAN, ELECTIVE, "E1", CourseCatalogStatus.KNOWN, Decimal("3"), 1),
        ProgressPlanCourse("pc-r3", PLAN, REQUIRED, "R2", CourseCatalogStatus.KNOWN, Decimal("3"), 3),
        ProgressPlanCourse("pc-e2", PLAN, ELECTIVE, "E2", CourseCatalogStatus.KNOWN, Decimal("3"), 2),
    )
    return AcademicProgressCatalog(ProgressStudyPlan(PLAN, Decimal(total)), groups, courses)


def attempts(*values: tuple[str, AttemptOutcome]) -> tuple[StudentCourseAttempt, ...]:
    return tuple(StudentCourseAttempt(code, outcome) for code, outcome in values)


def result(*values: tuple[str, AttemptOutcome], total: str = "12"):
    return calculate_academic_progress(catalog(total), attempts(*values))


def by_course(progress):
    return {row.course_code: row for row in progress.courses}


def by_group(progress):
    return {row.group_code: row for row in progress.requirement_groups}


@pytest.mark.parametrize("total", ["9", "12"])
@pytest.mark.parametrize(
    "history",
    [
        (),
        (("R1", AttemptOutcome.PASSED),),
        (("E1", AttemptOutcome.PASSED), ("R2", AttemptOutcome.IN_PROGRESS)),
        (("R1", AttemptOutcome.PASSED), ("R2", AttemptOutcome.PASSED)),
        (("R-ZERO", AttemptOutcome.FAILED), ("E3", AttemptOutcome.WITHDRAWN)),
    ],
)
def test_projected_passes_match_full_phase6_recalculation(total, history) -> None:
    from itertools import combinations

    progress_catalog = catalog(total)
    baseline_attempts = attempts(*history)
    baseline = calculate_academic_progress(progress_catalog, baseline_attempts)
    projection = prepare_progress_projection(baseline)
    codes = tuple(course.course_code for course in progress_catalog.plan_courses)
    for size in range(len(codes) + 1):
        for selected in combinations(codes, size):
            projected_delta, projected_groups = projection.selected_passes(set(selected))
            hypothetical = calculate_academic_progress(
                progress_catalog,
                baseline_attempts + attempts(*((code, AttemptOutcome.PASSED) for code in selected)),
            )
            expected_groups = tuple(
                group.group_code
                for group, original in zip(hypothetical.requirement_groups, baseline.requirement_groups)
                if group.is_satisfied and not original.is_satisfied
            )
            assert projected_delta == hypothetical.completed_plan_credits - baseline.completed_plan_credits
            assert projected_groups == expected_groups


def test_no_attempts_marks_every_plan_course_not_attempted() -> None:
    progress = result()
    assert {row.state for row in progress.courses} == {CourseProgressState.NOT_ATTEMPTED}
    assert progress.completed_plan_credits == 0
    assert progress.remaining_plan_credits == 12
    assert not progress.all_modeled_plan_requirements_satisfied


@pytest.mark.parametrize(
    ("history", "expected"),
    [
        ((AttemptOutcome.PASSED,), CourseProgressState.COMPLETED),
        ((AttemptOutcome.FAILED,), CourseProgressState.ATTEMPTED_NOT_COMPLETED),
        ((AttemptOutcome.WITHDRAWN,), CourseProgressState.ATTEMPTED_NOT_COMPLETED),
        ((AttemptOutcome.IN_PROGRESS,), CourseProgressState.IN_PROGRESS),
        ((AttemptOutcome.FAILED, AttemptOutcome.PASSED), CourseProgressState.COMPLETED),
        ((AttemptOutcome.PASSED, AttemptOutcome.FAILED), CourseProgressState.COMPLETED),
        ((AttemptOutcome.IN_PROGRESS, AttemptOutcome.PASSED), CourseProgressState.COMPLETED),
        ((AttemptOutcome.PASSED, AttemptOutcome.PASSED), CourseProgressState.COMPLETED),
        ((AttemptOutcome.FAILED, AttemptOutcome.IN_PROGRESS), CourseProgressState.IN_PROGRESS),
    ],
)
def test_course_state_uses_all_attempts_with_fixed_priority(history, expected) -> None:
    progress = result(*(("R1", outcome) for outcome in history))
    assert by_course(progress)["R1"].state is expected


def test_required_group_counts_each_completed_course_once() -> None:
    progress = result(
        ("R1", AttemptOutcome.PASSED),
        ("R1", AttemptOutcome.PASSED),
        ("R2", AttemptOutcome.PASSED),
        ("R-ZERO", AttemptOutcome.PASSED),
    )
    required = by_group(progress)["REQUIRED"]
    assert required.completed_listed_credits == 6
    assert required.completed_course_count == 3
    assert required.credited_toward_requirement == 6
    assert required.is_satisfied


def test_elective_excess_is_preserved_but_capped_for_requirement_and_plan() -> None:
    progress = result(*((code, AttemptOutcome.PASSED) for code in ("E1", "E2", "E3")))
    elective = by_group(progress)["ELECTIVE"]
    assert elective.completed_listed_credits == 9
    assert elective.credited_toward_requirement == 6
    assert elective.remaining_required_credits == 0
    assert elective.is_satisfied
    assert progress.completed_plan_credits == 6


def test_university_style_twelve_of_nine_is_credited_as_nine() -> None:
    base = catalog("9")
    group = ProgressRequirementGroup(
        ELECTIVE, PLAN, "UNIVERSITY_ELECTIVE", "جامعي", None, "university",
        RequirementType.ELECTIVE, Decimal("9"), 1,
    )
    courses = tuple(
        ProgressPlanCourse(f"p{index}", PLAN, ELECTIVE, f"U{index}", CourseCatalogStatus.KNOWN, Decimal("3"), index)
        for index in range(1, 5)
    )
    progress = calculate_academic_progress(
        AcademicProgressCatalog(base.study_plan, (group,), courses),
        attempts(*((course.course_code, AttemptOutcome.PASSED) for course in courses)),
    )
    university = progress.requirement_groups[0]
    assert university.completed_listed_credits == 12
    assert university.credited_toward_requirement == 9
    assert progress.completed_plan_credits == 9
    assert progress.remaining_plan_credits == 0


def test_elective_below_threshold_remains_unsatisfied() -> None:
    elective = by_group(result(("E1", AttemptOutcome.PASSED)))["ELECTIVE"]
    assert elective.credited_toward_requirement == 3
    assert elective.remaining_required_credits == 3
    assert not elective.is_satisfied


def test_required_zero_credit_course_blocks_then_allows_satisfaction() -> None:
    positive_passes = (("R1", AttemptOutcome.PASSED), ("R2", AttemptOutcome.PASSED))
    incomplete = by_group(result(*positive_passes))["REQUIRED"]
    complete = by_group(result(*positive_passes, ("R-ZERO", AttemptOutcome.PASSED)))["REQUIRED"]
    assert incomplete.credited_toward_requirement == 6
    assert not incomplete.is_satisfied
    assert complete.completed_listed_credits == 6
    assert complete.completed_course_count == 3
    assert complete.is_satisfied


def test_in_progress_failed_and_withdrawn_are_not_completed_credits() -> None:
    progress = result(
        ("R1", AttemptOutcome.IN_PROGRESS),
        ("R2", AttemptOutcome.FAILED),
        ("R-ZERO", AttemptOutcome.WITHDRAWN),
    )
    required = by_group(progress)["REQUIRED"]
    assert required.in_progress_listed_credits == 3
    assert required.completed_listed_credits == 0
    assert required.in_progress_course_count == 1
    assert required.attempted_not_completed_count == 2
    assert progress.in_progress_plan_credits == 3
    assert progress.completed_plan_credits == 0


def test_course_outside_plan_never_appears_or_counts() -> None:
    progress = result(("0300103", AttemptOutcome.PASSED))
    assert "0300103" not in by_course(progress)
    assert progress.completed_plan_credits == 0


def test_completed_and_remaining_plan_credits_are_bounded() -> None:
    progress = result(
        *((code, AttemptOutcome.PASSED) for code in ("R1", "R2", "R-ZERO", "E1", "E2", "E3")),
        total="10",
    )
    assert progress.completed_plan_credits == 10
    assert progress.remaining_plan_credits == 0


def test_group_and_course_ordering_uses_persisted_order_then_stable_ties() -> None:
    progress = result()
    assert [row.group_code for row in progress.requirement_groups] == ["ELECTIVE", "REQUIRED"]
    assert [row.course_code for row in progress.courses] == ["E1", "R1", "E2", "E3", "R2", "R-ZERO"]


def test_reported_facts_are_passed_through_and_not_reconciled() -> None:
    progress = calculate_academic_progress(
        catalog(),
        attempts(("R1", AttemptOutcome.PASSED)),
        reported_cumulative_gpa=Decimal("3.25"),
        reported_gpa_scale=Decimal("4"),
        reported_earned_credit_hours=Decimal("99"),
    )
    assert progress.reported_cumulative_gpa == Decimal("3.25")
    assert progress.reported_gpa_scale == Decimal("4")
    assert progress.reported_earned_credit_hours == Decimal("99")
    assert progress.completed_plan_credits == 3


def test_engine_inputs_have_no_raw_grade_or_prerequisite_channel() -> None:
    assert "raw_grade" not in calculate_academic_progress.__annotations__
    assert "raw_prerequisite" not in calculate_academic_progress.__annotations__
