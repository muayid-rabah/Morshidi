"""Bounded, retry-safe decision trace outbox processor."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.decision_trace import CanonicalLedgerEntry, canonical_ledger_payload

from .errors import DecisionTraceErrorCode, DecisionTracePersistenceError
from .models import (
    ClaimedOutboxEvent,
    OutboxBatchSummary,
    OutboxErrorClass,
    OutboxProcessingResult,
    OutboxProcessingStatus,
)
from .outbox_repository import SupabaseDecisionTraceOutboxRepository
from .p6_outbox_mapper import map_verified_mock_registration_submit


class DecisionTraceRepositoryProtocol(Protocol):
    async def append(self, entry: CanonicalLedgerEntry) -> str: ...

    async def load_student_entry(
        self,
        *,
        ledger_entry_id: str,
        student_user_id: str,
        university_id: str,
    ) -> CanonicalLedgerEntry | None: ...


class DecisionTraceOutboxProcessor:
    """Internal-only processor that claims P6 outbox events, maps, appends, and marks completion."""

    def __init__(
        self,
        outbox_repository: SupabaseDecisionTraceOutboxRepository,
        ledger_repository: DecisionTraceRepositoryProtocol,
        *,
        max_attempts: int = 5,
        backoff_seconds: int = 30,
    ) -> None:
        self._outbox_repo = outbox_repository
        self._ledger_repo = ledger_repository
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds

    async def process_batch(
        self,
        *,
        worker_id: str,
        batch_size: int = 10,
        lease_seconds: int = 60,
        university_id: UUID | None = None,
    ) -> OutboxBatchSummary:
        """Claim a bounded batch of eligible events and process each sequentially."""
        events = await self._outbox_repo.claim_events(
            worker_id=worker_id,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            university_id=university_id,
        )
        if not events:
            return OutboxBatchSummary(
                claimed_count=0,
                completed_count=0,
                retried_count=0,
                failed_count=0,
                results=(),
            )

        results: list[OutboxProcessingResult] = []
        completed = 0
        retried = 0
        failed = 0

        for event in events:
            result = await self.process_event(event)
            results.append(result)
            if result.status in (
                OutboxProcessingStatus.COMPLETED,
                OutboxProcessingStatus.IDEMPOTENT_DUPLICATE,
            ):
                completed += 1
            elif result.status == OutboxProcessingStatus.TRANSIENT_RETRY:
                retried += 1
            else:
                failed += 1

        return OutboxBatchSummary(
            claimed_count=len(events),
            completed_count=completed,
            retried_count=retried,
            failed_count=failed,
            results=tuple(results),
        )

    async def process_event(
        self,
        event: ClaimedOutboxEvent,
    ) -> OutboxProcessingResult:
        """Process a single claimed outbox event with deterministic mapping and idempotent append."""

        # 1. Deterministic mapping via existing P6 -> P8 mapper
        try:
            canonical_entry = map_verified_mock_registration_submit(event.projection)
        except DecisionTracePersistenceError as error:
            msg = str(error)
            error_class = (
                OutboxErrorClass.SOURCE_INTEGRITY_FAILURE.value
                if ("integrity" in msg or "reconstruct" in msg or "canonical" in msg or "hash" in msg)
                else OutboxErrorClass.CONTRACT_FAILURE.value
            )
            try:
                await self._outbox_repo.fail_event(
                    event_id=event.event_id,
                    claim_token=event.claim_token,
                    error_class=error_class,
                )
            except Exception:
                pass
            return OutboxProcessingResult(
                event_id=event.event_id,
                status=OutboxProcessingStatus.PERMANENT_FAILURE,
                ledger_entry_id=None,
                integrity_hash=None,
                error_code=error_class,
            )
        except Exception:
            error_class = OutboxErrorClass.CONTRACT_FAILURE.value
            try:
                await self._outbox_repo.fail_event(
                    event_id=event.event_id,
                    claim_token=event.claim_token,
                    error_class=error_class,
                )
            except Exception:
                pass
            return OutboxProcessingResult(
                event_id=event.event_id,
                status=OutboxProcessingStatus.PERMANENT_FAILURE,
                ledger_entry_id=None,
                integrity_hash=None,
                error_code=error_class,
            )

        # 2. Append to P8 ledger via trusted repository
        try:
            appended_id = await self._ledger_repo.append(canonical_entry)
            if appended_id != str(event.event_id):
                error_class = OutboxErrorClass.CONTRACT_FAILURE.value
                try:
                    await self._outbox_repo.fail_event(
                        event_id=event.event_id,
                        claim_token=event.claim_token,
                        error_class=error_class,
                    )
                except Exception:
                    pass
                return OutboxProcessingResult(
                    event_id=event.event_id,
                    status=OutboxProcessingStatus.PERMANENT_FAILURE,
                    ledger_entry_id=None,
                    integrity_hash=None,
                    error_code=error_class,
                )
        except DecisionTracePersistenceError as error:
            if error.code == DecisionTraceErrorCode.PERSISTENCE_CONFLICT:
                # Identity already exists: load existing entry to verify exact duplicate
                try:
                    existing = await self._ledger_repo.load_student_entry(
                        ledger_entry_id=str(event.event_id),
                        student_user_id=str(canonical_entry.student_user_id),
                        university_id=str(canonical_entry.university_id),
                    )
                except Exception:
                    existing = None

                if (
                    existing is not None
                    and existing.integrity_hash == canonical_entry.integrity_hash
                    and canonical_ledger_payload(existing) == canonical_ledger_payload(canonical_entry)
                ):
                    # Verified identical duplicate: complete outbox idempotently
                    try:
                        await self._outbox_repo.complete_event(
                            event_id=event.event_id,
                            claim_token=event.claim_token,
                            completed_ledger_integrity_hash=canonical_entry.integrity_hash,
                        )
                        return OutboxProcessingResult(
                            event_id=event.event_id,
                            status=OutboxProcessingStatus.IDEMPOTENT_DUPLICATE,
                            ledger_entry_id=str(event.event_id),
                            integrity_hash=canonical_entry.integrity_hash,
                            error_code=None,
                        )
                    except DecisionTracePersistenceError as complete_err:
                        return OutboxProcessingResult(
                            event_id=event.event_id,
                            status=OutboxProcessingStatus.COMPLETION_FAILED,
                            ledger_entry_id=str(event.event_id),
                            integrity_hash=canonical_entry.integrity_hash,
                            error_code="STALE_CLAIM"
                            if complete_err.code == DecisionTraceErrorCode.STALE_CLAIM
                            else "COMPLETION_ERROR",
                        )
                else:
                    # Payload or hash mismatch: permanent integrity failure
                    error_class = OutboxErrorClass.P8_DUPLICATE_MISMATCH.value
                    try:
                        await self._outbox_repo.fail_event(
                            event_id=event.event_id,
                            claim_token=event.claim_token,
                            error_class=error_class,
                        )
                    except Exception:
                        pass
                    return OutboxProcessingResult(
                        event_id=event.event_id,
                        status=OutboxProcessingStatus.PERMANENT_FAILURE,
                        ledger_entry_id=None,
                        integrity_hash=None,
                        error_code=error_class,
                    )

            elif error.code == DecisionTraceErrorCode.PERSISTENCE_UNAVAILABLE:
                # Transient persistence failure: release for bounded retry
                error_class = OutboxErrorClass.TRANSIENT_P8_UNAVAILABLE.value
                try:
                    await self._outbox_repo.release_event(
                        event_id=event.event_id,
                        claim_token=event.claim_token,
                        error_class=error_class,
                        backoff_seconds=self._backoff_seconds,
                        max_attempts=self._max_attempts,
                    )
                except Exception:
                    pass
                return OutboxProcessingResult(
                    event_id=event.event_id,
                    status=OutboxProcessingStatus.TRANSIENT_RETRY,
                    ledger_entry_id=None,
                    integrity_hash=None,
                    error_code=error_class,
                )

            else:
                # Other persistence error (e.g. INTEGRITY_FAILURE): fail closed
                error_class = OutboxErrorClass.CONTRACT_FAILURE.value
                try:
                    await self._outbox_repo.fail_event(
                        event_id=event.event_id,
                        claim_token=event.claim_token,
                        error_class=error_class,
                    )
                except Exception:
                    pass
                return OutboxProcessingResult(
                    event_id=event.event_id,
                    status=OutboxProcessingStatus.PERMANENT_FAILURE,
                    ledger_entry_id=None,
                    integrity_hash=None,
                    error_code=error_class,
                )

        except Exception:
            # Unexpected transient error: release for bounded retry
            error_class = OutboxErrorClass.TRANSIENT_P8_UNAVAILABLE.value
            try:
                await self._outbox_repo.release_event(
                    event_id=event.event_id,
                    claim_token=event.claim_token,
                    error_class=error_class,
                    backoff_seconds=self._backoff_seconds,
                    max_attempts=self._max_attempts,
                )
            except Exception:
                pass
            return OutboxProcessingResult(
                event_id=event.event_id,
                status=OutboxProcessingStatus.TRANSIENT_RETRY,
                ledger_entry_id=None,
                integrity_hash=None,
                error_code=error_class,
            )

        # 3. Mark outbox event completed with verified ledger integrity hash
        try:
            await self._outbox_repo.complete_event(
                event_id=event.event_id,
                claim_token=event.claim_token,
                completed_ledger_integrity_hash=canonical_entry.integrity_hash,
            )
            return OutboxProcessingResult(
                event_id=event.event_id,
                status=OutboxProcessingStatus.COMPLETED,
                ledger_entry_id=str(event.event_id),
                integrity_hash=canonical_entry.integrity_hash,
                error_code=None,
            )
        except DecisionTracePersistenceError as complete_err:
            return OutboxProcessingResult(
                event_id=event.event_id,
                status=OutboxProcessingStatus.COMPLETION_FAILED,
                ledger_entry_id=str(event.event_id),
                integrity_hash=canonical_entry.integrity_hash,
                error_code="STALE_CLAIM"
                if complete_err.code == DecisionTraceErrorCode.STALE_CLAIM
                else "COMPLETION_ERROR",
            )
        except Exception:
            return OutboxProcessingResult(
                event_id=event.event_id,
                status=OutboxProcessingStatus.COMPLETION_FAILED,
                ledger_entry_id=str(event.event_id),
                integrity_hash=canonical_entry.integrity_hash,
                error_code="COMPLETION_ERROR",
            )
