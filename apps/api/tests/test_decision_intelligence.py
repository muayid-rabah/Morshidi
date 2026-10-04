"""P4.2 factor isolation, baseline preservation, traces, and annotations."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.decision_intelligence.annotations import (
    annotate_degree_paths,
    annotate_semester_plans,
)
from app.decision_intelligence.factors import classify_factor, evaluate_readiness_factor
from app.decision_intelligence.models import (
    DecisionMode,
    FactorAction,
    FactorClassification,
    FactorReason,
    ReadinessFactorInput,
    SimulationProvenance,
    SimulationStateKind,
)
from app.decision_intelligence.recommendation import integrate_recommendations
from app.degree_path.models import DegreePathConstraints, DegreePathResult
from app.planner.models import PlannerConstraints, SemesterPlannerResult
from app.recommendations.models import RecommendationCandidate, RecommendationResult
from app.student_intelligence.models import (
    IntelligenceCapability,
    IntelligenceResult,
    IntelligenceStatus,
    MissingInput,
    ReadinessState,
)


def _candidate(code: str, values: tuple[int, int, str, int, int, int], rank: int):
    p1, p2, p3, p4, p5, display = values
    return RecommendationCandidate(
        course_code=code,
        course_name_ar=None,
        credit_hours=Decimal("3"),
        requirement_group_code="SYNTHETIC_REQUIRED",
        requirement_type="required",
        course_state="NOT_ATTEMPTED",
        eligibility_decision="ELIGIBLE",
        effective_credit_contribution=Decimal(p3),
        group_remaining_credits_before=Decimal("6"),
        group_remaining_credits_after=Decimal("3"),
        completes_requirement_group=bool(p4),
        newly_eligible_count=p5,
        newly_eligible_course_codes=(),
        priority_tuple=(p1, p2, Decimal(p3), p4, p5, -display, code),
        rank=rank,
        reason_codes=(),
        previously_attempted=False,
    )


def _baseline(*candidates):
    return RecommendationResult(
        study_plan_id="synthetic-plan",
        recommendation_policy_version="1.0",
        ranked_recommendations=tuple(candidates),
        review_required_courses=(),
        excluded_in_progress=(),
        methodology_note="synthetic",
        limitations=(),
    )


def _readiness(state: ReadinessState, status: IntelligenceStatus = IntelligenceStatus.AVAILABLE):
    return IntelligenceResult(
        policy_version="1.0",
        capability=IntelligenceCapability.ACADEMIC_PREPARATION_READINESS,
        status=status,
        readiness_state=state,
    )


def _factor(code: str, state: ReadinessState, **kwargs):
    return ReadinessFactorInput(code, code, _readiness(state), **kwargs)


PROVENANCE = SimulationProvenance(
    SimulationStateKind.AUTHORITATIVE,
    "synthetic-state-v1",
)


def _order(result):
    return tuple(item.candidate.course_code for item in result.ranked_candidates)


def test_structural_baseline_is_exact_and_records_abstention():
    a = _candidate("A", (2, 1, "3", 0, 0, 1), 1)
    b = _candidate("B", (2, 1, "3", 0, 0, 2), 2)
    baseline = _baseline(a, b)
    result = integrate_recommendations(
        baseline,
        mode=DecisionMode.STRUCTURAL_BASELINE,
        readiness_by_course={"A": _factor("A", ReadinessState.CAUTION_EVIDENCE_AVAILABLE)},
        simulation_provenance=PROVENANCE,
    )
    assert result.baseline_result is baseline
    assert _order(result) == ("A", "B")
    assert all(item.reason is FactorReason.P4_ABSTAIN_BASELINE_MODE for item in result.trace.ignored_factors)
    assert not result.trace.changed_relative_orders


@pytest.mark.parametrize(
    "a_values,b_values",
    [
        ((2, 1, "3", 0, 0, 1), (1, 1, "3", 0, 0, 2)),
        ((2, 1, "3", 0, 0, 1), (2, 0, "3", 0, 0, 2)),
        ((2, 1, "3", 1, 0, 1), (2, 1, "3", 0, 9, 2)),
    ],
)
def test_readiness_cannot_cross_any_baseline_semantic_dimension(a_values, b_values):
    baseline = _baseline(_candidate("A", a_values, 1), _candidate("B", b_values, 2))
    result = integrate_recommendations(
        baseline,
        mode=DecisionMode.READINESS_AWARE,
        readiness_by_course={
            "A": _factor("A", ReadinessState.CAUTION_EVIDENCE_AVAILABLE),
            "B": _factor("B", ReadinessState.PREPARATION_EVIDENCE_AVAILABLE),
        },
        simulation_provenance=PROVENANCE,
    )
    assert _order(result) == ("A", "B")


def test_readiness_reorders_only_an_exact_p1_to_p5_tie():
    baseline = _baseline(
        _candidate("A", (2, 1, "3", 0, 0, 1), 1),
        _candidate("B", (2, 1, "3", 0, 0, 2), 2),
    )
    result = integrate_recommendations(
        baseline,
        mode=DecisionMode.READINESS_AWARE,
        readiness_by_course={
            "A": _factor("A", ReadinessState.CAUTION_EVIDENCE_AVAILABLE),
            "B": _factor("B", ReadinessState.PREPARATION_EVIDENCE_AVAILABLE),
        },
        simulation_provenance=PROVENANCE,
    )
    assert _order(result) == ("B", "A")
    assert tuple(
        (c.candidate.course_code, c.baseline_rank, c.final_rank)
        for c in result.ranked_candidates
    ) == (
        ("B", 2, 1),
        ("A", 1, 2),
    )
    assert len(result.trace.changed_relative_orders) == 2
    assert result.baseline_result.ranked_recommendations == baseline.ranked_recommendations


@pytest.mark.parametrize(
    "factor_input,reason",
    [
        (None, FactorReason.P4_ABSTAIN_MISSING_RESULT),
        (ReadinessFactorInput("A", "B", _readiness(ReadinessState.NOT_APPLICABLE)), FactorReason.P4_ABSTAIN_IDENTITY_MISMATCH),
        (_factor("A", ReadinessState.NOT_APPLICABLE, evidence_verified=False), FactorReason.P4_ABSTAIN_UNVERIFIED_EVIDENCE),
        (_factor("A", ReadinessState.NOT_APPLICABLE, provenance_complete=False), FactorReason.P4_ABSTAIN_INCOMPLETE_PROVENANCE),
        (ReadinessFactorInput("A", "A", _readiness(ReadinessState.REVIEW_REQUIRED, IntelligenceStatus.REVIEW_REQUIRED)), FactorReason.P4_ABSTAIN_REVIEW_REQUIRED),
        (ReadinessFactorInput("A", "A", _readiness(ReadinessState.INSUFFICIENT_DATA, IntelligenceStatus.INSUFFICIENT_DATA)), FactorReason.P4_ABSTAIN_STATUS),
    ],
)
def test_readiness_adapter_abstains_explicitly(factor_input, reason):
    result = evaluate_readiness_factor(factor_input, DecisionMode.READINESS_AWARE)
    assert result.action is FactorAction.ABSTAIN
    assert result.ordering_value is None
    assert result.reason is reason


def test_readiness_declaring_missing_input_abstains_even_when_status_is_available():
    inconsistent = replace(
        _readiness(ReadinessState.NOT_APPLICABLE),
        missing_inputs=(MissingInput.NO_TARGET_COURSE_CONTEXT,),
    )
    result = evaluate_readiness_factor(
        ReadinessFactorInput("A", "A", inconsistent),
        DecisionMode.READINESS_AWARE,
    )
    assert result.action is FactorAction.ABSTAIN
    assert result.reason is FactorReason.P4_ABSTAIN_STATUS


def test_any_abstention_preserves_the_whole_tie_group_baseline_order():
    baseline = _baseline(
        _candidate("A", (2, 1, "3", 0, 0, 1), 1),
        _candidate("B", (2, 1, "3", 0, 0, 2), 2),
    )
    result = integrate_recommendations(
        baseline,
        mode=DecisionMode.READINESS_AWARE,
        readiness_by_course={"B": _factor("B", ReadinessState.PREPARATION_EVIDENCE_AVAILABLE)},
        simulation_provenance=PROVENANCE,
    )
    assert _order(result) == ("A", "B")
    assert result.trace.ignored_factors[0].reason is FactorReason.P4_ABSTAIN_MISSING_RESULT


def test_membership_identity_reasons_and_priority_tuples_never_change():
    candidates = (
        _candidate("A", (2, 1, "3", 0, 0, 1), 1),
        _candidate("B", (2, 1, "3", 0, 0, 2), 2),
    )
    baseline = _baseline(*candidates)
    result = integrate_recommendations(
        baseline,
        mode=DecisionMode.READINESS_AWARE,
        readiness_by_course={
            "A": _factor("A", ReadinessState.CAUTION_EVIDENCE_AVAILABLE),
            "B": _factor("B", ReadinessState.NOT_APPLICABLE),
            "NOT_IN_BASELINE": _factor("NOT_IN_BASELINE", ReadinessState.PREPARATION_EVIDENCE_AVAILABLE),
        },
        simulation_provenance=PROVENANCE,
    )
    assert {item.candidate.course_code for item in result.ranked_candidates} == {"A", "B"}
    for view in result.ranked_candidates:
        original = next(item for item in candidates if item.course_code == view.candidate.course_code)
        assert view.candidate is original
        assert view.candidate.reason_codes == original.reason_codes
        assert view.candidate.priority_tuple == original.priority_tuple


def test_closed_factor_registry_accounts_for_all_p3_signals_and_forbids_unknowns():
    explanation = {
        "PERF_OUTCOME_DISTRIBUTION", "PERF_REPEAT_HISTORY", "PERF_FAIL_PASS_RECOVERY",
        "PERF_REPEATED_FAILURE", "PERF_REQUIREMENT_COMPLETION", "PERF_DEPENDENCY_EXPOSURE",
        "STRENGTH_REQUIRED_COMPLETION", "STRENGTH_RECOVERY_EVIDENCE",
        "DIFFICULTY_REPEATED_FAILURE", "DIFFICULTY_REPEATED_WITHDRAWAL",
        "DIFFICULTY_REQUIRED_BOTTLENECK", "READINESS_RULE_REVIEW_REQUIRED",
        "STRUCTURAL_RISK_REQUIRED_REPEAT_FAILURE", "STRUCTURAL_RISK_REQUIRED_BOTTLENECK",
        "STRUCTURAL_RISK_CONCENTRATED_DEPENDENCY",
    }
    ordering = {
        "READINESS_PREREQUISITES_COMPLETED", "READINESS_PREREQUISITE_DIFFICULTY",
        "READINESS_PREREQUISITE_IN_PROGRESS", "READINESS_NO_PREREQUISITES",
    }
    assert all(classify_factor(item) is FactorClassification.EXPLANATION_ONLY for item in explanation)
    assert all(classify_factor(item) is FactorClassification.ORDERING_FACTOR for item in ordering)
    assert classify_factor("RAW_GRADES") is FactorClassification.NOT_ALLOWED
    with pytest.raises(ValueError, match="Unclassified"):
        classify_factor("INVENTED_FACTOR")


def test_explanation_only_inputs_and_raw_grade_have_no_ranking_input_channel():
    baseline = _baseline(
        _candidate("A", (2, 1, "3", 0, 0, 1), 1),
        _candidate("B", (2, 1, "3", 0, 0, 2), 2),
    )
    first = integrate_recommendations(
        baseline,
        mode=DecisionMode.STRUCTURAL_BASELINE,
        readiness_by_course={},
        simulation_provenance=PROVENANCE,
    )
    second = integrate_recommendations(
        baseline,
        mode=DecisionMode.STRUCTURAL_BASELINE,
        readiness_by_course={},
        simulation_provenance=PROVENANCE,
    )
    assert first == second
    assert not hasattr(first, "raw_grade") and not hasattr(first, "difficulty_score")


def test_phase8_and_phase9_annotations_preserve_baseline_objects_exactly():
    semester = SemesterPlannerResult(
        "synthetic-plan", "1.0", "ACADEMIC_STRUCTURE_ONLY",
        PlannerConstraints(Decimal("12")), 15, 0, 0, 0, (), (), (), "synthetic", (),
    )
    degree = DegreePathResult(
        "synthetic-plan", "1.0", "MODELED_DEGREE_PATH_ONLY",
        DegreePathConstraints(Decimal("12")), (), Decimal("0"), Decimal("6"), 0, 1,
    )
    annotated_semester = annotate_semester_plans(semester, {})
    annotated_degree = annotate_degree_paths(degree, {})
    assert annotated_semester.baseline_result is semester
    assert annotated_degree.baseline_result is degree
    assert annotated_semester.option_annotations == ()
    assert annotated_degree.option_annotations == ()
