"""Authority filtering and stable evidence helpers."""

from app.student.models import PerformanceProvenance, PerformanceVerificationState, StudentCourseAttemptRecord


def factual_attempts(attempts: tuple[StudentCourseAttemptRecord, ...]) -> tuple[StudentCourseAttemptRecord, ...]:
    allowed = {
        PerformanceProvenance.OFFICIAL_VERIFIED,
        PerformanceProvenance.STUDENT_RECORD,
        PerformanceProvenance.MANUAL_ACADEMIC_REVIEW,
    }
    return tuple(sorted((a for a in attempts if a.performance_provenance in allowed), key=_attempt_key))


def conclusion_attempts(attempts: tuple[StudentCourseAttemptRecord, ...]) -> tuple[StudentCourseAttemptRecord, ...]:
    allowed = {PerformanceProvenance.OFFICIAL_VERIFIED, PerformanceProvenance.MANUAL_ACADEMIC_REVIEW}
    return tuple(sorted((a for a in attempts if a.performance_provenance in allowed and a.performance_verification_state is PerformanceVerificationState.VERIFIED), key=_attempt_key))


def _attempt_key(attempt: StudentCourseAttemptRecord) -> tuple[str, int, str]:
    return (attempt.course_code, attempt.attempt_sequence or 2_147_483_647, attempt.attempt_id)
