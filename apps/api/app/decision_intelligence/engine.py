"""Read-only orchestration over already-loaded deterministic domain inputs."""

from __future__ import annotations

from app.decision_intelligence.annotations import (
    annotate_degree_paths,
    annotate_semester_plans,
)
from app.decision_intelligence.delay import analyze_delay, compare_degree_path_results
from app.decision_intelligence.models import (
    AnnotatedResult,
    DecisionMode,
    DegreePathComparison,
    DegreePathRunContext,
    DelayConsequenceInput,
    DelayConsequenceResult,
    EnhancedRecommendationResult,
    ReadinessFactorInput,
    SimulationProvenance,
)
from app.decision_intelligence.recommendation import integrate_recommendations
from app.degree_path.engine import plan_degree_paths
from app.planner.models import SemesterPlannerResult
from app.recommendations.engine import recommend_courses
from app.student_intelligence.models import StudentIntelligenceBundle


def recommend_with_decision_intelligence(
    progress_catalog,
    eligibility_catalog,
    student_attempts,
    *,
    mode: DecisionMode,
    readiness_by_course: dict[str, ReadinessFactorInput] | None,
    simulation_provenance: SimulationProvenance,
) -> EnhancedRecommendationResult:
    """Invoke Phase 7 once, then compose the optional readiness factor."""
    baseline = recommend_courses(
        progress_catalog,
        eligibility_catalog,
        student_attempts,
    )
    return integrate_recommendations(
        baseline,
        mode=mode,
        readiness_by_course=readiness_by_course,
        simulation_provenance=simulation_provenance,
    )


def annotate_existing_semester_result(
    baseline: SemesterPlannerResult,
    intelligence_by_course: dict[str, StudentIntelligenceBundle] | None = None,
) -> AnnotatedResult:
    return annotate_semester_plans(baseline, intelligence_by_course)


def annotate_existing_degree_path_result(
    baseline,
    intelligence_by_course: dict[str, StudentIntelligenceBundle] | None = None,
) -> AnnotatedResult:
    return annotate_degree_paths(baseline, intelligence_by_course)


def run_degree_path_comparison(
    baseline_context: DegreePathRunContext,
    delayed_context: DegreePathRunContext,
) -> DegreePathComparison:
    """Run unchanged Phase 9 once per explicit immutable snapshot and compare."""
    baseline = plan_degree_paths(
        baseline_context.progress_catalog,
        baseline_context.eligibility_catalog,
        baseline_context.attempts,
        baseline_context.constraints,
    )
    delayed = plan_degree_paths(
        delayed_context.progress_catalog,
        delayed_context.eligibility_catalog,
        delayed_context.attempts,
        delayed_context.constraints,
    )
    comparison = compare_degree_path_results(baseline, delayed)
    if comparison is None:  # pragma: no cover - both calls always return a result
        raise RuntimeError("Phase 9 comparison unexpectedly unavailable")
    return comparison


def evaluate_delay_consequence(data: DelayConsequenceInput) -> DelayConsequenceResult:
    return analyze_delay(data)
