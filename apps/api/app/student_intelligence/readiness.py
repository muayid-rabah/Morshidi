from app.rules.models import CanTakeDecision, Decision, DecisionReason, PrerequisiteLogicStatus, RequestErrorCode, AttemptOutcome
from app.student_intelligence.evidence import conclusion_attempts
from app.student_intelligence.models import *


def evaluate_readiness(context: ReadinessContext) -> IntelligenceResult:
    decision=context.eligibility
    if not isinstance(decision,CanTakeDecision):
        return _ready(ReadinessState.NOT_APPLICABLE,IntelligenceStatus.AVAILABLE,(),(),(MissingInput.NO_TARGET_COURSE_CONTEXT,))
    if decision.decision is Decision.REVIEW_REQUIRED:
        missing=MissingInput.SOURCE_CONFLICT if decision.prerequisite_logic_status is PrerequisiteLogicStatus.SOURCE_CONFLICT else MissingInput.UNRESOLVED_PREREQUISITE
        return _ready(ReadinessState.REVIEW_REQUIRED,IntelligenceStatus.REVIEW_REQUIRED,("READINESS-005",),(),(missing,))
    if decision.decision is Decision.NOT_ELIGIBLE:
        return _ready(ReadinessState.NOT_APPLICABLE,IntelligenceStatus.AVAILABLE,(),(),())
    if DecisionReason.NO_PREREQUISITES in decision.reasons:
        return _ready(ReadinessState.NOT_APPLICABLE,IntelligenceStatus.AVAILABLE,("READINESS-004",),(),())
    prereqs={c for g in (*decision.satisfied_dependency_groups,*decision.missing_dependency_groups) for c in g.option_course_codes}
    attempts=tuple(a for a in conclusion_attempts(context.attempts) if a.course_code in prereqs)
    caution_failure=any(a.outcome is AttemptOutcome.FAILED for a in attempts)
    caution_progress=any(a.outcome is AttemptOutcome.IN_PROGRESS for a in attempts)
    rules=[]
    if caution_failure: rules.append("READINESS-002")
    if caution_progress: rules.append("READINESS-003")
    if rules: return _ready(ReadinessState.CAUTION_EVIDENCE_AVAILABLE,IntelligenceStatus.AVAILABLE,tuple(rules),tuple(sorted(prereqs)),())
    if attempts and decision.decision is Decision.ELIGIBLE: return _ready(ReadinessState.PREPARATION_EVIDENCE_AVAILABLE,IntelligenceStatus.AVAILABLE,("READINESS-001",),tuple(sorted(prereqs)),())
    return _ready(ReadinessState.INSUFFICIENT_DATA,IntelligenceStatus.INSUFFICIENT_DATA,(),(),(MissingInput.NO_VERIFIED_PERFORMANCE_DATA,))


def _ready(state,status,rules,codes,missing):
    reason_map={"READINESS-001":"READINESS_PREREQUISITES_COMPLETED","READINESS-002":"READINESS_PREREQUISITE_DIFFICULTY","READINESS-003":"READINESS_PREREQUISITE_IN_PROGRESS","READINESS-004":"READINESS_NO_PREREQUISITES","READINESS-005":"READINESS_RULE_REVIEW_REQUIRED"}
    signals=tuple(IntelligenceObservation(r,state.value,course_codes=codes) for r in rules)
    return IntelligenceResult(POLICY_VERSION,IntelligenceCapability.ACADEMIC_PREPARATION_READINESS,status,signals=signals,reason_codes=tuple(reason_map[r] for r in rules),evidence=tuple(IntelligenceEvidence(r,EvidenceType.ELIGIBILITY_RESULT,codes) for r in rules),missing_inputs=missing,limitations=("Readiness never changes Phase 5 eligibility and is not a success probability.",),readiness_state=state)
