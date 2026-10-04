"""Baseline-preserving Phase 7 Decision Intelligence composition."""

from __future__ import annotations

from collections import defaultdict

from app.decision_intelligence.factors import evaluate_readiness_factor
from app.decision_intelligence.models import (
    DECISION_INTELLIGENCE_INTEGRATION_POLICY_VERSION,
    DecisionCandidateView,
    DecisionIntelligenceTrace,
    DecisionMode,
    EnhancedRecommendationResult,
    FactorAction,
    ReadinessFactorInput,
    SimulationProvenance,
)
from app.decision_intelligence.trace import relative_order_changes
from app.recommendations.models import RecommendationCandidate, RecommendationResult
from app.student_intelligence.models import POLICY_VERSION as INTELLIGENCE_POLICY_VERSION

_LIMITATIONS = (
    "Readiness is target-specific preparation evidence, not permission or success probability.",
    "Readiness may only break exact ties across Phase 7 baseline semantic dimensions P1-P5.",
    "Phase 8 and Phase 9 do not consume readiness-aware ordering in policy 1.0.",
)


def integrate_recommendations(
    baseline: RecommendationResult,
    *,
    mode: DecisionMode = DecisionMode.STRUCTURAL_BASELINE,
    readiness_by_course: dict[str, ReadinessFactorInput] | None = None,
    simulation_provenance: SimulationProvenance,
) -> EnhancedRecommendationResult:
    """Compose P3 readiness over an unchanged Phase 7 result.

    If any candidate in one P1-P5 tie group abstains, the entire group retains
    its baseline P6/P7 order. This implements the policy rule that an absent
    factor falls back to baseline rather than being converted to a score.
    """
    readiness_by_course = readiness_by_course or {}
    baseline_candidates = baseline.ranked_recommendations
    evaluations = {
        candidate.course_code: evaluate_readiness_factor(
            readiness_by_course.get(candidate.course_code), mode
        )
        for candidate in baseline_candidates
    }

    groups: dict[tuple[object, ...], list[RecommendationCandidate]] = defaultdict(list)
    group_order: list[tuple[object, ...]] = []
    for candidate in baseline_candidates:
        semantic_key = candidate.priority_tuple[:5]
        if semantic_key not in groups:
            group_order.append(semantic_key)
        groups[semantic_key].append(candidate)

    ordered: list[RecommendationCandidate] = []
    for semantic_key in group_order:
        candidates = groups[semantic_key]
        factor_values = [evaluations[item.course_code] for item in candidates]
        if mode is DecisionMode.READINESS_AWARE and all(
            item.action is FactorAction.APPLY for item in factor_values
        ):
            candidates = sorted(
                candidates,
                key=lambda item: (
                    -int(evaluations[item.course_code].ordering_value or 0),
                    item.rank,
                ),
            )
        ordered.extend(candidates)

    baseline_order = tuple(item.course_code for item in baseline_candidates)
    final_order = tuple(item.course_code for item in ordered)
    final_rank = {code: index + 1 for index, code in enumerate(final_order)}

    views = tuple(
        DecisionCandidateView(
            candidate=candidate,
            baseline_rank=candidate.rank,
            final_rank=final_rank[candidate.course_code],
            readiness_factor=evaluations[candidate.course_code],
        )
        for candidate in ordered
    )
    all_factors = tuple(evaluations[item.course_code] for item in baseline_candidates)
    trace = DecisionIntelligenceTrace(
        decision_type="COURSE_RECOMMENDATION",
        decision_mode=mode,
        base_policy_name="PHASE_7_RECOMMENDATION",
        base_policy_version=baseline.recommendation_policy_version,
        integration_policy_version=DECISION_INTELLIGENCE_INTEGRATION_POLICY_VERSION,
        intelligence_policy_version=INTELLIGENCE_POLICY_VERSION,
        baseline_order=baseline_order,
        applied_factors=tuple(
            item for item in all_factors if item.action is FactorAction.APPLY
        ),
        ignored_factors=tuple(
            item for item in all_factors if item.action is FactorAction.ABSTAIN
        ),
        changed_relative_orders=relative_order_changes(baseline_order, final_order),
        final_order=final_order,
        limitations=_LIMITATIONS,
        simulation_provenance=simulation_provenance,
    )
    return EnhancedRecommendationResult(
        baseline_result=baseline,
        decision_mode=mode,
        ranked_candidates=views,
        trace=trace,
    )
