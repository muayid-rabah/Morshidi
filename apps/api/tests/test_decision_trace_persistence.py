"""Unit tests for P8 Slice 2B's trusted repository, integrity gate, and authorization service."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from app.advisor_persistence.models import AdvisorAccessContext
from app.advisor_service import AdvisorAuthorizationError, AdvisorAuthorizationErrorCode
from app.core.auth import CurrentUser
from app.decision_trace import (
    ActorClass,
    DecisionStatus,
    DecisionType,
    EvidenceReference,
    MaterialityClass,
    ProvenanceClass,
    RedactionProfile,
    ReplayStatus,
    SubjectScopeType,
    calculate_integrity_hash,
    canonical_ledger_payload,
    create_canonical_ledger_entry,
    create_superseding_entry,
)
from app.decision_trace_persistence import (
    DecisionTraceErrorCode,
    DecisionTracePersistenceError,
    DecisionTraceService,
    SupabaseDecisionTraceRepository,
)


def _entry(
    *,
    student_id: UUID | None = None,
    university_id: UUID | None = None,
    actor_id: UUID | None = None,
    **changes: Any,
):
    student_id = student_id or uuid4()
    university_id = university_id or uuid4()
    actor_id = actor_id or student_id
    values: dict[str, Any] = {
        "ledger_entry_id": str(uuid4()),
        "decision_type": DecisionType.MOCK_REGISTRATION_SUBMIT,
        "materiality_class": MaterialityClass.LEDGER_REQUIRED,
        "actor_class": ActorClass.STUDENT,
        "actor_id": str(actor_id),
        "subject_scope_type": SubjectScopeType.STUDENT_INDIVIDUAL,
        "subject_scope_id": f"student-scope:{student_id}",
        "university_id": str(university_id),
        "student_user_id": str(student_id),
        "source_engine": "mock_registration",
        "source_engine_version": "6.5",
        "policy_version": "P8.1",
        "source_versions": ("catalog:plan12:v1", "policy:p8.1"),
        "input_state_reference": None,
        "scenario_id": None,
        "decision_status": DecisionStatus.VALIDATED,
        "outcome_reference": "نتيجة-معتمدة",
        "evidence_references": (
            EvidenceReference("policy", "P8.1", "v1", "section-5", "https://local.invalid/policy"),
            EvidenceReference("catalog", "خطة-12", "v1", None, None),
        ),
        "domain_trace_reference": None,
        "provenance_class": ProvenanceClass.AUTHORITATIVE_TRANSACTION,
        "created_at": datetime(2026, 9, 25, 13, 14, 15, 123456, tzinfo=timezone.utc),
        "redaction_profile": RedactionProfile.STUDENT_SAFE,
        "previous_entry_hash": None,
        "supersedes_entry_id": None,
        "replay_status": ReplayStatus.REPLAYABLE_EXACT,
        "limitations": ("SOURCE_SNAPSHOT_REQUIRED", "TEST_ONLY"),
    }
    values.update(changes)
    return create_canonical_ledger_entry(**values)


def _rows_for(entry):
    payload = canonical_ledger_payload(entry)
    evidence = payload.pop("evidence_references")
    payload["integrity_hash"] = entry.integrity_hash
    evidence_rows = [
        {
            "ledger_entry_id": entry.ledger_entry_id,
            "evidence_position": position,
            **reference,
        }
        for position, reference in enumerate(evidence, start=1)
    ]
    return payload, evidence_rows


class FakeTraceRepository:
    def __init__(self, entry=None) -> None:
        self.entry = entry
        self.appended: list[Any] = []
        self.load_calls: list[tuple[str, str, str]] = []

    async def append(self, entry):
        self.appended.append(entry)
        return entry.ledger_entry_id

    async def load_student_entry(self, *, ledger_entry_id, student_user_id, university_id):
        self.load_calls.append((ledger_entry_id, student_user_id, university_id))
        if (
            self.entry is not None
            and self.entry.ledger_entry_id == ledger_entry_id
            and self.entry.student_user_id == student_user_id
            and self.entry.university_id == university_id
        ):
            return self.entry
        return None


class FakeStudentScopes:
    def __init__(self, university: UUID | None) -> None:
        self.university = university

    async def load_student_authoritative_university(self, student_user_id: UUID) -> UUID | None:
        return self.university


class FakeAdvisorAuthorization:
    def __init__(self, context: AdvisorAccessContext | Exception) -> None:
        self.context = context
        self.calls: list[tuple[UUID | str | None, UUID | str | None]] = []

    async def authorize_advisor_for_student(self, advisor, student):
        self.calls.append((advisor, student))
        if isinstance(self.context, Exception):
            raise self.context
        return self.context


def _service(repository: FakeTraceRepository, university: UUID, advisor=None) -> DecisionTraceService:
    advisor = advisor or FakeAdvisorAuthorization(
        AdvisorAccessContext(uuid4(), uuid4(), university, uuid4(), "TEST", "v1")
    )
    return DecisionTraceService(repository, FakeStudentScopes(university), advisor)  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_repository_serializes_canonical_rpc_payload_and_losslessly_reconstructs_round_trip() -> None:
    student_id, university_id = uuid4(), uuid4()
    entry = _entry(student_id=student_id, university_id=university_id)
    parent, evidence = _rows_for(entry)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            assert request.url.path == "/rest/v1/rpc/append_decision_trace_ledger"
            body = json.loads(request.content)
            assert body["p_entry"]["integrity_hash"] == entry.integrity_hash
            assert body["p_entry"]["created_at"] == "2026-09-25T13:14:15.123456Z"
            assert body["p_evidence"] == canonical_ledger_payload(entry)["evidence_references"]
            return httpx.Response(200, json=entry.ledger_entry_id)
        if request.url.path.endswith("/decision_trace_ledger"):
            assert "limit=2" in str(request.url)
            return httpx.Response(200, json=[parent])
        if request.url.path.endswith("/decision_trace_evidence"):
            assert "order=evidence_position.asc" in str(request.url)
            return httpx.Response(200, json=evidence)
        raise AssertionError(request.url)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        repository = SupabaseDecisionTraceRepository("http://local.test", "server-key", client)
        assert await repository.append(entry) == entry.ledger_entry_id
        restored = await repository.load_student_entry(
            ledger_entry_id=entry.ledger_entry_id,
            student_user_id=str(student_id),
            university_id=str(university_id),
        )

    assert restored is not None
    assert canonical_ledger_payload(restored) == canonical_ledger_payload(entry)
    assert restored.integrity_hash == entry.integrity_hash
    assert restored.evidence_references == entry.evidence_references
    assert len(requests) == 3


@pytest.mark.anyio
async def test_repository_fails_closed_when_stored_payload_no_longer_matches_stored_hash() -> None:
    entry = _entry()
    parent, evidence = _rows_for(entry)
    parent["outcome_reference"] = "tampered-after-append"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decision_trace_ledger"):
            return httpx.Response(200, json=[parent])
        if request.url.path.endswith("/decision_trace_evidence"):
            return httpx.Response(200, json=evidence)
        raise AssertionError(request.url)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        repository = SupabaseDecisionTraceRepository("http://local.test", "server-key", client)
        with pytest.raises(DecisionTracePersistenceError) as exc_info:
            await repository.load_student_entry(
                ledger_entry_id=entry.ledger_entry_id,
                student_user_id=entry.student_user_id or "",
                university_id=entry.university_id,
            )
    assert exc_info.value.code is DecisionTraceErrorCode.INTEGRITY_FAILURE


@pytest.mark.anyio
async def test_repository_rejects_oversized_evidence_before_append_and_partial_retrieval() -> None:
    entry = _entry()
    references = tuple(
        EvidenceReference("bounded-source", f"reference-{index:04d}", "v1")
        for index in range(1001)
    )
    oversized = replace(entry, evidence_references=references, integrity_hash="")
    oversized = replace(oversized, integrity_hash=calculate_integrity_hash(oversized))

    def append_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("oversized entry must not issue an append request")

    async with httpx.AsyncClient(transport=httpx.MockTransport(append_handler)) as client:
        repository = SupabaseDecisionTraceRepository("http://local.test", "server-key", client)
        with pytest.raises(DecisionTracePersistenceError) as append_error:
            await repository.append(oversized)
    assert append_error.value.code is DecisionTraceErrorCode.INTEGRITY_FAILURE

    parent, _ = _rows_for(entry)
    too_many_rows = [
        {
            "ledger_entry_id": entry.ledger_entry_id,
            "evidence_position": index,
            "source": "bounded-source",
            "identifier": f"reference-{index:04d}",
            "version": "v1",
            "locator": None,
            "uri": None,
        }
        for index in range(1, 1002)
    ]

    def retrieval_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decision_trace_ledger"):
            return httpx.Response(200, json=[parent])
        if request.url.path.endswith("/decision_trace_evidence"):
            assert "limit=1001" in str(request.url)
            return httpx.Response(200, json=too_many_rows)
        raise AssertionError(request.url)

    async with httpx.AsyncClient(transport=httpx.MockTransport(retrieval_handler)) as client:
        repository = SupabaseDecisionTraceRepository("http://local.test", "server-key", client)
        with pytest.raises(DecisionTracePersistenceError) as retrieval_error:
            await repository.load_student_entry(
                ledger_entry_id=entry.ledger_entry_id,
                student_user_id=entry.student_user_id or "",
                university_id=entry.university_id,
            )
    assert retrieval_error.value.code is DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE


@pytest.mark.anyio
async def test_repository_preserves_python_canonical_unicode_evidence_order_by_position() -> None:
    base = _entry()
    unordered = replace(
        base,
        evidence_references=(
            EvidenceReference("source", "😀", "v1"),
            EvidenceReference("source", "漢", "v1"),
            EvidenceReference("source", "é", "v1"),
            EvidenceReference("source", "a", "v1"),
        ),
        integrity_hash="",
    )
    entry = create_canonical_ledger_entry(
        **{name: getattr(unordered, name) for name in unordered.__dataclass_fields__}
    )
    parent, evidence = _rows_for(entry)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content)
            assert [item["identifier"] for item in body["p_evidence"]] == ["a", "é", "漢", "😀"]
            return httpx.Response(200, json=entry.ledger_entry_id)
        if request.url.path.endswith("/decision_trace_ledger"):
            return httpx.Response(200, json=[parent])
        if request.url.path.endswith("/decision_trace_evidence"):
            return httpx.Response(200, json=evidence)
        raise AssertionError(request.url)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        repository = SupabaseDecisionTraceRepository("http://local.test", "server-key", client)
        assert await repository.append(entry) == entry.ledger_entry_id
        restored = await repository.load_student_entry(
            ledger_entry_id=entry.ledger_entry_id,
            student_user_id=entry.student_user_id or "",
            university_id=entry.university_id,
        )
    assert restored is not None
    assert restored.evidence_references == entry.evidence_references


@pytest.mark.anyio
async def test_user_submitted_authoritative_outcome_is_rejected_even_with_a_valid_hash() -> None:
    student_id, university_id = uuid4(), uuid4()
    repository = FakeTraceRepository()
    service = _service(repository, university_id)
    valid = _entry(student_id=student_id, university_id=university_id)

    fabricated = replace(
        valid,
        outcome_reference="fabricated-authoritative-academic-outcome",
        integrity_hash="",
    )
    fabricated = replace(fabricated, integrity_hash=calculate_integrity_hash(fabricated))
    with pytest.raises(DecisionTracePersistenceError) as exc_info:
        await service.append_student(CurrentUser(str(student_id)), fabricated)
    assert exc_info.value.code is DecisionTraceErrorCode.UNSUPPORTED_APPEND_AUTHORITY
    assert repository.appended == []


@pytest.mark.anyio
async def test_user_supplied_engine_provenance_and_evidence_are_never_promoted_to_trusted_events() -> None:
    student_id, university_id = uuid4(), uuid4()
    repository = FakeTraceRepository()
    service = _service(repository, university_id)
    valid = _entry(student_id=student_id, university_id=university_id)
    untrusted = replace(
        valid,
        source_engine="user-claimed-engine",
        provenance_class=ProvenanceClass.GOVERNED_ASSESSMENT,
        evidence_references=(EvidenceReference("user", "private-assertion", "v1"),),
        integrity_hash="",
    )
    untrusted = replace(untrusted, integrity_hash=calculate_integrity_hash(untrusted))
    with pytest.raises(DecisionTracePersistenceError) as exc_info:
        await service.append_student(CurrentUser(str(student_id)), untrusted)
    assert exc_info.value.code is DecisionTraceErrorCode.UNSUPPORTED_APPEND_AUTHORITY
    assert repository.appended == []


@pytest.mark.anyio
async def test_user_submitted_envelopes_never_reach_the_repository_even_when_malformed() -> None:
    student_id, university_id = uuid4(), uuid4()
    repository = FakeTraceRepository()
    service = _service(repository, university_id)
    valid = _entry(student_id=student_id, university_id=university_id)
    for candidate in (replace(valid, integrity_hash="a" * 64), replace(valid, outcome_reference="tampered")):
        with pytest.raises(DecisionTracePersistenceError) as exc_info:
            await service.append_student(CurrentUser(str(student_id)), candidate)
        assert exc_info.value.code is DecisionTraceErrorCode.UNSUPPORTED_APPEND_AUTHORITY
    assert repository.appended == []


@pytest.mark.anyio
async def test_raw_uuid_is_not_a_verified_transport_principal() -> None:
    student_id, university_id = uuid4(), uuid4()
    repository = FakeTraceRepository()
    service = _service(repository, university_id)
    entry = _entry(student_id=student_id, university_id=university_id)
    with pytest.raises(DecisionTracePersistenceError) as exc_info:
        await service.get_student_trace(student_id, entry.ledger_entry_id)  # type: ignore[arg-type]
    assert exc_info.value.code is DecisionTraceErrorCode.AUTH_REQUIRED
    assert repository.appended == []


@pytest.mark.anyio
async def test_student_safe_retrieval_requires_stored_student_visibility_and_omits_free_form_fields() -> None:
    student_id, university_id = uuid4(), uuid4()
    entry = _entry(student_id=student_id, university_id=university_id)
    repository = FakeTraceRepository(entry)
    service = _service(repository, university_id)

    view = await service.get_student_trace(CurrentUser(str(student_id)), entry.ledger_entry_id)

    assert view.metadata.ledger_entry_id == entry.ledger_entry_id
    assert not hasattr(view.metadata, "student_user_id")
    assert not hasattr(view.metadata, "subject_scope_id")
    assert not hasattr(view.metadata, "limitations")
    assert not hasattr(view, "evidence_references")
    assert repository.load_calls == [(entry.ledger_entry_id, str(student_id), str(university_id))]

    restricted = _entry(
        student_id=student_id,
        university_id=university_id,
        redaction_profile=RedactionProfile.ADVISOR_SAFE,
        evidence_references=(EvidenceReference("restricted", "sensitive-identifier", "v1"),),
        limitations=("sensitive limitation",),
    )
    with pytest.raises(DecisionTracePersistenceError) as denied:
        await _service(FakeTraceRepository(restricted), university_id).get_student_trace(
            CurrentUser(str(student_id)), restricted.ledger_entry_id
        )
    assert denied.value.code is DecisionTraceErrorCode.ACCESS_DENIED


@pytest.mark.anyio
async def test_advisor_retrieval_requires_p7_authorization_and_revocation_denial_happens_before_load() -> None:
    advisor_id, student_id, university_id = uuid4(), uuid4(), uuid4()
    entry = _entry(student_id=student_id, university_id=university_id)
    allowed = FakeAdvisorAuthorization(
        AdvisorAccessContext(advisor_id, student_id, university_id, uuid4(), "TEST", "v1")
    )
    repository = FakeTraceRepository(entry)
    service = _service(repository, university_id, allowed)

    view = await service.get_advisor_trace(
        CurrentUser(str(advisor_id)), student_id, entry.ledger_entry_id
    )
    assert view.metadata.ledger_entry_id == entry.ledger_entry_id
    assert allowed.calls == [(advisor_id, student_id)]

    revoked = FakeAdvisorAuthorization(
        AdvisorAuthorizationError(
            AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH,
            "assignment revoked",
        )
    )
    denied_repository = FakeTraceRepository(entry)
    denied_service = _service(denied_repository, university_id, revoked)
    with pytest.raises(DecisionTracePersistenceError) as exc_info:
        await denied_service.get_advisor_trace(
            CurrentUser(str(advisor_id)), student_id, entry.ledger_entry_id
        )
    assert exc_info.value.code is DecisionTraceErrorCode.ACCESS_DENIED
    assert denied_repository.load_calls == []


@pytest.mark.anyio
async def test_analyst_and_anonymous_individual_reads_are_denied_without_repository_load() -> None:
    repository = FakeTraceRepository()
    service = _service(repository, uuid4())
    with pytest.raises(DecisionTracePersistenceError) as analyst:
        await service.get_institutional_individual_trace(CurrentUser(str(uuid4())), "entry-id")
    assert analyst.value.code is DecisionTraceErrorCode.ACCESS_DENIED
    with pytest.raises(DecisionTracePersistenceError) as anonymous:
        await service.get_student_trace(None, "entry-id")
    assert anonymous.value.code is DecisionTraceErrorCode.AUTH_REQUIRED
    assert repository.load_calls == []
