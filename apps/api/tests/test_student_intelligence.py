"""P3.2 rule-catalog, safety, and determinism tests."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.progress.models import AcademicProgress, CourseProgress, CourseProgressState
from app.rules.models import (
    AttemptOutcome, CanTakeDecision, CanTakeError, Decision, DecisionReason,
    DependencyGroupEvidence, DependencyType, PrerequisiteLogicStatus, RequestErrorCode,
    TargetAttemptState,
)
from app.student.models import PerformanceProvenance, PerformanceVerificationState, StudentCourseAttemptRecord
from app.student_intelligence.engine import evaluate_student_intelligence
from app.student_intelligence.models import (
    DependencyExposure, IntelligenceStatus, MissingInput, ReadinessContext, ReadinessState,
    StudentIntelligenceContext,
)
from app.student_intelligence.readiness import evaluate_readiness

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def attempt(code, outcome, sequence=1, *, provenance=PerformanceProvenance.OFFICIAL_VERIFIED, grade=None):
    return StudentCourseAttemptRecord(
        f"{code}-{sequence}-{outcome.value}", "profile", code, outcome, sequence, None, None,
        None, "transcript_import", NOW, NOW, raw_numeric_grade=grade,
        performance_provenance=provenance,
        performance_verification_state=(PerformanceVerificationState.VERIFIED if provenance in {PerformanceProvenance.OFFICIAL_VERIFIED, PerformanceProvenance.MANUAL_ACADEMIC_REVIEW} else PerformanceVerificationState.UNVERIFIED),
    )


def progress(*courses):
    return AcademicProgress("plan", Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),0,0,False,(),tuple(courses),None,None,None)


def course(code, state, credits="3"):
    return CourseProgress(code, Decimal(credits), "g", "G", state)


def decision(kind=Decision.ELIGIBLE, *, status=PrerequisiteLogicStatus.VERIFIED, no_prereq=False):
    group=DependencyGroupEvidence(1,DependencyType.PREREQUISITE,("P",),("P",),())
    reason=DecisionReason.NO_PREREQUISITES if no_prereq else DecisionReason.PREREQUISITES_SATISFIED
    return CanTakeDecision("decision",kind,"plan","T",status,TargetAttemptState(False,False),(group,) if not no_prereq else (),(),(reason,),(),None,None)


def context(attempts=(), *, prog=None, required=frozenset(), exposures=()):
    return StudentIntelligenceContext(tuple(attempts),prog,required,tuple(exposures))


def rule_ids(result):
    return {item.rule_id for item in (*result.observations,*result.signals)}


def test_all_global_catalog_rules_emit_exact_codes_and_evidence():
    attempts=(attempt("A",AttemptOutcome.FAILED,1),attempt("A",AttemptOutcome.PASSED,2),attempt("B",AttemptOutcome.FAILED,1),attempt("B",AttemptOutcome.FAILED,2),attempt("W",AttemptOutcome.WITHDRAWN,1),attempt("W",AttemptOutcome.WITHDRAWN,2))
    exposures=(DependencyExposure("T1",("P",)),DependencyExposure("T2",("P",)))
    bundle=evaluate_student_intelligence(context(attempts,prog=progress(course("A",CourseProgressState.COMPLETED),course("Z0",CourseProgressState.COMPLETED,"0")),required=frozenset({"A","B","W","Z0","T1","T2"}),exposures=exposures))
    assert rule_ids(bundle.performance)=={f"PERF-00{i}" for i in range(1,7)}
    assert rule_ids(bundle.strengths)=={"STRENGTH-001","STRENGTH-002"}
    assert rule_ids(bundle.difficulty)=={"DIFFICULTY-001","DIFFICULTY-002","DIFFICULTY-003"}
    assert rule_ids(bundle.structural_risk)=={"STRUCTURAL_RISK-001","STRUCTURAL_RISK-002","STRUCTURAL_RISK-003"}
    assert all(result.policy_version=="1.0" for result in (bundle.performance,bundle.strengths,bundle.difficulty,bundle.structural_risk,bundle.predictive_risk))
    assert bundle.predictive_risk.status is IntelligenceStatus.BLOCKED_BY_EXTERNAL_DATA
    assert bundle.predictive_risk.missing_inputs==(MissingInput.NO_COHORT_DATA,)


@pytest.mark.parametrize("history,expected",[
    ((AttemptOutcome.FAILED,AttemptOutcome.PASSED),{"PERF-003","STRENGTH-002"}),
    ((AttemptOutcome.FAILED,AttemptOutcome.FAILED),{"PERF-004","DIFFICULTY-001"}),
    ((AttemptOutcome.WITHDRAWN,AttemptOutcome.PASSED),set()),
    ((AttemptOutcome.FAILED,AttemptOutcome.IN_PROGRESS),set()),
    ((AttemptOutcome.FAILED,AttemptOutcome.FAILED,AttemptOutcome.PASSED),{"PERF-003","PERF-004","STRENGTH-002","DIFFICULTY-001"}),
    ((AttemptOutcome.WITHDRAWN,AttemptOutcome.WITHDRAWN),{"DIFFICULTY-002"}),
])
def test_repeated_attempt_matrix_preserves_full_history(history,expected):
    rows=tuple(attempt("R",outcome,i+1) for i,outcome in enumerate(history))
    bundle=evaluate_student_intelligence(context(rows,required=frozenset({"R"})))
    actual=rule_ids(bundle.performance)|rule_ids(bundle.strengths)|rule_ids(bundle.difficulty)
    assert expected <= actual


def test_grade_values_never_change_intelligence_or_outcome():
    base=attempt("A",AttemptOutcome.FAILED,1,grade=Decimal("85"))
    low=replace(base,raw_numeric_grade=Decimal("59"),raw_letter_grade="F",raw_grade_points=Decimal("0"))
    high=evaluate_student_intelligence(context((base,),required=frozenset({"A"})))
    low_result=evaluate_student_intelligence(context((low,),required=frozenset({"A"})))
    assert high==low_result
    assert base.outcome is low.outcome is AttemptOutcome.FAILED
    assert "strong" not in repr(high).lower() and "weak" not in repr(high).lower()


@pytest.mark.parametrize("provenance",[PerformanceProvenance.UNVERIFIED,PerformanceProvenance.MODEL_OUTPUT,PerformanceProvenance.DERIVED_DETERMINISTIC])
def test_disallowed_provenance_cannot_drive_conclusions(provenance):
    rows=(attempt("A",AttemptOutcome.FAILED,1,provenance=provenance),attempt("A",AttemptOutcome.FAILED,2,provenance=provenance))
    bundle=evaluate_student_intelligence(context(rows,required=frozenset({"A"})))
    assert not rule_ids(bundle.difficulty) and not rule_ids(bundle.structural_risk)


def test_student_record_is_factual_only_and_manual_review_may_conclude():
    student=(attempt("A",AttemptOutcome.FAILED,1,provenance=PerformanceProvenance.STUDENT_RECORD),attempt("A",AttemptOutcome.FAILED,2,provenance=PerformanceProvenance.STUDENT_RECORD))
    manual=(attempt("A",AttemptOutcome.FAILED,1,provenance=PerformanceProvenance.MANUAL_ACADEMIC_REVIEW),attempt("A",AttemptOutcome.FAILED,2,provenance=PerformanceProvenance.MANUAL_ACADEMIC_REVIEW))
    assert "PERF-004" in rule_ids(evaluate_student_intelligence(context(student)).performance)
    assert not rule_ids(evaluate_student_intelligence(context(student,required=frozenset({"A"}))).difficulty)
    assert "DIFFICULTY-001" in rule_ids(evaluate_student_intelligence(context(manual,required=frozenset({"A"}))).difficulty)


def test_deterministic_ordering_is_independent_of_input_order():
    rows=(attempt("B",AttemptOutcome.FAILED,2),attempt("A",AttemptOutcome.PASSED,2),attempt("A",AttemptOutcome.FAILED,1),attempt("B",AttemptOutcome.FAILED,1))
    a=evaluate_student_intelligence(context(rows,required=frozenset({"A","B"})))
    b=evaluate_student_intelligence(context(tuple(reversed(rows)),required=frozenset({"A","B"})))
    assert a==b


def test_zero_credit_required_counts_but_referenced_only_does_not():
    prog=progress(course("ZERO",CourseProgressState.COMPLETED,"0"),course("REF",CourseProgressState.COMPLETED,"3"))
    result=evaluate_student_intelligence(context(prog=prog,required=frozenset({"ZERO"}))).strengths
    assert result.signals[0].course_codes==("ZERO",)


def test_review_exposure_is_conservative():
    bundle=evaluate_student_intelligence(context(exposures=(DependencyExposure("T",("P",),review_required=True),)))
    assert bundle.difficulty.status is IntelligenceStatus.REVIEW_REQUIRED
    assert bundle.structural_risk.status is IntelligenceStatus.REVIEW_REQUIRED
    assert not bundle.difficulty.signals and not bundle.structural_risk.signals


@pytest.mark.parametrize("eligibility,rows,state,status,rule",[
    (decision(),(attempt("P",AttemptOutcome.PASSED),),ReadinessState.PREPARATION_EVIDENCE_AVAILABLE,IntelligenceStatus.AVAILABLE,"READINESS-001"),
    (decision(),(attempt("P",AttemptOutcome.PASSED),attempt("P",AttemptOutcome.FAILED,2)),ReadinessState.CAUTION_EVIDENCE_AVAILABLE,IntelligenceStatus.AVAILABLE,"READINESS-002"),
    (decision(),(attempt("P",AttemptOutcome.IN_PROGRESS),),ReadinessState.CAUTION_EVIDENCE_AVAILABLE,IntelligenceStatus.AVAILABLE,"READINESS-003"),
    (decision(no_prereq=True),(),ReadinessState.NOT_APPLICABLE,IntelligenceStatus.AVAILABLE,"READINESS-004"),
    (decision(Decision.REVIEW_REQUIRED,status=PrerequisiteLogicStatus.UNRESOLVED),(),ReadinessState.REVIEW_REQUIRED,IntelligenceStatus.REVIEW_REQUIRED,"READINESS-005"),
])
def test_five_readiness_rules(eligibility,rows,state,status,rule):
    result=evaluate_readiness(ReadinessContext(eligibility,rows))
    assert result.readiness_state is state and result.status is status and rule in rule_ids(result)


def test_readiness_matrix_not_eligible_referenced_only_and_insufficient():
    not_eligible=evaluate_readiness(ReadinessContext(decision(Decision.NOT_ELIGIBLE),()))
    referenced=evaluate_readiness(ReadinessContext(CanTakeError("error",RequestErrorCode.TARGET_NOT_IN_STUDY_PLAN,"plan","REF"),()))
    insufficient=evaluate_readiness(ReadinessContext(decision(),(attempt("P",AttemptOutcome.PASSED,provenance=PerformanceProvenance.UNVERIFIED),)))
    assert not_eligible.readiness_state is referenced.readiness_state is ReadinessState.NOT_APPLICABLE
    assert insufficient.readiness_state is ReadinessState.INSUFFICIENT_DATA


def test_source_conflict_readiness_propagates_exact_missing_input():
    result=evaluate_readiness(ReadinessContext(decision(Decision.REVIEW_REQUIRED,status=PrerequisiteLogicStatus.SOURCE_CONFLICT),()))
    assert result.missing_inputs==(MissingInput.SOURCE_CONFLICT,)


def test_empty_and_partial_data_never_fabricates_conclusions():
    empty=evaluate_student_intelligence(context())
    in_progress=evaluate_student_intelligence(context((attempt("A",AttemptOutcome.IN_PROGRESS),)))
    assert empty.performance.status is IntelligenceStatus.INSUFFICIENT_DATA
    assert not empty.strengths.signals and not empty.difficulty.signals and not empty.structural_risk.signals
    assert not in_progress.strengths.signals and not in_progress.difficulty.signals
    assert not hasattr(empty,"score") and not hasattr(empty.predictive_risk,"probability")
