"""Student-only Decision History projection and repository query regressions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest

from app.core.auth import CurrentUser
from app.decision_trace import (
    ActorClass, DecisionStatus, DecisionType, EvidenceReference, MaterialityClass,
    ProvenanceClass, RedactionProfile, ReplayStatus, SubjectScopeType,
    create_canonical_ledger_entry, create_superseding_entry,
)
from app.decision_trace_persistence import (
    DecisionTraceErrorCode, DecisionTracePersistenceError, DecisionTraceService,
    SupabaseDecisionTraceRepository,
)
from app.decision_trace.canonical import canonical_ledger_payload


STUDENT = uuid4()
OTHER = uuid4()
UNIVERSITY = uuid4()
FOREIGN_UNIVERSITY = uuid4()
STAMP = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def entry(*, student=STUDENT, university=UNIVERSITY, profile=RedactionProfile.STUDENT_SAFE,
          created_at=STAMP, **changes):
    values = dict(
        ledger_entry_id=str(uuid4()), decision_type=DecisionType.MOCK_REGISTRATION_SUBMIT,
        materiality_class=MaterialityClass.LEDGER_REQUIRED, actor_class=ActorClass.STUDENT,
        actor_id=str(student), subject_scope_type=SubjectScopeType.STUDENT_INDIVIDUAL,
        subject_scope_id=f"student:{student}", university_id=str(university),
        student_user_id=str(student), source_engine="mock_registration",
        source_engine_version="6.5", policy_version="P8.1",
        source_versions=("catalog:v1", "policy:v1"), input_state_reference=None,
        scenario_id=None, decision_status=DecisionStatus.VALIDATED,
        outcome_reference="test-only-result", evidence_references=(
            EvidenceReference("catalog", "plan-test", "v1", "section 2", "https://example.test/source"),
            EvidenceReference("policy", "test-only", "v2", "article 4", "javascript:alert(1)"),
        ), domain_trace_reference=None, provenance_class=ProvenanceClass.AUTHORITATIVE_TRANSACTION,
        created_at=created_at, redaction_profile=profile, previous_entry_hash=None,
        supersedes_entry_id=None, replay_status=ReplayStatus.REPLAYABLE_EXACT,
        limitations=("TEST_ONLY",),
    )
    values.update(changes)
    return create_canonical_ledger_entry(**values)


class Scope:
    def __init__(self, university=UNIVERSITY):
        self.university = university

    async def load_student_authoritative_university(self, student_user_id):
        return self.university


class Repository:
    def __init__(self, entries=()):
        self.entries = tuple(entries)
        self.calls = []

    async def list_student_entries(self, *, student_user_id, university_id, limit,
                                   before_created_at=None, before_entry_id=None):
        self.calls.append((student_user_id, university_id, limit, before_created_at, before_entry_id))
        rows = [item for item in self.entries if item.student_user_id == student_user_id
                and item.university_id == university_id
                and item.subject_scope_type is SubjectScopeType.STUDENT_INDIVIDUAL
                and item.redaction_profile is RedactionProfile.STUDENT_SAFE]
        rows.sort(key=lambda item: (item.created_at, item.ledger_entry_id), reverse=True)
        if before_created_at is not None:
            rows = [item for item in rows if (item.created_at, item.ledger_entry_id)
                    < (before_created_at, before_entry_id)]
        return tuple(rows[:limit])

    async def load_student_entry(self, *, ledger_entry_id, student_user_id, university_id,
                                 redaction_profile=None):
        return next((item for item in self.entries if item.ledger_entry_id == ledger_entry_id
                     and item.student_user_id == student_user_id
                     and item.university_id == university_id
                     and (redaction_profile is None or item.redaction_profile.value == redaction_profile)), None)

    async def load_student_successor(self, *, ledger_entry_id, student_user_id, university_id):
        return next((item for item in self.entries if item.supersedes_entry_id == ledger_entry_id
                     and item.student_user_id == student_user_id
                     and item.university_id == university_id
                     and item.redaction_profile is RedactionProfile.STUDENT_SAFE), None)


def service(rows=(), university=UNIVERSITY):
    repository = Repository(rows)
    return DecisionTraceService(repository, Scope(university), None), repository


@pytest.mark.anyio
async def test_owner_only_student_safe_newest_first_and_empty_history():
    older = entry(created_at=STAMP)
    newer = entry(created_at=STAMP.replace(hour=13))
    restricted = entry(profile=RedactionProfile.ADVISOR_SAFE)
    other = entry(student=OTHER)
    foreign = entry(university=FOREIGN_UNIVERSITY)
    viewer, repository = service((older, restricted, other, foreign, newer))
    page = await viewer.list_student_history(CurrentUser(str(STUDENT)))
    assert [item.ledger_entry_id for item in page] == [newer.ledger_entry_id, older.ledger_entry_id]
    assert all(item.integrity_status == "VERIFIED" for item in page)
    assert repository.calls == [(str(STUDENT), str(UNIVERSITY), 20, None, None)]
    empty, _ = service()
    assert await empty.list_student_history(CurrentUser(str(STUDENT))) == ()


@pytest.mark.anyio
async def test_stable_tuple_pagination_and_bound_passed_to_repository():
    rows = sorted((entry() for _ in range(3)), key=lambda item: item.ledger_entry_id, reverse=True)
    viewer, repository = service(rows)
    first = await viewer.list_student_history(CurrentUser(str(STUDENT)), limit=2)
    second = await viewer.list_student_history(
        CurrentUser(str(STUDENT)), limit=2,
        before_created_at=first[-1].created_at, before_entry_id=first[-1].ledger_entry_id,
    )
    assert [item.ledger_entry_id for item in first + second] == [item.ledger_entry_id for item in rows]
    assert repository.calls[-1][2:] == (2, first[-1].created_at, first[-1].ledger_entry_id)


@pytest.mark.anyio
async def test_detail_exact_evidence_safe_uri_versions_replay_and_no_private_fields():
    own = entry()
    viewer, _ = service((own,))
    detail = await viewer.get_student_history_detail(CurrentUser(str(STUDENT)), own.ledger_entry_id)
    assert detail.integrity_status == "VERIFIED"
    assert detail.source_versions == own.source_versions
    assert detail.replay_status is ReplayStatus.REPLAYABLE_EXACT
    assert [item.identifier for item in detail.evidence] == ["plan-test", "test-only"]
    assert detail.evidence[0].uri == "https://example.test/source"
    assert detail.evidence[1].uri is None
    assert not hasattr(detail, "actor_id") and not hasattr(detail, "integrity_hash")
    assert not hasattr(detail, "outcome_reference") and not hasattr(detail, "input_state_reference")


@pytest.mark.anyio
async def test_cross_owner_tenant_restricted_and_missing_detail_do_not_disclose():
    own = entry()
    restricted = entry(profile=RedactionProfile.ADVISOR_SAFE)
    viewer, _ = service((own, restricted))
    for principal, target in ((OTHER, own.ledger_entry_id), (STUDENT, restricted.ledger_entry_id),
                              (STUDENT, str(uuid4()))):
        with pytest.raises(DecisionTracePersistenceError) as caught:
            await viewer.get_student_history_detail(CurrentUser(str(principal)), target)
        assert caught.value.code in {DecisionTraceErrorCode.NOT_FOUND, DecisionTraceErrorCode.ACCESS_DENIED}
    foreign_viewer, _ = service((own,), FOREIGN_UNIVERSITY)
    with pytest.raises(DecisionTracePersistenceError) as caught:
        await foreign_viewer.get_student_history_detail(CurrentUser(str(STUDENT)), own.ledger_entry_id)
    assert caught.value.code is DecisionTraceErrorCode.NOT_FOUND


@pytest.mark.anyio
async def test_mismatched_repository_projection_fails_closed():
    wrong = entry(student=OTHER)

    class BrokenRepository(Repository):
        async def load_student_entry(self, **kwargs):
            return wrong

    viewer = DecisionTraceService(BrokenRepository((wrong,)), Scope(), None)
    with pytest.raises(DecisionTracePersistenceError) as caught:
        await viewer.get_student_history_detail(CurrentUser(str(STUDENT)), wrong.ledger_entry_id)
    assert caught.value.code is DecisionTraceErrorCode.PERSISTENCE_INTEGRITY_FAILURE


@pytest.mark.anyio
async def test_tampered_trace_fails_closed_in_list_and_detail():
    original = entry()
    tampered = replace(original, policy_version="changed-without-rehash")
    viewer, _ = service((tampered,))
    for operation in (viewer.list_student_history(CurrentUser(str(STUDENT))),
                      viewer.get_student_history_detail(CurrentUser(str(STUDENT)), tampered.ledger_entry_id)):
        with pytest.raises(DecisionTracePersistenceError) as caught:
            await operation
        assert caught.value.code is DecisionTraceErrorCode.INTEGRITY_FAILURE


@pytest.mark.anyio
async def test_supersession_derived_only_from_verified_visible_history():
    old = entry()
    new = create_superseding_entry(old, ledger_entry_id=str(uuid4()))
    viewer, _ = service((old, new))
    older = await viewer.get_student_history_detail(CurrentUser(str(STUDENT)), old.ledger_entry_id)
    newer = await viewer.get_student_history_detail(CurrentUser(str(STUDENT)), new.ledger_entry_id)
    assert older.is_superseded and older.supersedes_entry_id is None
    assert newer.supersedes_entry_id == old.ledger_entry_id and not newer.is_superseded
    broken = replace(new, previous_entry_hash="f" * 64)
    broken_viewer, _ = service((old, broken))
    with pytest.raises(DecisionTracePersistenceError):
        await broken_viewer.get_student_history_detail(CurrentUser(str(STUDENT)), old.ledger_entry_id)


def stored_rows(item):
    row = canonical_ledger_payload(item)
    evidence = row.pop("evidence_references")
    row["integrity_hash"] = item.integrity_hash
    return row, [{"ledger_entry_id": item.ledger_entry_id, "evidence_position": index, **ref}
                 for index, ref in enumerate(evidence, 1)]


@pytest.mark.anyio
async def test_repository_query_enforces_owner_tenant_profile_order_and_cursor():
    first = entry()
    row, evidence = stored_rows(first)
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("decision_trace_ledger"):
            return httpx.Response(200, json=[row])
        return httpx.Response(200, json=evidence)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        repository = SupabaseDecisionTraceRepository("http://local.test", "server-key", client)
        result = await repository.list_student_entries(
            student_user_id=str(STUDENT), university_id=str(UNIVERSITY), limit=20,
        )
    assert result == (first,)
    params = seen[0].url.params
    assert params["student_user_id"] == f"eq.{STUDENT}"
    assert params["university_id"] == f"eq.{UNIVERSITY}"
    assert params["subject_scope_type"] == "eq.STUDENT_INDIVIDUAL"
    assert params["redaction_profile"] == "eq.STUDENT_SAFE"
    assert params["order"] == "created_at.desc,ledger_entry_id.desc"
    assert params["limit"] == "20"
    assert len(seen) == 2 and seen[1].url.params["order"] == "evidence_position.asc"


@pytest.mark.anyio
async def test_repository_cursor_and_limit_are_bounded():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        repository = SupabaseDecisionTraceRepository("http://local.test", "server-key", client)
        for bad in (0, 51):
            with pytest.raises(ValueError):
                await repository.list_student_entries(
                    student_user_id=str(STUDENT), university_id=str(UNIVERSITY), limit=bad,
                )
        assert await repository.list_student_entries(
            student_user_id=str(STUDENT), university_id=str(UNIVERSITY), limit=2,
            before_created_at=STAMP, before_entry_id=str(uuid4()),
        ) == ()
    assert len(seen) == 1 and "created_at.lt." in seen[0].url.params["or"]


@pytest.mark.anyio
async def test_repository_student_detail_filters_redaction_before_loading_evidence():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        repository = SupabaseDecisionTraceRepository("http://local.test", "server-key", client)
        assert await repository.load_student_entry(
            ledger_entry_id=str(uuid4()), student_user_id=str(STUDENT),
            university_id=str(UNIVERSITY), redaction_profile="STUDENT_SAFE",
        ) is None
    assert len(seen) == 1
    assert seen[0].url.params["redaction_profile"] == "eq.STUDENT_SAFE"
