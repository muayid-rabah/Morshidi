from collections import Counter, defaultdict
from app.rules.models import AttemptOutcome
from app.student_intelligence.evidence import conclusion_attempts
from app.student_intelligence.models import *


def evaluate_structural_risk(context: StudentIntelligenceContext) -> IntelligenceResult:
    by=defaultdict(list)
    for a in conclusion_attempts(context.attempts): by[a.course_code].append(a)
    failures=tuple(sorted(c for c,r in by.items() if c in context.required_course_codes and sum(a.outcome is AttemptOutcome.FAILED for a in r)>=2))
    bottlenecks=tuple(sorted(e.target_course_code for e in context.dependency_exposures if e.required_target and e.blocking_course_codes and not e.review_required))
    blockers=Counter(c for e in context.dependency_exposures if e.required_target and not e.review_required for c in e.blocking_course_codes)
    concentrated=tuple(sorted(c for c,n in blockers.items() if n>=2))
    values=(("STRUCTURAL_RISK-001","REQUIRED_REPEAT_FAILURE",failures,EvidenceType.COURSE_ATTEMPT),("STRUCTURAL_RISK-002","REQUIRED_BOTTLENECK",bottlenecks,EvidenceType.ELIGIBILITY_RESULT),("STRUCTURAL_RISK-003","CONCENTRATED_DEPENDENCY",concentrated,EvidenceType.COURSE_DEPENDENCY))
    signals=tuple(IntelligenceObservation(r,v,len(c),c) for r,v,c,_ in values if c)
    evidence=tuple(IntelligenceEvidence(r,e,c) for r,_,c,e in values if c)
    review=any(e.review_required for e in context.dependency_exposures)
    status=IntelligenceStatus.REVIEW_REQUIRED if review and not signals else (IntelligenceStatus.AVAILABLE if signals else IntelligenceStatus.INSUFFICIENT_DATA)
    reason_map={"STRUCTURAL_RISK-001":"STRUCTURAL_RISK_REQUIRED_REPEAT_FAILURE","STRUCTURAL_RISK-002":"STRUCTURAL_RISK_REQUIRED_BOTTLENECK","STRUCTURAL_RISK-003":"STRUCTURAL_RISK_CONCENTRATED_DEPENDENCY"}
    return IntelligenceResult(POLICY_VERSION,IntelligenceCapability.STRUCTURAL_RISK_SIGNAL,status,signals=signals,reason_codes=tuple(reason_map[s.rule_id] for s in signals),evidence=evidence,missing_inputs=(MissingInput.UNRESOLVED_PREREQUISITE,) if review else (() if signals else (MissingInput.NO_VERIFIED_PERFORMANCE_DATA,)),limitations=("Structural signals are not predictions and contain no probability or score.",))


def predictive_risk_boundary() -> IntelligenceResult:
    return IntelligenceResult(POLICY_VERSION,IntelligenceCapability.PREDICTIVE_ACADEMIC_RISK,IntelligenceStatus.BLOCKED_BY_EXTERNAL_DATA,missing_inputs=(MissingInput.NO_COHORT_DATA,),limitations=("No predictive model, score, probability, or risk band exists.",))
