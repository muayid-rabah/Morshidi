"""Read-only academic catalog infrastructure for the rules engine."""

from app.catalog.errors import (
    CatalogIntegrityError,
    CatalogRepositoryError,
    CatalogTransportError,
    StudyPlanNotFound,
    TargetCourseNotFound,
    TargetCourseNotInStudyPlan,
)
from app.catalog.repository import AcademicCatalogRepository
from app.catalog.supabase_repository import SupabaseAcademicCatalogRepository

__all__ = [
    "AcademicCatalogRepository",
    "CatalogIntegrityError",
    "CatalogRepositoryError",
    "CatalogTransportError",
    "StudyPlanNotFound",
    "SupabaseAcademicCatalogRepository",
    "TargetCourseNotFound",
    "TargetCourseNotInStudyPlan",
]
