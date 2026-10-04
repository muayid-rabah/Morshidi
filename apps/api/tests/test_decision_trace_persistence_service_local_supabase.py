"""P8 Slice 2B adversarial verification against the isolated Local Supabase stack."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import os
from uuid import UUID, uuid4

import httpx
import pytest

from app.advisor_persistence import SupabaseAdvisorAssignmentRepository
from app.advisor_service import AdvisorAuthorizationService
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


URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
SERVER_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")
ANON_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_ANON_KEY")

pytestmark = pytest.mark.skipif(
    not all((URL, SERVER_KEY, ANON_KEY)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values",
)


def _server_headers() -> dict[str, str]:
    return {
        "apikey": SERVER_KEY or "",
        "Authorization": f"Bearer {SERVER_KEY or ''}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _user_headers(token: str) -> dict[str, str]:
    return {
        "apikey": ANON_KEY or "",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _create_user(client: httpx.Client, label: str) -> tuple[str, str]:
    marker = uuid4().hex
    password = f"P8-2B-{marker}-Aa1!"
    email = f"p8-2b-{label}-{marker}@local.test"
    created = client.post(
        f"{URL}/auth/v1/admin/users",
        headers=_server_headers(),
        json={"email": email, "password": password, "email_confirm": True},
    )
    created.raise_for_status()
    signed_in = client.post(
        f"{URL}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": ANON_KEY or "", "Content-Type": "application/json"},
        json={"email": email, "password": password},
    )
    signed_in.raise_for_status()
    return created.json()["id"], signed_in.json()["access_token"]


def _plan_scope(client: httpx.Client) -> tuple[str, str]:
    response = client.get(
        f"{URL}/rest/v1/study_plans",
        headers=_server_headers(),
        params={"select": "id,majors(faculties(university_id))", "limit": "1"},
    )
    response.raise_for_status()
    row = response.json()[0]
    return row["id"], row["majors"]["faculties"]["university_id"]


def _create_profile(client: httpx.Client, student_user_id: str, plan_id: str) -> None:
    response = client.post(
        f"{URL}/rest/v1/student_academic_profiles",
        headers=_server_headers(),
        json={"owner_user_id": student_user_id, "study_plan_id": plan_id},
    )
    assert response.status_code == 201, response.text


def _membership(
    client: httpx.Client, user_id: str, university_id: str, role: str, active: bool = True
) -> str:
    response = client.post(
        f"{URL}/rest/v1/institutional_memberships",
        headers=_server_headers(),
        json={
            "subject_user_id": user_id,
            "university_id": university_id,
            "provider_namespace": f"p8-2b-{uuid4()}",
            "role": role,
            "active": active,
            "authority_source": "P8_2B_LOCAL_TEST",
            "authority_source_version": "v1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()[0]["id"]


def _assignment(client: httpx.Client, advisor_id: str, student_id: str, university_id: str) -> str:
    response = client.post(
        f"{URL}/rest/v1/advisor_student_assignments",
        headers=_server_headers(),
        json={
            "advisor_user_id": advisor_id,
            "student_user_id": student_id,
            "university_id": university_id,
            "is_active": True,
            "authority_source": "P8_2B_LOCAL_TEST",
            "authority_version": "v1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()[0]["id"]


def _student_entry(student_id: str, university_id: str, **changes: object):
    values: dict[str, object] = {
        "ledger_entry_id": str(uuid4()),
        "decision_type": DecisionType.MOCK_REGISTRATION_SUBMIT,
        "materiality_class": MaterialityClass.LEDGER_REQUIRED,
        "actor_class": ActorClass.STUDENT,
        "actor_id": student_id,
        "subject_scope_type": SubjectScopeType.STUDENT_INDIVIDUAL,
        "subject_scope_id": f"student-scope:{student_id}",
        "university_id": university_id,
        "student_user_id": student_id,
        "source_engine": "mock_registration",
        "source_engine_version": "6.5",
        "policy_version": "P8.1",
        "source_versions": ("catalog:plan12:v1", "policy:p8.1"),
        "input_state_reference": None,
        "scenario_id": None,
        "decision_status": DecisionStatus.VALIDATED,
        "outcome_reference": "قرار-اختبار-موثق",
        "evidence_references": (
            EvidenceReference("policy", "P8.1", "v1", "section-5", "https://local.invalid/policy"),
            EvidenceReference("catalog", "خطة-12", "v1", None, None),
        ),
        "domain_trace_reference": None,
        "provenance_class": ProvenanceClass.AUTHORITATIVE_TRANSACTION,
        "created_at": datetime.now(timezone.utc).replace(microsecond=123456),
        "redaction_profile": RedactionProfile.STUDENT_SAFE,
        "previous_entry_hash": None,
        "supersedes_entry_id": None,
        "replay_status": ReplayStatus.REPLAYABLE_EXACT,
        "limitations": ("SOURCE_SNAPSHOT_REQUIRED",),
    }
    values.update(changes)
    return create_canonical_ledger_entry(**values)


def _advisor_entry(advisor_id: str, student_id: str, university_id: str):
    return _student_entry(
        student_id,
        university_id,
        decision_type=DecisionType.ADVISOR_FORMAL_GUIDANCE,
        actor_class=ActorClass.ACADEMIC_ADVISOR,
        actor_id=advisor_id,
        redaction_profile=RedactionProfile.ADVISOR_SAFE,
        provenance_class=ProvenanceClass.GOVERNED_ASSESSMENT,
        scenario_id="advisor-formal-guidance",
    )


def _service(client: httpx.AsyncClient) -> tuple[
    DecisionTraceService, SupabaseDecisionTraceRepository
]:
    traces = SupabaseDecisionTraceRepository(URL or "", SERVER_KEY or "", client)
    assignments = SupabaseAdvisorAssignmentRepository(URL or "", SERVER_KEY or "", client)
    return DecisionTraceService(traces, assignments, AdvisorAuthorizationService(assignments)), traces


def _assert_denied(response: httpx.Response) -> None:
    assert response.status_code in {401, 403, 404}, response.text


@pytest.mark.anyio
async def test_p8_2b_local_canonical_round_trip_conservative_student_view_and_direct_evidence_denial() -> None:
    with httpx.Client(timeout=30) as raw:
        plan_id, university_id = _plan_scope(raw)
        owner_id, owner_token = _create_user(raw, "owner")
        other_id, _ = _create_user(raw, "other")
        _create_profile(raw, owner_id, plan_id)
        _create_profile(raw, other_id, plan_id)
        entry = _student_entry(owner_id, university_id)

        async with httpx.AsyncClient(timeout=30) as client:
            service, repository = _service(client)
            # Repository use models a future internal deterministic-event adapter;
            # user-facing append_student deliberately rejects supplied envelopes.
            assert await repository.append(entry) == entry.ledger_entry_id
            with pytest.raises(DecisionTracePersistenceError) as duplicate:
                await repository.append(entry)
            assert duplicate.value.code is DecisionTraceErrorCode.PERSISTENCE_CONFLICT
            restored = await repository.load_student_entry(
                ledger_entry_id=entry.ledger_entry_id,
                student_user_id=owner_id,
                university_id=university_id,
            )
            assert restored is not None
            assert canonical_ledger_payload(restored) == canonical_ledger_payload(entry)
            assert restored.integrity_hash == entry.integrity_hash
            assert restored.evidence_references == entry.evidence_references

            view = await service.get_student_trace(CurrentUser(owner_id), entry.ledger_entry_id)
            assert view.metadata.ledger_entry_id == entry.ledger_entry_id
            assert view.metadata.created_at.microsecond == 123456
            assert not hasattr(view.metadata, "student_user_id")
            assert not hasattr(view.metadata, "subject_scope_id")
            assert not hasattr(view.metadata, "limitations")
            assert not hasattr(view, "evidence_references")

            with pytest.raises(DecisionTracePersistenceError) as other:
                await service.get_student_trace(CurrentUser(other_id), entry.ledger_entry_id)
            assert other.value.code is DecisionTraceErrorCode.NOT_FOUND

        headers = _user_headers(owner_token)
        direct_evidence = (
            raw.post(
                f"{URL}/rest/v1/decision_trace_evidence",
                headers=headers,
                json={
                    "ledger_entry_id": entry.ledger_entry_id,
                    "evidence_position": 99,
                    "source": "forged",
                    "identifier": "forged",
                    "version": "v1",
                },
            ),
            raw.patch(
                f"{URL}/rest/v1/decision_trace_evidence",
                headers=headers,
                params={"ledger_entry_id": f"eq.{entry.ledger_entry_id}"},
                json={"source": "tampered"},
            ),
            raw.delete(
                f"{URL}/rest/v1/decision_trace_evidence",
                headers=headers,
                params={"ledger_entry_id": f"eq.{entry.ledger_entry_id}"},
            ),
            raw.post(
                f"{URL}/rest/v1/rpc/append_decision_trace_ledger",
                headers=headers,
                json={"p_entry": {}, "p_evidence": []},
            ),
        )
        for response in direct_evidence:
            _assert_denied(response)
        for table in ("decision_trace_ledger", "decision_trace_evidence"):
            _assert_denied(
                raw.get(
                    f"{URL}/rest/v1/{table}",
                    headers={"apikey": ANON_KEY or ""},
                    params={"select": "*"},
                )
            )


@pytest.mark.anyio
async def test_p8_2b_local_rejects_all_user_supplied_authoritative_envelopes_before_append() -> None:
    with httpx.Client(timeout=30) as raw:
        plan_id, university_id = _plan_scope(raw)
        owner_id, _ = _create_user(raw, "forgery-owner")
        other_id, _ = _create_user(raw, "forgery-other")
        _create_profile(raw, owner_id, plan_id)
        _create_profile(raw, other_id, plan_id)
        foreign = raw.post(
            f"{URL}/rest/v1/universities",
            headers=_server_headers(),
            json={"name_ar": f"جامعة P8 {uuid4()}", "name_en": f"P8 foreign {uuid4()}", "country": "JO"},
        )
        foreign.raise_for_status()
        foreign_university_id = foreign.json()[0]["id"]

        valid = _student_entry(owner_id, university_id)
        forged_hash = replace(valid, integrity_hash="a" * 64)
        tampered = replace(valid, outcome_reference="tampered-after-hash")
        spoofed_student = _student_entry(other_id, university_id)
        spoofed_university = _student_entry(owner_id, foreign_university_id)
        spoofed_actor = _student_entry(
            owner_id, university_id, actor_class=ActorClass.ACADEMIC_ADVISOR
        )
        unsupported = _student_entry(
            owner_id,
            university_id,
            decision_type=DecisionType.GET_PROGRESS,
            materiality_class=MaterialityClass.DOMAIN_TRACE_ONLY,
        )

        async with httpx.AsyncClient(timeout=30) as client:
            service, _ = _service(client)
            for candidate in (
                forged_hash,
                tampered,
                spoofed_student,
                spoofed_university,
                spoofed_actor,
                unsupported,
            ):
                with pytest.raises(DecisionTracePersistenceError) as rejected:
                    await service.append_student(CurrentUser(owner_id), candidate)
                assert rejected.value.code is DecisionTraceErrorCode.UNSUPPORTED_APPEND_AUTHORITY

        for entry_id in (
            forged_hash.ledger_entry_id,
            tampered.ledger_entry_id,
            spoofed_student.ledger_entry_id,
            spoofed_university.ledger_entry_id,
            spoofed_actor.ledger_entry_id,
            unsupported.ledger_entry_id,
        ):
            rows = raw.get(
                f"{URL}/rest/v1/decision_trace_ledger",
                headers=_server_headers(),
                params={"select": "ledger_entry_id", "ledger_entry_id": f"eq.{entry_id}"},
            )
            rows.raise_for_status()
            assert rows.json() == []


@pytest.mark.anyio
async def test_p8_2b_local_advisor_assignment_revocation_membership_and_cross_tenant_denial() -> None:
    with httpx.Client(timeout=30) as raw:
        plan_id, university_id = _plan_scope(raw)
        student_id, _ = _create_user(raw, "advisor-student")
        advisor_id, _ = _create_user(raw, "assigned-advisor")
        unassigned_id, _ = _create_user(raw, "unassigned-advisor")
        foreign_advisor_id, _ = _create_user(raw, "foreign-advisor")
        _create_profile(raw, student_id, plan_id)
        _create_profile(raw, advisor_id, plan_id)
        _create_profile(raw, unassigned_id, plan_id)
        _create_profile(raw, foreign_advisor_id, plan_id)
        _membership(raw, advisor_id, university_id, "ACADEMIC_ADVISOR")
        _membership(raw, unassigned_id, university_id, "ACADEMIC_ADVISOR")
        assignment_id = _assignment(raw, advisor_id, student_id, university_id)

        foreign = raw.post(
            f"{URL}/rest/v1/universities",
            headers=_server_headers(),
            json={"name_ar": f"جامعة بعيدة {uuid4()}", "name_en": f"foreign {uuid4()}", "country": "JO"},
        )
        foreign.raise_for_status()
        _membership(raw, foreign_advisor_id, foreign.json()[0]["id"], "ACADEMIC_ADVISOR")

        async with httpx.AsyncClient(timeout=30) as client:
            service, repository = _service(client)
            student_entry = _student_entry(student_id, university_id)
            assert await repository.append(student_entry) == student_entry.ledger_entry_id
            assert (
                await service.get_advisor_trace(
                    CurrentUser(advisor_id), student_id, student_entry.ledger_entry_id
                )
            ).metadata.ledger_entry_id == student_entry.ledger_entry_id
            advisor_entry = _advisor_entry(advisor_id, student_id, university_id)
            assert await repository.append(advisor_entry) == advisor_entry.ledger_entry_id
            with pytest.raises(DecisionTracePersistenceError) as student_restricted:
                await service.get_student_trace(CurrentUser(student_id), advisor_entry.ledger_entry_id)
            assert student_restricted.value.code is DecisionTraceErrorCode.ACCESS_DENIED

            for advisor in (unassigned_id, foreign_advisor_id):
                with pytest.raises(DecisionTracePersistenceError) as denied:
                    await service.get_advisor_trace(
                        CurrentUser(advisor), student_id, student_entry.ledger_entry_id
                    )
                assert denied.value.code is DecisionTraceErrorCode.ACCESS_DENIED
                with pytest.raises(DecisionTracePersistenceError) as append_denied:
                    await service.append_advisor(
                        CurrentUser(advisor), student_id, _advisor_entry(advisor, student_id, university_id)
                    )
                assert append_denied.value.code is DecisionTraceErrorCode.UNSUPPORTED_APPEND_AUTHORITY

            deactivated = raw.patch(
                f"{URL}/rest/v1/advisor_student_assignments",
                headers=_server_headers(),
                params={"id": f"eq.{assignment_id}"},
                json={"is_active": False},
            )
            assert deactivated.status_code == 200, deactivated.text
            with pytest.raises(DecisionTracePersistenceError) as revoked:
                await service.get_advisor_trace(
                    CurrentUser(advisor_id), student_id, student_entry.ledger_entry_id
                )
            assert revoked.value.code is DecisionTraceErrorCode.ACCESS_DENIED

            reactivated = raw.patch(
                f"{URL}/rest/v1/advisor_student_assignments",
                headers=_server_headers(),
                params={"id": f"eq.{assignment_id}"},
                json={"is_active": True},
            )
            assert reactivated.status_code == 200, reactivated.text
            membership_rows = raw.get(
                f"{URL}/rest/v1/institutional_memberships",
                headers=_server_headers(),
                params={"select": "id", "subject_user_id": f"eq.{advisor_id}", "role": "eq.ACADEMIC_ADVISOR"},
            )
            membership_rows.raise_for_status()
            membership_id = membership_rows.json()[0]["id"]
            inactive = raw.patch(
                f"{URL}/rest/v1/institutional_memberships",
                headers=_server_headers(),
                params={"id": f"eq.{membership_id}"},
                json={"active": False},
            )
            assert inactive.status_code == 200, inactive.text
            with pytest.raises(DecisionTracePersistenceError) as inactive_denied:
                await service.get_advisor_trace(
                    CurrentUser(advisor_id), student_id, student_entry.ledger_entry_id
                )
            assert inactive_denied.value.code is DecisionTraceErrorCode.ACCESS_DENIED

            with pytest.raises(DecisionTracePersistenceError) as analyst:
                await service.get_institutional_individual_trace(
                    CurrentUser(str(uuid4())), student_entry.ledger_entry_id
                )
            assert analyst.value.code is DecisionTraceErrorCode.ACCESS_DENIED


@pytest.mark.anyio
async def test_p8_2b_local_preserves_python_unicode_evidence_order_by_stored_position() -> None:
    with httpx.Client(timeout=30) as raw:
        plan_id, university_id = _plan_scope(raw)
        student_id, _ = _create_user(raw, "unicode")
        _create_profile(raw, student_id, plan_id)
        entry = _student_entry(
            student_id,
            university_id,
            evidence_references=(
                EvidenceReference("source", "😀", "v1"),
                EvidenceReference("source", "漢", "v1"),
                EvidenceReference("source", "é", "v1"),
                EvidenceReference("source", "a", "v1"),
            ),
        )

        async with httpx.AsyncClient(timeout=30) as client:
            _, repository = _service(client)
            assert await repository.append(entry) == entry.ledger_entry_id
            restored = await repository.load_student_entry(
                ledger_entry_id=entry.ledger_entry_id,
                student_user_id=student_id,
                university_id=university_id,
            )
        assert restored is not None
        assert [reference.identifier for reference in restored.evidence_references] == [
            "a",
            "é",
            "漢",
            "😀",
        ]
        assert canonical_ledger_payload(restored) == canonical_ledger_payload(entry)


@pytest.mark.anyio
async def test_p8_2b_local_atomic_rollback_and_canonical_supersession_concurrency() -> None:
    with httpx.Client(timeout=30) as raw:
        plan_id, university_id = _plan_scope(raw)
        student_id, _ = _create_user(raw, "supersession")
        _create_profile(raw, student_id, plan_id)

        async with httpx.AsyncClient(timeout=30) as client:
            _, repository = _service(client)
            predecessor = _student_entry(student_id, university_id)
            assert await repository.append(predecessor) == predecessor.ledger_entry_id

            malformed_seed = _student_entry(student_id, university_id)
            duplicate_evidence = replace(
                malformed_seed,
                evidence_references=(
                    malformed_seed.evidence_references[0],
                    malformed_seed.evidence_references[0],
                ),
                integrity_hash="",
            )
            duplicate_evidence = replace(
                duplicate_evidence,
                integrity_hash=calculate_integrity_hash(duplicate_evidence),
            )
            with pytest.raises(DecisionTracePersistenceError) as atomic:
                await repository.append(duplicate_evidence)
            assert atomic.value.code is DecisionTraceErrorCode.PERSISTENCE_CONFLICT
            absent = await repository.load_student_entry(
                ledger_entry_id=duplicate_evidence.ledger_entry_id,
                student_user_id=student_id,
                university_id=university_id,
            )
            assert absent is None

            first = create_superseding_entry(
                predecessor,
                ledger_entry_id=str(uuid4()),
                outcome_reference="canonical-successor-one",
            )
            second = create_superseding_entry(
                predecessor,
                ledger_entry_id=str(uuid4()),
                outcome_reference="canonical-successor-two",
            )
            results = await asyncio.gather(
                repository.append(first),
                repository.append(second),
                return_exceptions=True,
            )
            assert sum(isinstance(result, str) for result in results) == 1
            conflicts = [result for result in results if isinstance(result, Exception)]
            assert len(conflicts) == 1
            assert isinstance(conflicts[0], DecisionTracePersistenceError)
            assert conflicts[0].code is DecisionTraceErrorCode.PERSISTENCE_CONFLICT
            reloaded_predecessor = await repository.load_student_entry(
                ledger_entry_id=predecessor.ledger_entry_id,
                student_user_id=student_id,
                university_id=university_id,
            )
            assert reloaded_predecessor is not None
            assert reloaded_predecessor.integrity_hash == predecessor.integrity_hash
            assert reloaded_predecessor.outcome_reference == predecessor.outcome_reference
