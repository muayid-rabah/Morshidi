"""Finite service error codes and exceptions for Institutional Intelligence Service."""

from __future__ import annotations

from enum import Enum


class InstitutionalIntelligenceServiceErrorCode(str, Enum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    INSTITUTIONAL_ACCESS_DENIED = "INSTITUTIONAL_ACCESS_DENIED"
    TARGET_PERIOD_UNAVAILABLE = "TARGET_PERIOD_UNAVAILABLE"
    STUDY_PLAN_UNAVAILABLE = "STUDY_PLAN_UNAVAILABLE"
    COURSE_UNAVAILABLE = "COURSE_UNAVAILABLE"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    AGGREGATION_SCOPE_INVALID = "AGGREGATION_SCOPE_INVALID"
    PERSISTENCE_UNAVAILABLE = "PERSISTENCE_UNAVAILABLE"


HTTP_STATUS = {
    InstitutionalIntelligenceServiceErrorCode.AUTH_REQUIRED: 401,
    InstitutionalIntelligenceServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED: 403,
    InstitutionalIntelligenceServiceErrorCode.TARGET_PERIOD_UNAVAILABLE: 404,
    InstitutionalIntelligenceServiceErrorCode.STUDY_PLAN_UNAVAILABLE: 404,
    InstitutionalIntelligenceServiceErrorCode.COURSE_UNAVAILABLE: 404,
    InstitutionalIntelligenceServiceErrorCode.RESOURCE_NOT_FOUND: 404,
    InstitutionalIntelligenceServiceErrorCode.AGGREGATION_SCOPE_INVALID: 422,
    InstitutionalIntelligenceServiceErrorCode.PERSISTENCE_UNAVAILABLE: 503,
}

ERROR_MESSAGES = {
    InstitutionalIntelligenceServiceErrorCode.AUTH_REQUIRED: "Authentication is required",
    InstitutionalIntelligenceServiceErrorCode.INSTITUTIONAL_ACCESS_DENIED: "Institutional intelligence access is denied",
    InstitutionalIntelligenceServiceErrorCode.TARGET_PERIOD_UNAVAILABLE: "Target period is unavailable",
    InstitutionalIntelligenceServiceErrorCode.STUDY_PLAN_UNAVAILABLE: "Study plan is unavailable",
    InstitutionalIntelligenceServiceErrorCode.COURSE_UNAVAILABLE: "Course is unavailable in study plan or catalog",
    InstitutionalIntelligenceServiceErrorCode.RESOURCE_NOT_FOUND: "Requested resource was not found",
    InstitutionalIntelligenceServiceErrorCode.AGGREGATION_SCOPE_INVALID: "Institutional intelligence scope is invalid",
    InstitutionalIntelligenceServiceErrorCode.PERSISTENCE_UNAVAILABLE: "Institutional storage is unavailable",
}


class InstitutionalIntelligenceServiceError(RuntimeError):
    def __init__(
        self,
        code: InstitutionalIntelligenceServiceErrorCode,
        detail: str | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.detail = detail or ERROR_MESSAGES.get(code, "An error occurred")

