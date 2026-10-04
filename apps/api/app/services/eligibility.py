"""Thin application service for deterministic CAN TAKE evaluation."""

from __future__ import annotations

from uuid import UUID
from decimal import Decimal

from app.catalog.repository import AcademicCatalogRepository
from app.rules.evaluator import CanTakeResult, evaluate_can_take
from app.rules.models import CanTakeRequest, StudentCourseAttempt


class EligibilityConfigurationError(RuntimeError):
    """The server-side catalog repository has not been configured."""


class EligibilityService:
    """Coordinates repository resolution with the pure rules evaluator."""

    def __init__(self, repository: AcademicCatalogRepository) -> None:
        self._repository = repository

    async def evaluate_can_take(
        self,
        study_plan_id: UUID,
        target_course_code: str,
        student_attempts: tuple[StudentCourseAttempt, ...],
        earned_completed_credits: Decimal | None = None,
    ) -> CanTakeResult:
        """Load canonical rules and delegate the decision unchanged to the engine."""

        catalog = await self._repository.load_target_rules(study_plan_id, target_course_code)
        return evaluate_can_take(
            catalog,
            CanTakeRequest(
                study_plan_id=str(study_plan_id),
                target_course_code=target_course_code,
                student_attempts=student_attempts,
                earned_completed_credits=earned_completed_credits,
            ),
        )
