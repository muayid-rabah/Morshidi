"""Phase P7.5 Advisor Copilot Package."""

from __future__ import annotations

from app.advisor_copilot.dispatcher import AdvisorCopilotService, AdvisorToolDispatcher
from app.advisor_copilot.errors import (
    AdvisorCopilotServiceError,
    AdvisorCopilotServiceErrorCode,
)
from app.advisor_copilot.models import (
    AdvisorToolExecutionRequest,
    AdvisorToolExecutionResponse,
)
from app.advisor_copilot.registries import (
    TOOL_AUTHORITY_CLASSES,
    TOOL_REQUIRES_TARGET_PERIOD,
    TOOL_SIDE_EFFECTS,
    AdvisorToolId,
    ToolAuthorityClass,
)

__all__ = [
    "AdvisorCopilotService",
    "AdvisorCopilotServiceError",
    "AdvisorCopilotServiceErrorCode",
    "AdvisorToolDispatcher",
    "AdvisorToolExecutionRequest",
    "AdvisorToolExecutionResponse",
    "AdvisorToolId",
    "TOOL_AUTHORITY_CLASSES",
    "TOOL_REQUIRES_TARGET_PERIOD",
    "TOOL_SIDE_EFFECTS",
    "ToolAuthorityClass",
]
