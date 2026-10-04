"""Student persistence mapping feeds the unchanged Phase 5 evaluator."""

from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    AttemptOutcome, CanTakeCatalog, CanTakeRequest, CourseCatalogStatus,
    CourseIdentity, Decision, PlanCourseRule, PrerequisiteLogicStatus,
    StudentCourseAttempt,
)
from app.student.models import StudentAcademicState

PLAN = "11111111-1111-1111-1111-111111111111"


def state(*attempts: StudentCourseAttempt) -> StudentAcademicState:
    return StudentAcademicState("profile", "owner", PLAN, None, None, None, attempts)


def catalog(target: str, status: PrerequisiteLogicStatus) -> CanTakeCatalog:
    from app.rules.models import DependencyGroup, DependencyType
    groups = () if status is not PrerequisiteLogicStatus.VERIFIED else (
        DependencyGroup(1, DependencyType.PREREQUISITE, ("1501110",)),
    )
    return CanTakeCatalog(PLAN, (PlanCourseRule(target, status, groups),), (
        CourseIdentity(target, CourseCatalogStatus.KNOWN),
        CourseIdentity("1501110", CourseCatalogStatus.KNOWN),
    ))


def decide(target: str, status: PrerequisiteLogicStatus, *attempts: StudentCourseAttempt) -> Decision:
    persisted = state(*attempts)
    return evaluate_can_take(catalog(target, status), CanTakeRequest(PLAN, target, persisted.attempts)).decision


def test_persisted_attempt_mapping_preserves_phase5_prerequisite_semantics() -> None:
    passed = StudentCourseAttempt("1501110", AttemptOutcome.PASSED)
    failed = StudentCourseAttempt("1501110", AttemptOutcome.FAILED)
    assert decide("1501112", PrerequisiteLogicStatus.VERIFIED, passed) is Decision.ELIGIBLE
    assert decide("1501112", PrerequisiteLogicStatus.VERIFIED, failed) is Decision.NOT_ELIGIBLE
    assert decide("1501112", PrerequisiteLogicStatus.VERIFIED) is Decision.NOT_ELIGIBLE
    assert decide("1501112", PrerequisiteLogicStatus.VERIFIED, failed, passed) is Decision.ELIGIBLE
    assert decide("1501112", PrerequisiteLogicStatus.VERIFIED, passed, failed) is Decision.ELIGIBLE


def test_non_executable_and_no_prerequisite_targets_remain_phase5_decisions() -> None:
    assert decide("1505311", PrerequisiteLogicStatus.UNRESOLVED) is Decision.REVIEW_REQUIRED
    assert decide("1505320", PrerequisiteLogicStatus.SOURCE_CONFLICT) is Decision.REVIEW_REQUIRED
    assert decide("0200115", PrerequisiteLogicStatus.NOT_APPLICABLE) is Decision.ELIGIBLE


def test_referenced_only_code_survives_persistence_aggregate_unchanged() -> None:
    persisted = state(StudentCourseAttempt("0300103", AttemptOutcome.PASSED))
    assert persisted.attempts[0].course_code == "0300103"
