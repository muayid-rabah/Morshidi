"""Safe typed failures for student academic-state retrieval."""


class StudentRepositoryError(Exception):
    """Base class for student repository failures."""


class StudentProfileNotFound(StudentRepositoryError):
    """The owner has no persisted academic profile."""


class StudentProfileAlreadyExists(StudentRepositoryError):
    """The owner already has the single profile allowed by the MVP."""


class StudentStudyPlanNotFound(StudentRepositoryError):
    """The selected study plan does not exist."""


class StudentProfileValidationError(StudentRepositoryError):
    """Reported profile facts violate the accepted structural contract."""


class StudentAttemptNotFound(StudentRepositoryError):
    """The attempt is absent or does not belong to the trusted owner."""


class StudentCourseNotFound(StudentRepositoryError):
    """No catalog course has the exact requested code."""


class StudentCourseUniversityMismatch(StudentRepositoryError):
    """The code exists, but not at the profile study plan's university."""


class StudentProfileIntegrityError(StudentRepositoryError):
    """Persisted student data cannot safely map to rules input."""


class StudentProfileTransportError(StudentRepositoryError):
    """A safe description of a failed Supabase read."""

    def __init__(self, operation: str, resource: str, *, status_code: int | None = None) -> None:
        detail = f"Student {operation} failed for {resource}"
        if status_code is not None:
            detail += f" (HTTP {status_code})"
        super().__init__(detail)
