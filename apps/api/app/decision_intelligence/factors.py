"""Closed factor registry and P3 readiness adapter for policy version 1.0."""

from __future__ import annotations

from app.decision_intelligence.models import (
    DecisionMode,
    EvidenceReference,
    FactorAction,
    FactorClassification,
    FactorEvaluation,
    FactorReason,
    ReadinessFactorInput,
)
from app.student_intelligence.models import (
    IntelligenceCapability,
    IntelligenceStatus,
    ReadinessState,
)

_P3_EXPLANATION_FACTORS = frozenset(
    {
        "PERF_OUTCOME_DISTRIBUTION",
        "PERF_REPEAT_HISTORY",
        "PERF_FAIL_PASS_RECOVERY",
        "PERF_REPEATED_FAILURE",
        "PERF_REQUIREMENT_COMPLETION",
        "PERF_DEPENDENCY_EXPOSURE",
        "STRENGTH_REQUIRED_COMPLETION",
        "STRENGTH_RECOVERY_EVIDENCE",
        "DIFFICULTY_REPEATED_FAILURE",
        "DIFFICULTY_REPEATED_WITHDRAWAL",
        "DIFFICULTY_REQUIRED_BOTTLENECK",
        "READINESS_RULE_REVIEW_REQUIRED",
        "STRUCTURAL_RISK_REQUIRED_REPEAT_FAILURE",
        "STRUCTURAL_RISK_REQUIRED_BOTTLENECK",
        "STRUCTURAL_RISK_CONCENTRATED_DEPENDENCY",
    }
)
_P3_ORDERING_FACTORS = frozenset(
    {
        "READINESS_PREREQUISITES_COMPLETED",
        "READINESS_PREREQUISITE_DIFFICULTY",
        "READINESS_PREREQUISITE_IN_PROGRESS",
        "READINESS_NO_PREREQUISITES",
    }
)
_FORBIDDEN_FACTORS = frozenset(
    {
        "RAW_GRADES",
        "PREDICTIVE_ACADEMIC_RISK",
        "DOMAIN_STRENGTH_OR_WEAKNESS",
        "DEMOGRAPHIC_ATTRIBUTES",
        "AI_GENERATED_SCORE",
    }
)
_HARD_GATES = frozenset({"ELIGIBILITY", "REQUIREMENT_STATE"})
_BASELINE_ORDERING = frozenset(
    {
        "REQUIRED_COURSE_PRIORITY",
        "REQUIREMENT_GROUP_REMAINING_NEED",
        "EFFECTIVE_CREDIT_CONTRIBUTION",
        "GROUP_COMPLETION",
        "DIRECT_UNLOCK_IMPACT",
        "EXISTING_RECOMMENDATION_RANK",
        "TYPED_STUDENT_PREFERENCE",
    }
)


def classify_factor(factor_id: str) -> FactorClassification:
    """Return the locked classification; reject every unclassified factor."""
    if factor_id in _HARD_GATES:
        return FactorClassification.HARD_GATE
    if factor_id in _P3_ORDERING_FACTORS or factor_id in _BASELINE_ORDERING:
        return FactorClassification.ORDERING_FACTOR
    if factor_id in _P3_EXPLANATION_FACTORS:
        return FactorClassification.EXPLANATION_ONLY
    if factor_id in _FORBIDDEN_FACTORS:
        return FactorClassification.NOT_ALLOWED
    raise ValueError(f"Unclassified Decision Intelligence factor: {factor_id}")


def evaluate_readiness_factor(
    factor_input: ReadinessFactorInput | None,
    mode: DecisionMode,
) -> FactorEvaluation:
    """Adapt an existing P3 readiness result without recalculating readiness."""
    if mode is DecisionMode.STRUCTURAL_BASELINE:
        return _abstain(FactorReason.P4_ABSTAIN_BASELINE_MODE)
    if factor_input is None or factor_input.result is None:
        return _abstain(FactorReason.P4_ABSTAIN_MISSING_RESULT)
    if factor_input.course_code != factor_input.result_course_code:
        return _abstain(FactorReason.P4_ABSTAIN_IDENTITY_MISMATCH)
    if not factor_input.evidence_verified:
        return _abstain(FactorReason.P4_ABSTAIN_UNVERIFIED_EVIDENCE)
    if not factor_input.provenance_complete:
        return _abstain(FactorReason.P4_ABSTAIN_INCOMPLETE_PROVENANCE)

    result = factor_input.result
    if result.policy_version != "1.0":
        return _abstain(FactorReason.P4_ABSTAIN_POLICY_MISMATCH)
    if result.capability is not IntelligenceCapability.ACADEMIC_PREPARATION_READINESS:
        return _abstain(FactorReason.P4_ABSTAIN_UNSUPPORTED_STATE)
    if result.status is IntelligenceStatus.REVIEW_REQUIRED:
        return _abstain(FactorReason.P4_ABSTAIN_REVIEW_REQUIRED)
    if result.status is not IntelligenceStatus.AVAILABLE:
        return _abstain(FactorReason.P4_ABSTAIN_STATUS)
    if result.missing_inputs:
        return _abstain(FactorReason.P4_ABSTAIN_STATUS)

    evidence = tuple(
        EvidenceReference(
            source="P3_READINESS",
            identifier=item.identifier,
            course_codes=tuple(sorted(item.course_codes)),
        )
        for item in sorted(result.evidence, key=lambda value: value.identifier)
    )
    state = result.readiness_state
    if state is ReadinessState.PREPARATION_EVIDENCE_AVAILABLE:
        return _apply(state, 1, FactorReason.P4_READINESS_PREPARATION_TIE_BREAK, evidence)
    if state is ReadinessState.NOT_APPLICABLE:
        return _apply(state, 1, FactorReason.P4_READINESS_NOT_APPLICABLE_TIE_BREAK, evidence)
    if state is ReadinessState.CAUTION_EVIDENCE_AVAILABLE:
        return _apply(state, 0, FactorReason.P4_READINESS_CAUTION_TIE_BREAK, evidence)
    if state is ReadinessState.REVIEW_REQUIRED:
        return _abstain(FactorReason.P4_ABSTAIN_REVIEW_REQUIRED)
    return _abstain(FactorReason.P4_ABSTAIN_STATUS)


def _apply(
    state: ReadinessState,
    ordering_value: int,
    reason: FactorReason,
    evidence: tuple[EvidenceReference, ...],
) -> FactorEvaluation:
    return FactorEvaluation(
        factor_id="ACADEMIC_PREPARATION_READINESS",
        classification=FactorClassification.ORDERING_FACTOR,
        action=FactorAction.APPLY,
        categorical_value=state.value,
        ordering_value=ordering_value,
        reason=reason,
        evidence_references=evidence,
    )


def _abstain(reason: FactorReason) -> FactorEvaluation:
    return FactorEvaluation(
        factor_id="ACADEMIC_PREPARATION_READINESS",
        classification=FactorClassification.ORDERING_FACTOR,
        action=FactorAction.ABSTAIN,
        categorical_value=None,
        ordering_value=None,
        reason=reason,
    )
