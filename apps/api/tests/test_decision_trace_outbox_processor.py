"""Deterministic unit tests for DecisionTraceOutboxProcessor."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.decision_trace import (
    CanonicalLedgerEntry,
    create_canonical_ledger_entry,
    verify_integrity_hash,
)
from app.decision_trace_persistence import (
    ClaimedOutboxEvent,
    DecisionTraceErrorCode,
    DecisionTraceOutboxProcessor,
    DecisionTracePersistenceError,
    OutboxErrorClass,
    OutboxProcessingStatus,
    P6DecisionTraceOutboxEvent,
    TrustedP6OutboxProjection,
    map_verified_mock_registration_submit,
)
from app.mock_registration.models import IntentLifecycle, IntentProvenance, ValidationStatus
from app.mock_registration.registries import ReasonCode
from app.mock_registration_persistence.models import PersistedIntentCourse, PersistedIntentRevision


def _valid_revision(**changes: object) -> PersistedIntentRevision:
    values: dict[str, object] = {
        "revision_id": UUID("00000000-0000-0000-0000-000000000101"),
        "intent_id": UUID("00000000-0000-0000-0000-000000000102"),
        "owner_user_id": UUID("00000000-0000-0000-0000-000000000103"),
        "university_id": UUID("00000000-0000-0000-0000-000000000104"),
        "major_id": UUID("00000000-0000-0000-0000-000000000105"),
        "study_plan_id": UUID("00000000-0000-0000-0000-000000000106"),
        "study_plan_version": "plan12:v7",
        "target_period_id": UUID("00000000-0000-0000-0000-000000000107"),
        "revision": 3,
        "lifecycle_status": IntentLifecycle.SUBMITTED,
        "validation_status": ValidationStatus.VALID,
        "content_fingerprint": "a" * 64,
        "intent_provenance": IntentProvenance.DECLARED_STUDENT_INTENT,
        "intent_source_version": "intent:v2",
        "validation_reason_codes": (ReasonCode.MOCK_REG_ELIGIBILITY_REVIEW_REQUIRED,),
        "catalog_source_versions": ("catalog:z", "catalog:a"),
        "prerequisite_source_versions": ("prereq:v3",),
        "progress_state_version": "progress:v9",
        "progress_state_reference": "progress-state:opaque",
        "phase5_policy_version": "phase5:v1",
        "phase6_policy_version": "phase6:v1",
        "p6_contract_version": "1.0",
        "target_period_source_version": "period:v1",
        "transparency_notice_version": "notice:v1",
        "transparency_acknowledged_at": datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
        "actor_class": "STUDENT_AUTHENTICATED",
        "created_at": datetime(2026, 9, 25, 12, 1, 2, 123456, tzinfo=timezone.utc),
        "courses": (
            PersistedIntentCourse(UUID("00000000-0000-0000-0000-000000000108"), "AI101", 1),
            PersistedIntentCourse(UUID("00000000-0000-0000-0000-000000000109"), "AI201", 2),
        ),
    }
    values.update(changes)
    return PersistedIntentRevision(**values)  # type: ignore[arg-type]


def _snapshot(revision: PersistedIntentRevision) -> dict[str, object]:
    return {
        "revision_id": str(revision.revision_id),
        "intent_id": str(revision.intent_id),
        "owner_user_id": str(revision.owner_user_id),
        "university_id": str(revision.university_id),
        "major_id": str(revision.major_id),
        "study_plan_id": str(revision.study_plan_id),
        "study_plan_version": revision.study_plan_version,
        "target_period_id": str(revision.target_period_id),
        "revision": revision.revision,
        "lifecycle_status": revision.lifecycle_status.value,
        "validation_status": revision.validation_status.value,
        "content_fingerprint": revision.content_fingerprint,
        "intent_provenance": revision.intent_provenance.value,
        "intent_source_version": revision.intent_source_version,
        "validation_reason_codes": [item.value for item in revision.validation_reason_codes],
        "catalog_source_versions": list(revision.catalog_source_versions),
        "prerequisite_source_versions": list(revision.prerequisite_source_versions),
        "progress_state_version": revision.progress_state_version,
        "progress_state_reference": revision.progress_state_reference,
        "phase5_policy_version": revision.phase5_policy_version,
        "phase6_policy_version": revision.phase6_policy_version,
        "p6_contract_version": revision.p6_contract_version,
        "target_period_source_version": revision.target_period_source_version,
        "transparency_notice_version": revision.transparency_notice_version,
        "actor_class": revision.actor_class,
        "created_at": revision.created_at.isoformat(),
        "courses": [
            {
                "course_id": str(course.course_id),
                "course_code": course.course_code,
                "selection_order": course.selection_order,
            }
            for course in revision.courses
        ],
    }


def _claimed_event(
    revision: PersistedIntentRevision | None = None,
    *,
    outbox_required: bool = True,
    claim_token: str = "worker-1:token-123",
) -> ClaimedOutboxEvent:
    rev = revision or _valid_revision()
    event = P6DecisionTraceOutboxEvent(
        event_id=rev.revision_id,
        revision_id=rev.revision_id,
        owner_user_id=rev.owner_user_id,
        university_id=rev.university_id,
        major_id=rev.major_id,
        study_plan_id=rev.study_plan_id,
        study_plan_version=rev.study_plan_version,
        target_period_id=rev.target_period_id,
        revision=rev.revision,
        event_type="MOCK_REGISTRATION_SUBMIT",
        snapshot_contract_version="1.0",
        source_snapshot=_snapshot(rev),
        processing_state="PROCESSING",
    )
    projection = TrustedP6OutboxProjection(
        revision=rev,
        outbox_required=outbox_required,
        outbox_event=event,
    )
    return ClaimedOutboxEvent(
        event_id=rev.revision_id,
        revision_id=rev.revision_id,
        claim_token=claim_token,
        attempt_count=1,
        lease_expires_at=datetime.now(timezone.utc),
        projection=projection,
    )


class FakeOutboxRepository:
    def __init__(self, events: list[ClaimedOutboxEvent] | None = None) -> None:
        self.events = events or []
        self.completed: list[tuple[UUID, str, str]] = []
        self.released: list[tuple[UUID, str, str, int, int]] = []
        self.failed: list[tuple[UUID, str, str]] = []
        self.fail_completion = False
        self.fail_completion_stale = False

    async def claim_events(
        self,
        *,
        worker_id: str,
        batch_size: int = 10,
        lease_seconds: int = 60,
        university_id: UUID | None = None,
    ) -> tuple[ClaimedOutboxEvent, ...]:
        claimed = tuple(self.events[:batch_size])
        self.events = self.events[batch_size:]
        return claimed

    async def complete_event(
        self,
        *,
        event_id: UUID,
        claim_token: str,
        completed_ledger_integrity_hash: str,
    ) -> None:
        if self.fail_completion_stale:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.STALE_CLAIM, "stale claim token"
            )
        if self.fail_completion:
            raise DecisionTracePersistenceError(
                DecisionTraceErrorCode.PERSISTENCE_UNAVAILABLE, "completion failed"
            )
        self.completed.append((event_id, claim_token, completed_ledger_integrity_hash))

    async def release_event(
        self,
        *,
        event_id: UUID,
        claim_token: str,
        error_class: str = "TRANSIENT_P8_UNAVAILABLE",
        backoff_seconds: int = 30,
        max_attempts: int = 5,
    ) -> None:
        self.released.append((event_id, claim_token, error_class, backoff_seconds, max_attempts))

    async def fail_event(
        self,
        *,
        event_id: UUID,
        claim_token: str,
        error_class: str,
    ) -> None:
        self.failed.append((event_id, claim_token, error_class))


class FakeLedgerRepository:
    def __init__(self) -> None:
        self.appended: list[CanonicalLedgerEntry] = []
        self.existing_entries: dict[str, CanonicalLedgerEntry] = {}
        self.append_error: DecisionTracePersistenceError | None = None

    async def append(self, entry: CanonicalLedgerEntry) -> str:
        if self.append_error:
            raise self.append_error
        self.appended.append(entry)
        self.existing_entries[entry.ledger_entry_id] = entry
        return entry.ledger_entry_id

    async def load_student_entry(
        self,
        *,
        ledger_entry_id: str,
        student_user_id: str,
        university_id: str,
    ) -> CanonicalLedgerEntry | None:
        return self.existing_entries.get(ledger_entry_id)


@pytest.mark.anyio
async def test_empty_batch() -> None:
    outbox_repo = FakeOutboxRepository([])
    ledger_repo = FakeLedgerRepository()
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)

    summary = await processor.process_batch(worker_id="worker-test")
    assert summary.claimed_count == 0
    assert summary.completed_count == 0
    assert summary.retried_count == 0
    assert summary.failed_count == 0
    assert len(summary.results) == 0


@pytest.mark.anyio
async def test_successful_event() -> None:
    event = _claimed_event()
    outbox_repo = FakeOutboxRepository([event])
    ledger_repo = FakeLedgerRepository()
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)

    summary = await processor.process_batch(worker_id="worker-test")
    assert summary.claimed_count == 1
    assert summary.completed_count == 1
    assert summary.retried_count == 0
    assert summary.failed_count == 0
    assert len(summary.results) == 1

    res = summary.results[0]
    assert res.status == OutboxProcessingStatus.COMPLETED
    assert res.ledger_entry_id == str(event.event_id)
    assert res.integrity_hash is not None
    assert res.error_code is None

    assert len(ledger_repo.appended) == 1
    assert len(outbox_repo.completed) == 1
    assert outbox_repo.completed[0][0] == event.event_id
    assert outbox_repo.completed[0][1] == event.claim_token
    assert outbox_repo.completed[0][2] == res.integrity_hash


@pytest.mark.anyio
async def test_multiple_bounded_events() -> None:
    events = [
        _claimed_event(_valid_revision(revision_id=UUID("00000000-0000-0000-0000-000000000201"))),
        _claimed_event(_valid_revision(revision_id=UUID("00000000-0000-0000-0000-000000000202"))),
    ]
    outbox_repo = FakeOutboxRepository(events)
    ledger_repo = FakeLedgerRepository()
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)

    summary = await processor.process_batch(worker_id="worker-test", batch_size=2)
    assert summary.claimed_count == 2
    assert summary.completed_count == 2
    assert len(outbox_repo.completed) == 2


@pytest.mark.anyio
async def test_mapper_rejection_fails_closed() -> None:
    # unverified outbox_required = False causes mapper rejection
    event = _claimed_event(outbox_required=False)
    outbox_repo = FakeOutboxRepository([event])
    ledger_repo = FakeLedgerRepository()
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)

    summary = await processor.process_batch(worker_id="worker-test")
    assert summary.claimed_count == 1
    assert summary.completed_count == 0
    assert summary.failed_count == 1

    res = summary.results[0]
    assert res.status == OutboxProcessingStatus.PERMANENT_FAILURE
    assert res.error_code == OutboxErrorClass.CONTRACT_FAILURE.value

    # Never appends to ledger
    assert len(ledger_repo.appended) == 0
    # Calls fail_event
    assert len(outbox_repo.failed) == 1
    assert outbox_repo.failed[0][0] == event.event_id
    assert outbox_repo.failed[0][2] == OutboxErrorClass.CONTRACT_FAILURE.value


@pytest.mark.anyio
async def test_transient_append_failure_releases_for_retry() -> None:
    event = _claimed_event()
    outbox_repo = FakeOutboxRepository([event])
    ledger_repo = FakeLedgerRepository()
    ledger_repo.append_error = DecisionTracePersistenceError(
        DecisionTraceErrorCode.PERSISTENCE_UNAVAILABLE, "database connection dropped"
    )
    processor = DecisionTraceOutboxProcessor(
        outbox_repo, ledger_repo, max_attempts=3, backoff_seconds=15
    )

    summary = await processor.process_batch(worker_id="worker-test")
    assert summary.claimed_count == 1
    assert summary.retried_count == 1
    assert summary.completed_count == 0

    res = summary.results[0]
    assert res.status == OutboxProcessingStatus.TRANSIENT_RETRY
    assert res.error_code == OutboxErrorClass.TRANSIENT_P8_UNAVAILABLE.value

    assert len(outbox_repo.released) == 1
    assert outbox_repo.released[0][0] == event.event_id
    assert outbox_repo.released[0][2] == OutboxErrorClass.TRANSIENT_P8_UNAVAILABLE.value
    assert outbox_repo.released[0][3] == 15  # backoff
    assert outbox_repo.released[0][4] == 3   # max_attempts


@pytest.mark.anyio
async def test_permanent_validation_failure() -> None:
    event = _claimed_event()
    outbox_repo = FakeOutboxRepository([event])
    ledger_repo = FakeLedgerRepository()
    ledger_repo.append_error = DecisionTracePersistenceError(
        DecisionTraceErrorCode.INTEGRITY_FAILURE, "unsupported constraint"
    )
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)

    summary = await processor.process_batch(worker_id="worker-test")
    assert summary.claimed_count == 1
    assert summary.failed_count == 1

    res = summary.results[0]
    assert res.status == OutboxProcessingStatus.PERMANENT_FAILURE
    assert res.error_code == OutboxErrorClass.CONTRACT_FAILURE.value
    assert len(outbox_repo.failed) == 1


@pytest.mark.anyio
async def test_duplicate_retry_matching_converges_idempotently() -> None:
    event = _claimed_event()
    outbox_repo = FakeOutboxRepository([event])
    ledger_repo = FakeLedgerRepository()

    # Pre-populate ledger repository with the exact canonical entry
    canonical = map_verified_mock_registration_submit(event.projection)
    ledger_repo.existing_entries[canonical.ledger_entry_id] = canonical

    # Next append call raises PERSISTENCE_CONFLICT
    ledger_repo.append_error = DecisionTracePersistenceError(
        DecisionTraceErrorCode.PERSISTENCE_CONFLICT, "unique violation"
    )
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)

    summary = await processor.process_batch(worker_id="worker-test")
    assert summary.claimed_count == 1
    assert summary.completed_count == 1
    assert summary.failed_count == 0

    res = summary.results[0]
    assert res.status == OutboxProcessingStatus.IDEMPOTENT_DUPLICATE
    assert res.ledger_entry_id == canonical.ledger_entry_id
    assert res.integrity_hash == canonical.integrity_hash

    # Successfully completed the outbox event without duplicate row
    assert len(outbox_repo.completed) == 1
    assert outbox_repo.completed[0][2] == canonical.integrity_hash


@pytest.mark.anyio
async def test_duplicate_retry_mismatch_fails_closed() -> None:
    event = _claimed_event()
    outbox_repo = FakeOutboxRepository([event])
    ledger_repo = FakeLedgerRepository()

    # Pre-populate with a conflicting entry that has a DIFFERENT hash
    canonical = map_verified_mock_registration_submit(event.projection)
    conflicting = CanonicalLedgerEntry(
        ledger_entry_id=canonical.ledger_entry_id,
        decision_type=canonical.decision_type,
        materiality_class=canonical.materiality_class,
        actor_class=canonical.actor_class,
        actor_id=canonical.actor_id,
        subject_scope_type=canonical.subject_scope_type,
        subject_scope_id=canonical.subject_scope_id,
        university_id=canonical.university_id,
        student_user_id=canonical.student_user_id,
        source_engine="DIFFERENT_ENGINE",
        source_engine_version=canonical.source_engine_version,
        policy_version=canonical.policy_version,
        source_versions=canonical.source_versions,
        input_state_reference=canonical.input_state_reference,
        scenario_id=canonical.scenario_id,
        decision_status=canonical.decision_status,
        outcome_reference=canonical.outcome_reference,
        evidence_references=canonical.evidence_references,
        domain_trace_reference=canonical.domain_trace_reference,
        provenance_class=canonical.provenance_class,
        created_at=canonical.created_at,
        redaction_profile=canonical.redaction_profile,
        integrity_hash="b" * 64,
        previous_entry_hash=None,
        supersedes_entry_id=None,
        replay_status=canonical.replay_status,
        limitations=canonical.limitations,
        hash_contract_version="1.0",
        decision_schema_version="1.0",
    )
    ledger_repo.existing_entries[canonical.ledger_entry_id] = conflicting
    ledger_repo.append_error = DecisionTracePersistenceError(
        DecisionTraceErrorCode.PERSISTENCE_CONFLICT, "unique violation"
    )
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)

    summary = await processor.process_batch(worker_id="worker-test")
    assert summary.claimed_count == 1
    assert summary.failed_count == 1
    assert summary.completed_count == 0

    res = summary.results[0]
    assert res.status == OutboxProcessingStatus.PERMANENT_FAILURE
    assert res.error_code == OutboxErrorClass.P8_DUPLICATE_MISMATCH.value
    assert len(outbox_repo.failed) == 1
    assert outbox_repo.failed[0][2] == OutboxErrorClass.P8_DUPLICATE_MISMATCH.value


@pytest.mark.anyio
async def test_completion_failure_handles_gracefully() -> None:
    event = _claimed_event()
    outbox_repo = FakeOutboxRepository([event])
    outbox_repo.fail_completion = True
    ledger_repo = FakeLedgerRepository()
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)

    summary = await processor.process_batch(worker_id="worker-test")
    assert summary.claimed_count == 1
    assert summary.failed_count == 1

    res = summary.results[0]
    assert res.status == OutboxProcessingStatus.COMPLETION_FAILED
    assert res.error_code == "COMPLETION_ERROR"


@pytest.mark.anyio
async def test_lease_expiry_handling_stale_claim() -> None:
    event = _claimed_event()
    outbox_repo = FakeOutboxRepository([event])
    outbox_repo.fail_completion_stale = True
    ledger_repo = FakeLedgerRepository()
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)

    summary = await processor.process_batch(worker_id="worker-test")
    assert summary.claimed_count == 1
    assert summary.failed_count == 1

    res = summary.results[0]
    assert res.status == OutboxProcessingStatus.COMPLETION_FAILED
    assert res.error_code == "STALE_CLAIM"


@pytest.mark.anyio
async def test_safe_error_code_projection_no_raw_exception_leakage() -> None:
    event = _claimed_event()
    outbox_repo = FakeOutboxRepository([event])
    ledger_repo = FakeLedgerRepository()
    ledger_repo.append_error = RuntimeError("SECRET_DB_PASSWORD_123 in /var/log/pg.log")
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)

    summary = await processor.process_batch(worker_id="worker-test")
    res = summary.results[0]
    assert "SECRET" not in str(res.error_code)
    assert res.error_code == OutboxErrorClass.TRANSIENT_P8_UNAVAILABLE.value
