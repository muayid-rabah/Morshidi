"""Independent orchestration tests for the eligibility application service."""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest

from app.catalog.errors import CatalogIntegrityError, StudyPlanNotFound
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CourseCatalogStatus,
    CourseIdentity,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)
from app.services.eligibility import EligibilityService

PLAN_ID = UUID("10000000-0000-0000-0000-000000000005")


class FakeRepository:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[tuple[UUID, str]] = []

    async def load_target_rules(self, study_plan_id: UUID, target_course_code: str):
        self.calls.append((study_plan_id, target_course_code))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def verified_catalog() -> CanTakeCatalog:
    return CanTakeCatalog(
        study_plan_id=str(PLAN_ID),
        plan_courses=(
            PlanCourseRule(
                "1501112",
                PrerequisiteLogicStatus.VERIFIED,
                (DependencyGroup(1, DependencyType.PREREQUISITE, ("1501110",)),),
            ),
        ),
        courses=(
            CourseIdentity("1501112", CourseCatalogStatus.KNOWN),
            CourseIdentity("1501110", CourseCatalogStatus.KNOWN),
        ),
    )


def test_service_passes_repository_catalog_directly_to_evaluator() -> None:
    repository = FakeRepository(verified_catalog())
    result = asyncio.run(
        EligibilityService(repository).evaluate_can_take(
            PLAN_ID,
            "1501112",
            (StudentCourseAttempt("1501110", AttemptOutcome.PASSED),),
        )
    )
    assert result.decision.value == "ELIGIBLE"
    assert repository.calls == [(PLAN_ID, "1501112")]


@pytest.mark.parametrize("error", [StudyPlanNotFound("missing"), CatalogIntegrityError("bad data")])
def test_service_propagates_repository_failures_without_relabeling(error: Exception) -> None:
    with pytest.raises(type(error)):
        asyncio.run(EligibilityService(FakeRepository(error)).evaluate_can_take(PLAN_ID, "1501112", ()))
