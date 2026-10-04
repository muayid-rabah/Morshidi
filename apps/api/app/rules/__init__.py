"""Pure, deterministic academic rules for Morshidi."""

from app.rules.evaluator import evaluate_can_take
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CanTakeDecision,
    CanTakeError,
    CanTakeRequest,
    CourseIdentity,
    Decision,
    DependencyGroup,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)

__all__ = [
    "AttemptOutcome",
    "CanTakeCatalog",
    "CanTakeDecision",
    "CanTakeError",
    "CanTakeRequest",
    "CourseIdentity",
    "Decision",
    "DependencyGroup",
    "PrerequisiteLogicStatus",
    "StudentCourseAttempt",
    "evaluate_can_take",
]
