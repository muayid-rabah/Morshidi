from app.progress.models import CourseProgressState
from app.student_intelligence.evidence import conclusion_attempts
from app.student_intelligence.models import *
from app.student_intelligence.observations import _by_course, _fail_then_pass


def evaluate_strengths(context: StudentIntelligenceContext) -> IntelligenceResult:
    signals=[]; evidence=[]
    if context.progress:
        completed=tuple(sorted(c.course_code for c in context.progress.courses if c.course_code in context.required_course_codes and c.state is CourseProgressState.COMPLETED))
        if completed:
            signals.append(IntelligenceObservation("STRENGTH-001", "REQUIRED_COMPLETION", len(completed), completed)); evidence.append(IntelligenceEvidence("STRENGTH-001", EvidenceType.REQUIREMENT_PROGRESS, completed))
    recovered=tuple(sorted(code for code, rows in _by_course(conclusion_attempts(context.attempts)).items() if _fail_then_pass(rows)))
    if recovered:
        signals.append(IntelligenceObservation("STRENGTH-002", "RECOVERY_EVIDENCE", len(recovered), recovered)); evidence.append(IntelligenceEvidence("STRENGTH-002", EvidenceType.COURSE_ATTEMPT, recovered))
    return _result(IntelligenceCapability.ACADEMIC_STRENGTH, signals, evidence, "Strength evidence is not a trait or domain classification.")


def _result(capability, signals, evidence, limitation):
    reason_map={"STRENGTH-001":"STRENGTH_REQUIRED_COMPLETION","STRENGTH-002":"STRENGTH_RECOVERY_EVIDENCE"}
    return IntelligenceResult(POLICY_VERSION, capability, IntelligenceStatus.AVAILABLE if signals else IntelligenceStatus.INSUFFICIENT_DATA, signals=tuple(signals), reason_codes=tuple(reason_map[s.rule_id] for s in signals), evidence=tuple(evidence), missing_inputs=() if signals else (MissingInput.NO_VERIFIED_PERFORMANCE_DATA,), limitations=(limitation,))
