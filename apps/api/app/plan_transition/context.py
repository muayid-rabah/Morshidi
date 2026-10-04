"""Boundary between P12 logical identity and existing version-row academic catalogs."""

from __future__ import annotations

from dataclasses import dataclass

from app.catalog.roadmap_metadata import RoadmapPlanMetadata
from app.progress.models import AcademicProgressCatalog
from app.rules.models import CanTakeCatalog

from .models import PlanIdentity


@dataclass(frozen=True)
class PlanVersionContext:
    identity: PlanIdentity
    study_plan_version_row_id: str

    @property
    def cache_key(self) -> tuple[str, str, str, str, str]:
        return self.identity.key

    def validate_scoped_inputs(self, progress: AcademicProgressCatalog,
                               eligibility: CanTakeCatalog,
                               metadata: RoadmapPlanMetadata | None = None) -> None:
        if not self.study_plan_version_row_id or progress.study_plan.study_plan_id != self.study_plan_version_row_id \
           or eligibility.study_plan_id != self.study_plan_version_row_id \
           or (metadata is not None and metadata.study_plan_id != self.study_plan_version_row_id):
            raise ValueError("Plan/version catalog scope mismatch")
        if self.identity.institution_id == "" or self.identity.major_id == "" or self.identity.version_id == "":
            raise ValueError("Incomplete plan/version context")
