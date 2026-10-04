"""Finite error codes, status mappings, and exceptions for Advisor Copilot."""

from __future__ import annotations

from enum import Enum


class AdvisorCopilotServiceErrorCode(str, Enum):
    """Finite error codes distinguishing Advisor Copilot failures."""

    AUTH_REQUIRED = "AUTH_REQUIRED"
    ADVISOR_ACCESS_DENIED = "ADVISOR_ACCESS_DENIED"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_INPUT_INVALID = "TOOL_INPUT_INVALID"
    TARGET_RESOURCE_UNAVAILABLE = "TARGET_RESOURCE_UNAVAILABLE"
    PERSISTENCE_UNAVAILABLE = "PERSISTENCE_UNAVAILABLE"
    DOMAIN_VALIDATION_FAILED = "DOMAIN_VALIDATION_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    COMPUTE_CAPACITY_BUSY = "COMPUTE_CAPACITY_BUSY"
    COMPUTATION_TIMEOUT = "COMPUTATION_TIMEOUT"


HTTP_STATUS: dict[AdvisorCopilotServiceErrorCode, int] = {
    AdvisorCopilotServiceErrorCode.AUTH_REQUIRED: 401,
    AdvisorCopilotServiceErrorCode.ADVISOR_ACCESS_DENIED: 403,
    AdvisorCopilotServiceErrorCode.TOOL_NOT_FOUND: 422,
    AdvisorCopilotServiceErrorCode.TOOL_INPUT_INVALID: 422,
    AdvisorCopilotServiceErrorCode.TARGET_RESOURCE_UNAVAILABLE: 404,
    AdvisorCopilotServiceErrorCode.PERSISTENCE_UNAVAILABLE: 503,
    AdvisorCopilotServiceErrorCode.DOMAIN_VALIDATION_FAILED: 422,
    AdvisorCopilotServiceErrorCode.INTERNAL_ERROR: 500,
    AdvisorCopilotServiceErrorCode.COMPUTE_CAPACITY_BUSY: 503,
    AdvisorCopilotServiceErrorCode.COMPUTATION_TIMEOUT: 504,
}

ERROR_MESSAGES: dict[AdvisorCopilotServiceErrorCode, str] = {
    AdvisorCopilotServiceErrorCode.AUTH_REQUIRED: "Authentication is required for advisor access",
    AdvisorCopilotServiceErrorCode.ADVISOR_ACCESS_DENIED: "Advisor access is denied",
    AdvisorCopilotServiceErrorCode.TOOL_NOT_FOUND: "Requested advisor tool was not found in registry",
    AdvisorCopilotServiceErrorCode.TOOL_INPUT_INVALID: "Tool input parameters are invalid",
    AdvisorCopilotServiceErrorCode.TARGET_RESOURCE_UNAVAILABLE: "Target student academic resource is unavailable",
    AdvisorCopilotServiceErrorCode.PERSISTENCE_UNAVAILABLE: "Advisor storage or dependency is unavailable",
    AdvisorCopilotServiceErrorCode.DOMAIN_VALIDATION_FAILED: "Domain operation validation failed",
    AdvisorCopilotServiceErrorCode.INTERNAL_ERROR: "An internal error occurred during tool execution",
    AdvisorCopilotServiceErrorCode.COMPUTE_CAPACITY_BUSY: "Academic computation capacity is busy",
    AdvisorCopilotServiceErrorCode.COMPUTATION_TIMEOUT: "Academic computation timed out",
}


class AdvisorCopilotServiceError(RuntimeError):
    """Domain exception raised by Advisor Copilot dispatcher and adapters."""

    def __init__(
        self,
        code: AdvisorCopilotServiceErrorCode,
        detail: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.detail = detail or ERROR_MESSAGES.get(code, "Advisor tool execution failed")
        self.status_code = status_code or HTTP_STATUS.get(code, 500)
