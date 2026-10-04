"""Closed P6.3 service-error registry and privacy-safe failures."""

from __future__ import annotations

from enum import Enum

from app.mock_registration.registries import ReasonCode


class ServiceErrorCode(str, Enum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    OWNER_SCOPE_MISMATCH = "OWNER_SCOPE_MISMATCH"
    ACADEMIC_CONTEXT_UNAVAILABLE = "ACADEMIC_CONTEXT_UNAVAILABLE"
    ACADEMIC_STATE_CHANGED = "ACADEMIC_STATE_CHANGED"
    INVALID_INTENT = "INVALID_INTENT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    PERIOD_INVALID = "PERIOD_INVALID"
    PLAN_SCOPE_INVALID = "PLAN_SCOPE_INVALID"
    PERSISTENCE_CONFLICT = "PERSISTENCE_CONFLICT"
    PERSISTENCE_UNAVAILABLE = "PERSISTENCE_UNAVAILABLE"
    INSTITUTIONAL_ACCESS_DENIED = "INSTITUTIONAL_ACCESS_DENIED"
    AGGREGATION_SCOPE_INVALID = "AGGREGATION_SCOPE_INVALID"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"


HTTP_STATUS = {
    ServiceErrorCode.AUTH_REQUIRED: 401,
    ServiceErrorCode.OWNER_SCOPE_MISMATCH: 404,
    ServiceErrorCode.ACADEMIC_CONTEXT_UNAVAILABLE: 503,
    ServiceErrorCode.ACADEMIC_STATE_CHANGED: 409,
    ServiceErrorCode.INVALID_INTENT: 422,
    ServiceErrorCode.REVIEW_REQUIRED: 202,
    ServiceErrorCode.REVISION_CONFLICT: 409,
    ServiceErrorCode.PERIOD_INVALID: 422,
    ServiceErrorCode.PLAN_SCOPE_INVALID: 422,
    ServiceErrorCode.PERSISTENCE_CONFLICT: 409,
    ServiceErrorCode.PERSISTENCE_UNAVAILABLE: 503,
    ServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED: 403,
    ServiceErrorCode.AGGREGATION_SCOPE_INVALID: 422,
    ServiceErrorCode.RESOURCE_NOT_FOUND: 404,
}


class MockRegistrationServiceError(RuntimeError):
    def __init__(
        self,
        code: ServiceErrorCode,
        *,
        reasons: tuple[ReasonCode, ...] = (),
        current_revision: int | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.reasons = reasons
        self.current_revision = current_revision

