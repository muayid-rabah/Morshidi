"""Conservative, allowlisted service and processor models for P8 decision trace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from app.decision_trace.registries import DecisionStatus, DecisionType, ReplayStatus, ProvenanceClass

from .p6_outbox_mapper import TrustedP6OutboxProjection


class OutboxProcessingStatus(str, Enum):
    COMPLETED = "COMPLETED"
    IDEMPOTENT_DUPLICATE = "IDEMPOTENT_DUPLICATE"
    TRANSIENT_RETRY = "TRANSIENT_RETRY"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"
    COMPLETION_FAILED = "COMPLETION_FAILED"


class OutboxErrorClass(str, Enum):
    TRANSIENT_P8_UNAVAILABLE = "TRANSIENT_P8_UNAVAILABLE"
    P8_DUPLICATE_MATCHED = "P8_DUPLICATE_MATCHED"
    P8_DUPLICATE_MISMATCH = "P8_DUPLICATE_MISMATCH"
    SOURCE_INTEGRITY_FAILURE = "SOURCE_INTEGRITY_FAILURE"
    CONTRACT_FAILURE = "CONTRACT_FAILURE"


@dataclass(frozen=True, slots=True)
class DecisionTraceSafeMetadata:
    """Stable, non-free-form metadata approved for the local individual projection."""

    ledger_entry_id: str
    decision_type: DecisionType
    decision_status: DecisionStatus
    created_at: datetime
    replay_status: ReplayStatus


@dataclass(frozen=True, slots=True)
class DecisionTraceSafeView:
    """Minimum individual projection; evidence is not projected in this local slice."""

    metadata: DecisionTraceSafeMetadata


@dataclass(frozen=True, slots=True)
class StudentDecisionHistoryItem:
    ledger_entry_id: str
    decision_type: DecisionType
    decision_status: DecisionStatus
    created_at: datetime
    source_engine: str
    source_engine_version: str
    policy_version: str
    replay_status: ReplayStatus
    supersedes_entry_id: str | None
    is_superseded: bool
    limitations: tuple[str, ...]
    integrity_status: str = "VERIFIED"


@dataclass(frozen=True, slots=True)
class StudentDecisionEvidence:
    source: str
    identifier: str
    version: str
    locator: str | None
    uri: str | None


@dataclass(frozen=True, slots=True)
class StudentDecisionHistoryDetail:
    ledger_entry_id: str
    decision_type: DecisionType
    decision_status: DecisionStatus
    created_at: datetime
    source_engine: str
    source_engine_version: str
    policy_version: str
    source_versions: tuple[str, ...]
    replay_status: ReplayStatus
    provenance_class: ProvenanceClass
    limitations: tuple[str, ...]
    integrity_status: str
    supersedes_entry_id: str | None
    is_superseded: bool
    evidence: tuple[StudentDecisionEvidence, ...]


@dataclass(frozen=True, slots=True)
class ClaimedOutboxEvent:
    """Bounded, leased outbox event with its verified P6 parent projection."""

    event_id: UUID
    revision_id: UUID
    claim_token: str
    attempt_count: int
    lease_expires_at: datetime
    projection: TrustedP6OutboxProjection


@dataclass(frozen=True, slots=True)
class OutboxProcessingResult:
    """Bounded, safe result of processing a single claimed outbox event."""

    event_id: UUID
    status: OutboxProcessingStatus
    ledger_entry_id: str | None = None
    integrity_hash: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class OutboxBatchSummary:
    """Batch processing metrics and typed individual results."""

    claimed_count: int
    completed_count: int
    retried_count: int
    failed_count: int
    results: tuple[OutboxProcessingResult, ...]
