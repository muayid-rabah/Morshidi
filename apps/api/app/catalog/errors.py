"""Typed failures for read-only academic catalog retrieval."""

from __future__ import annotations


class CatalogRepositoryError(Exception):
    """Base class for safe repository failures."""


class StudyPlanNotFound(CatalogRepositoryError):
    """The requested persistent study-plan identifier does not exist."""


class TargetCourseNotFound(CatalogRepositoryError):
    """The requested course code is absent from the plan university's catalog."""


class TargetCourseNotInStudyPlan(CatalogRepositoryError):
    """The course exists at the university but is not a member of the plan."""


class CatalogIntegrityError(CatalogRepositoryError):
    """Persisted catalog data cannot safely form a canonical rules snapshot."""


class CatalogTransportError(CatalogRepositoryError):
    """A safe description of a failed read from the Supabase Data API."""

    def __init__(
        self,
        operation: str,
        resource: str,
        *,
        status_code: int | None = None,
    ) -> None:
        self.operation = operation
        self.resource = resource
        self.status_code = status_code
        detail = f"Catalog {operation} failed for {resource}"
        if status_code is not None:
            detail += f" (HTTP {status_code})"
        super().__init__(detail)
