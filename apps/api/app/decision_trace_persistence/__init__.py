"""P8 trusted persistence, safe retrieval, and outbox processor boundary."""

from .errors import DecisionTraceErrorCode, DecisionTracePersistenceError
from .models import (
    ClaimedOutboxEvent,
    DecisionTraceSafeMetadata,
    DecisionTraceSafeView,
    OutboxBatchSummary,
    OutboxErrorClass,
    OutboxProcessingResult,
    OutboxProcessingStatus,
)
from .outbox_repository import SupabaseDecisionTraceOutboxRepository
from .p6_outbox_mapper import (
    P6DecisionTraceOutboxEvent,
    TrustedP6OutboxProjection,
    map_verified_mock_registration_submit,
)
from .processor import DecisionTraceOutboxProcessor
from .repository import SupabaseDecisionTraceRepository
from .service import DecisionTraceService

__all__ = [
    "DecisionTraceErrorCode",
    "DecisionTracePersistenceError",
    "DecisionTraceSafeView",
    "DecisionTraceSafeMetadata",
    "SupabaseDecisionTraceRepository",
    "DecisionTraceService",
    "P6DecisionTraceOutboxEvent",
    "TrustedP6OutboxProjection",
    "map_verified_mock_registration_submit",
    "SupabaseDecisionTraceOutboxRepository",
    "DecisionTraceOutboxProcessor",
    "ClaimedOutboxEvent",
    "OutboxProcessingResult",
    "OutboxProcessingStatus",
    "OutboxBatchSummary",
    "OutboxErrorClass",
]
