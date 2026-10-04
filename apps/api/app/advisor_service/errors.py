"""Phase P7.4 Advisor Authorization Service Errors."""

from __future__ import annotations

from enum import Enum


class AdvisorAuthorizationErrorCode(str, Enum):
    """Finite, audit-friendly internal error codes for advisor authorization decisions."""

    AUTH_REQUIRED = "AUTH_REQUIRED"
    ADVISOR_ROLE_REQUIRED = "ADVISOR_ROLE_REQUIRED"
    ADVISOR_ASSIGNMENT_REQUIRED = "ADVISOR_ASSIGNMENT_REQUIRED"
    ADVISOR_STUDENT_SCOPE_MISMATCH = "ADVISOR_STUDENT_SCOPE_MISMATCH"
    ADVISOR_SCOPE_MISMATCH = "ADVISOR_SCOPE_MISMATCH"
    ADVISOR_ACCESS_DENIED = "ADVISOR_ACCESS_DENIED"
    PERSISTENCE_UNAVAILABLE = "PERSISTENCE_UNAVAILABLE"


class AdvisorAuthorizationError(Exception):
    """Raised when an advisor authorization check fails."""

    def __init__(
        self,
        code: AdvisorAuthorizationErrorCode,
        message: str,
        status_code: int = 403,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
