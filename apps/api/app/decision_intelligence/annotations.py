"""Post-result annotations that cannot alter Phase 8 or Phase 9 behavior."""

from __future__ import annotations

from app.decision_intelligence.models import (
    AnnotatedResult,
    CourseIntelligenceAnnotation,
    RankedOptionAnnotation,
)
from app.degree_path.models import DegreePathResult
from app.planner.models import SemesterPlannerResult
from app.student_intelligence.models import StudentIntelligenceBundle


def _annotation(
    course_code: str,
    bundles: dict[str, StudentIntelligenceBundle],
) -> CourseIntelligenceAnnotation:
    bundle = bundles.get(course_code)
    if bundle is None:
        return CourseIntelligenceAnnotation(course_code=course_code)
    readiness = bundle.readiness
    return CourseIntelligenceAnnotation(
        course_code=course_code,
        readiness_state=(
            readiness.readiness_state.value
            if readiness is not None and readiness.readiness_state is not None
            else None
        ),
        readiness_reason_codes=(readiness.reason_codes if readiness is not None else ()),
        difficulty_reason_codes=bundle.difficulty.reason_codes,
        structural_risk_reason_codes=bundle.structural_risk.reason_codes,
        strength_reason_codes=bundle.strengths.reason_codes,
        performance_reason_codes=bundle.performance.reason_codes,
    )


def annotate_semester_plans(
    baseline: SemesterPlannerResult,
    intelligence_by_course: dict[str, StudentIntelligenceBundle] | None = None,
) -> AnnotatedResult:
    bundles = intelligence_by_course or {}
    annotations = tuple(
        RankedOptionAnnotation(
            rank=option.rank,
            course_annotations=tuple(
                _annotation(course.course_code, bundles) for course in option.courses
            ),
        )
        for option in baseline.plan_options
    )
    return AnnotatedResult(baseline_result=baseline, option_annotations=annotations)


def annotate_degree_paths(
    baseline: DegreePathResult,
    intelligence_by_course: dict[str, StudentIntelligenceBundle] | None = None,
) -> AnnotatedResult:
    bundles = intelligence_by_course or {}
    annotations: list[RankedOptionAnnotation] = []
    for path in baseline.paths:
        course_codes = tuple(
            course.course_code
            for semester in path.semesters
            for course in semester.plan_option.courses
        )
        annotations.append(
            RankedOptionAnnotation(
                rank=path.rank,
                course_annotations=tuple(_annotation(code, bundles) for code in course_codes),
            )
        )
    return AnnotatedResult(
        baseline_result=baseline,
        option_annotations=tuple(annotations),
    )
