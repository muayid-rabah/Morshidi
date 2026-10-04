from collections import Counter, defaultdict
from app.rules.models import AttemptOutcome
from app.student_intelligence.evidence import conclusion_attempts
from app.student_intelligence.models import *


def evaluate_difficulty(context: StudentIntelligenceContext) -> IntelligenceResult:
    by=defaultdict(list)
    for a in conclusion_attempts(context.attempts): by[a.course_code].append(a)
    signals=[]; evidence=[]
    failed=tuple(sorted(c for c,r in by.items() if sum(a.outcome is AttemptOutcome.FAILED for a in r)>=2))
    withdrawn=tuple(sorted(c for c,r in by.items() if c in context.required_course_codes and sum(a.outcome is AttemptOutcome.WITHDRAWN for a in r)>=2))
    bottlenecks=tuple(sorted(e.target_course_code for e in context.dependency_exposures if e.required_target and e.blocking_course_codes and not e.review_required))
    for rule,value,codes,etype in (("DIFFICULTY-001","REPEATED_FAILURE",failed,EvidenceType.ATTEMPT_OUTCOME),("DIFFICULTY-002","REPEATED_WITHDRAWAL",withdrawn,EvidenceType.COURSE_ATTEMPT),("DIFFICULTY-003","REQUIRED_BOTTLENECK",bottlenecks,EvidenceType.ELIGIBILITY_RESULT)):
        if codes: signals.append(IntelligenceObservation(rule,value,len(codes),codes)); evidence.append(IntelligenceEvidence(rule,etype,codes))
    review=any(e.review_required for e in context.dependency_exposures)
    status=IntelligenceStatus.REVIEW_REQUIRED if review and not signals else (IntelligenceStatus.AVAILABLE if signals else IntelligenceStatus.INSUFFICIENT_DATA)
    reason_map={"DIFFICULTY-001":"DIFFICULTY_REPEATED_FAILURE","DIFFICULTY-002":"DIFFICULTY_REPEATED_WITHDRAWAL","DIFFICULTY-003":"DIFFICULTY_REQUIRED_BOTTLENECK"}
    return IntelligenceResult(POLICY_VERSION, IntelligenceCapability.ACADEMIC_DIFFICULTY_SIGNAL,status,signals=tuple(signals),reason_codes=tuple(reason_map[s.rule_id] for s in signals),evidence=tuple(evidence),missing_inputs=(MissingInput.UNRESOLVED_PREREQUISITE,) if review else (() if signals else (MissingInput.NO_VERIFIED_PERFORMANCE_DATA,)),limitations=("Signals do not infer cause, effort, ability, or intelligence.",))
