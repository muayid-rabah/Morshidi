"""PERF-001 through PERF-006."""

from collections import Counter, defaultdict

from app.progress.models import CourseProgressState
from app.rules.models import AttemptOutcome
from app.student_intelligence.evidence import factual_attempts
from app.student_intelligence.models import *


def evaluate_performance(context: StudentIntelligenceContext) -> IntelligenceResult:
    attempts = factual_attempts(context.attempts)
    observations: list[IntelligenceObservation] = []
    evidence: list[IntelligenceEvidence] = []
    if attempts:
        counts = Counter(a.outcome.value for a in attempts)
        for outcome in AttemptOutcome:
            observations.append(IntelligenceObservation("PERF-001", f"OUTCOME_{outcome.value}", counts[outcome.value]))
        evidence.append(IntelligenceEvidence("PERF-001", EvidenceType.ATTEMPT_OUTCOME, attempt_ids=tuple(a.attempt_id for a in attempts)))
        by_course = _by_course(attempts)
        repeated = tuple(sorted(code for code, rows in by_course.items() if len(rows) > 1))
        if repeated:
            observations.append(IntelligenceObservation("PERF-002", "REPEAT_HISTORY", len(repeated), repeated))
            evidence.append(IntelligenceEvidence("PERF-002", EvidenceType.COURSE_ATTEMPT, repeated))
        recovered = tuple(sorted(code for code, rows in by_course.items() if _fail_then_pass(rows)))
        if recovered:
            observations.append(IntelligenceObservation("PERF-003", "FAIL_PASS_RECOVERY", len(recovered), recovered))
            evidence.append(IntelligenceEvidence("PERF-003", EvidenceType.COURSE_ATTEMPT, recovered))
        repeated_failed = tuple(sorted(code for code, rows in by_course.items() if sum(a.outcome is AttemptOutcome.FAILED for a in rows) >= 2))
        if repeated_failed:
            observations.append(IntelligenceObservation("PERF-004", "REPEATED_FAILURE", len(repeated_failed), repeated_failed))
            evidence.append(IntelligenceEvidence("PERF-004", EvidenceType.ATTEMPT_OUTCOME, repeated_failed))
    if context.progress is not None:
        completed = tuple(sorted(c.course_code for c in context.progress.courses if c.state is CourseProgressState.COMPLETED))
        observations.append(IntelligenceObservation("PERF-005", "REQUIREMENT_COMPLETION", len(completed), completed))
        evidence.append(IntelligenceEvidence("PERF-005", EvidenceType.REQUIREMENT_PROGRESS, completed))
    blocked = tuple(sorted(e.target_course_code for e in context.dependency_exposures if e.required_target and e.blocking_course_codes and not e.review_required))
    if blocked:
        observations.append(IntelligenceObservation("PERF-006", "DEPENDENCY_EXPOSURE", len(blocked), blocked))
        evidence.append(IntelligenceEvidence("PERF-006", EvidenceType.ELIGIBILITY_RESULT, blocked))
    reason_map = {
        "PERF-001": "PERF_OUTCOME_DISTRIBUTION", "PERF-002": "PERF_REPEAT_HISTORY",
        "PERF-003": "PERF_FAIL_PASS_RECOVERY", "PERF-004": "PERF_REPEATED_FAILURE",
        "PERF-005": "PERF_REQUIREMENT_COMPLETION", "PERF-006": "PERF_DEPENDENCY_EXPOSURE",
    }
    reasons = tuple(dict.fromkeys(reason_map[o.rule_id] for o in observations))
    missing = () if observations else (MissingInput.NO_ATTEMPT_HISTORY,)
    return IntelligenceResult(POLICY_VERSION, IntelligenceCapability.PERFORMANCE_INTELLIGENCE, IntelligenceStatus.AVAILABLE if observations else IntelligenceStatus.INSUFFICIENT_DATA, tuple(observations), reason_codes=reasons, evidence=tuple(evidence), missing_inputs=missing, limitations=("Raw grades and academic-period trends are not interpreted.",))


def _by_course(attempts):
    result = defaultdict(list)
    for attempt in attempts: result[attempt.course_code].append(attempt)
    return result


def _fail_then_pass(attempts) -> bool:
    ordered = [a for a in attempts if a.attempt_sequence is not None]
    return any(a.outcome is AttemptOutcome.FAILED for a in ordered) and any(
        p.outcome is AttemptOutcome.PASSED and any(f.outcome is AttemptOutcome.FAILED and f.attempt_sequence < p.attempt_sequence for f in ordered)
        for p in ordered
    )
