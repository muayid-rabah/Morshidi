"""The narrow read contract used by future eligibility application code."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.rules.models import CanTakeCatalog
from app.progress.models import AcademicProgressCatalog
from app.advisor.models import ResolvedCourseReference
from app.catalog.roadmap_metadata import RoadmapPlanMetadata
from app.catalog.display import CourseDisplayIdentity


class AcademicCatalogRepository(Protocol):
    """Loads one resolved plan target as the canonical pure-engine snapshot.

    TODO(Phase 5.4): replace raw database UUID exposure with a stable public
    study-plan selector once the catalog defines one.
    """

    async def load_university_course_identities(
        self, university_id: UUID | str,
    ) -> tuple[CourseDisplayIdentity, ...]:
        """Batch display identities for an already-authorized university."""

    async def load_target_rules(
        self,
        study_plan_id: UUID | str,
        target_course_code: str,
    ) -> CanTakeCatalog:
        """Return the resolved target and dependency identities for CAN TAKE."""

    async def load_progress_catalog(
        self,
        study_plan_id: UUID | str,
    ) -> AcademicProgressCatalog:
        """Return one complete, explicitly ordered plan snapshot for progress."""

    async def load_plan_eligibility_catalog(
        self,
        study_plan_id: UUID | str,
    ) -> CanTakeCatalog:
        """Return all resolved plan-course rules and dependency identities for CAN TAKE simulation."""

    async def load_advisor_course_catalog(
        self,
        study_plan_id: UUID | str,
    ) -> tuple[ResolvedCourseReference, ...]:
        """Return canonical university-course identities for exact advisor resolution."""

    async def load_roadmap_plan_metadata(self, study_plan_id: UUID | str) -> RoadmapPlanMetadata:
        """Return plan-facing provenance without changing replay-pinned engine models."""
