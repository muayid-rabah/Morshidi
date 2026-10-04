"""Student-to-catalog orchestration tests for academic progress."""

import asyncio
from decimal import Decimal

from app.progress.models import (
    AcademicProgressCatalog,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.rules.models import AttemptOutcome, CourseCatalogStatus, StudentCourseAttempt
from app.services.student import StudentService
from app.student.models import StudentAcademicState

OWNER = "11111111-1111-1111-1111-111111111111"
PLAN = "10000000-0000-0000-0000-000000000005"
GROUP = "10000000-0000-0000-0000-000000000011"


class StudentRepository:
    def __init__(self, state):
        self.state = state
        self.owners = []

    async def load_student_academic_state(self, owner):
        self.owners.append(owner)
        return self.state


class CatalogRepository:
    def __init__(self, value):
        self.value = value
        self.plan_ids = []

    async def load_progress_catalog(self, plan_id):
        self.plan_ids.append(plan_id)
        return self.value


def test_service_loads_owner_state_then_its_selected_plan_and_passes_reported_facts() -> None:
    state = StudentAcademicState(
        "profile", OWNER, PLAN, Decimal("3.4"), Decimal("4"), Decimal("20"),
        (StudentCourseAttempt("1501110", AttemptOutcome.PASSED),),
    )
    catalog = AcademicProgressCatalog(
        ProgressStudyPlan(PLAN, Decimal("3")),
        (ProgressRequirementGroup(
            GROUP, PLAN, "FACULTY_REQUIRED", "كلية", None, "faculty",
            RequirementType.REQUIRED, Decimal("3"), 1,
        ),),
        (ProgressPlanCourse(
            "membership", PLAN, GROUP, "1501110", CourseCatalogStatus.KNOWN,
            Decimal("3"), 1,
        ),),
    )
    student_repository = StudentRepository(state)
    catalog_repository = CatalogRepository(catalog)
    service = StudentService(student_repository, eligibility=None, catalog_repository=catalog_repository)

    progress = asyncio.run(service.get_academic_progress(OWNER))

    assert student_repository.owners == [OWNER]
    assert catalog_repository.plan_ids == [PLAN]
    assert progress.completed_plan_credits == 3
    assert progress.reported_cumulative_gpa == Decimal("3.4")
    assert progress.reported_earned_credit_hours == Decimal("20")
