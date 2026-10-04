"""Real local Supabase integration and adversarial security tests for P8 Slice 2C outbox processor."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
import uuid
from datetime import datetime, timezone

import httpx
import pytest

from app.decision_trace import (
    CanonicalLedgerEntry,
    canonical_ledger_payload,
    verify_integrity_hash,
)
from app.decision_trace_persistence import (
    ClaimedOutboxEvent,
    DecisionTraceErrorCode,
    DecisionTraceOutboxProcessor,
    DecisionTracePersistenceError,
    OutboxErrorClass,
    OutboxProcessingStatus,
    SupabaseDecisionTraceOutboxRepository,
    SupabaseDecisionTraceRepository,
)


URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
SERVER_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")
ANON_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_ANON_KEY")
pytestmark = pytest.mark.skipif(
    not all((URL, SERVER_KEY, ANON_KEY)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values",
)


def _admin_headers() -> dict[str, str]:
    return {
        "apikey": SERVER_KEY or "",
        "Authorization": f"Bearer {SERVER_KEY or ''}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _anon_headers() -> dict[str, str]:
    return {
        "apikey": ANON_KEY or "",
        "Authorization": f"Bearer {ANON_KEY or ''}",
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


def _psql(sql: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            "docker", "exec", "supabase_db_Morshidi", "psql",
            "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-At", "-c", sql,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


@pytest.fixture(autouse=True)
def clean_outbox_tables():
    _psql("truncate table public.decision_trace_outbox, public.decision_trace_evidence, public.decision_trace_ledger cascade;")
    yield


def _create_user(client: httpx.Client, run_id: uuid.UUID) -> tuple[str, str]:
    password = f"Outbox-{run_id}-Aa1!"
    user_tag = uuid.uuid4().hex[:8]
    email = f"outbox-p8-{run_id}-{user_tag}@local.test"
    response = client.post(
        f"{URL}/auth/v1/admin/users",
        headers=_admin_headers(),
        json={"email": email, "password": password, "email_confirm": True},
    )
    response.raise_for_status()
    signed_in = client.post(
        f"{URL}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": ANON_KEY or "", "Content-Type": "application/json"},
        json={"email": email, "password": password},
    )
    signed_in.raise_for_status()
    return response.json()["id"], signed_in.json()["access_token"]


def _context(client: httpx.Client, run_id: uuid.UUID) -> tuple[str, str, str, list[str], list[str], str]:
    plans = client.get(
        f"{URL}/rest/v1/study_plans",
        headers=_admin_headers(),
        params={"select": "id,major_id,majors(faculties(university_id))", "limit": "1"},
    )
    plans.raise_for_status()
    plan = plans.json()[0]
    courses = client.get(
        f"{URL}/rest/v1/study_plan_courses",
        headers=_admin_headers(),
        params={
            "select": "course_id,courses(course_code)",
            "study_plan_id": f"eq.{plan['id']}",
            "active": "eq.true",
            "order": "display_order.asc",
            "limit": "2",
        },
    )
    courses.raise_for_status()
    pairs = sorted(
        ((row["courses"]["course_code"], row["course_id"]) for row in courses.json()),
        key=lambda item: item[0],
    )
    assert len(pairs) == 2
    university_id = plan["majors"]["faculties"]["university_id"]
    period = client.post(
        f"{URL}/rest/v1/mock_registration_target_periods",
        headers=_admin_headers(),
        json={
            "university_id": university_id,
            "provider_namespace": f"outbox-p8-{run_id}",
            "period_key": f"outbox-p8-period-{uuid.uuid4()}",
            "period_class": "SYNTHETIC_SANDBOX_PERIOD",
            "source_version": "outbox-period:v1",
        },
    )
    period.raise_for_status()
    return (
        plan["id"],
        plan["major_id"],
        university_id,
        [pair[1] for pair in pairs],
        [pair[0] for pair in pairs],
        period.json()[0]["id"],
    )


def _payload(
    *,
    intent_id: str,
    owner_id: str,
    university_id: str,
    major_id: str,
    plan_id: str,
    period_id: str,
    expected: int | None,
    fingerprint: str,
    course_ids: list[str],
    course_codes: list[str],
) -> dict[str, object]:
    return {
        "p_intent_id": intent_id,
        "p_owner_user_id": owner_id,
        "p_university_id": university_id,
        "p_major_id": major_id,
        "p_study_plan_id": plan_id,
        "p_study_plan_version": "outbox-plan:v1",
        "p_target_period_id": period_id,
        "p_expected_current_revision": expected,
        "p_lifecycle_status": "SUBMITTED",
        "p_validation_status": "VALID",
        "p_content_fingerprint": fingerprint,
        "p_intent_provenance": "SYNTHETIC_SANDBOX_INTENT",
        "p_intent_source_version": "outbox-intent:v1",
        "p_validation_reason_codes": [],
        "p_catalog_source_versions": ["catalog:v1"],
        "p_prerequisite_source_versions": ["prereq:v1"],
        "p_progress_state_version": "progress:v1",
        "p_progress_state_reference": "progress-ref:1",
        "p_phase5_policy_version": "phase5:v1",
        "p_phase6_policy_version": "phase6:v1",
        "p_p6_contract_version": "1.0",
        "p_target_period_source_version": "outbox-period:v1",
        "p_transparency_notice_version": "notice:v1",
        "p_actor_class": "STUDENT_AUTHENTICATED",
        "p_course_ids": course_ids,
        "p_course_codes": course_codes,
    }


def _create_p6_outbox_event(client: httpx.Client, run_id: uuid.UUID) -> tuple[str, str, str]:
    """Create real P6 revision + outbox event; returns (revision_id, owner_id, university_id)."""
    owner_id, _ = _create_user(client, run_id)
    plan_id, major_id, university_id, course_ids, course_codes, period_id = _context(client, run_id)
    payload = _payload(
        intent_id=str(uuid.uuid4()),
        owner_id=owner_id,
        university_id=university_id,
        major_id=major_id,
        plan_id=plan_id,
        period_id=period_id,
        expected=None,
        fingerprint=uuid.uuid4().hex + uuid.uuid4().hex,
        course_ids=[course_ids[0]],
        course_codes=[course_codes[0]],
    )
    res = client.post(
        f"{URL}/rest/v1/rpc/persist_mock_registration_revision",
        headers=_admin_headers(),
        json=payload,
    )
    res.raise_for_status()
    revision_id = res.json()[0]["persisted_revision_id"]
    return revision_id, owner_id, university_id


# =========================================================================
# MANDATORY SECURITY TESTS 1 - 4: Access Control & Direct Bypass Prevention
# =========================================================================

def test_security_01_anon_cannot_claim_events() -> None:
    with httpx.Client(timeout=10) as client:
        res = client.post(
            f"{URL}/rest/v1/rpc/claim_decision_trace_outbox_events",
            headers=_anon_headers(),
            json={"p_worker_id": "anon-worker", "p_batch_size": 5},
        )
        assert res.status_code in (401, 403, 404)


def test_security_02_authenticated_cannot_claim_events() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=10) as client:
        _, token = _create_user(client, run_id)
        res = client.post(
            f"{URL}/rest/v1/rpc/claim_decision_trace_outbox_events",
            headers=_user_headers(token),
            json={"p_worker_id": "user-worker", "p_batch_size": 5},
        )
        assert res.status_code in (401, 403, 404)


def test_security_03_anon_and_authenticated_cannot_complete_events() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=10) as client:
        _, token = _create_user(client, run_id)
        anon_res = client.post(
            f"{URL}/rest/v1/rpc/complete_decision_trace_outbox_event",
            headers=_anon_headers(),
            json={
                "p_event_id": str(uuid.uuid4()),
                "p_claim_token": "token",
                "p_completed_ledger_integrity_hash": "a" * 64,
            },
        )
        assert anon_res.status_code in (401, 403, 404)

        auth_res = client.post(
            f"{URL}/rest/v1/rpc/complete_decision_trace_outbox_event",
            headers=_user_headers(token),
            json={
                "p_event_id": str(uuid.uuid4()),
                "p_claim_token": "token",
                "p_completed_ledger_integrity_hash": "a" * 64,
            },
        )
        assert auth_res.status_code in (401, 403, 404)


def test_security_04_service_role_cannot_bypass_rpc_via_direct_table_access() -> None:
    with httpx.Client(timeout=10) as client:
        # Direct SELECT fails (revoked)
        sel_res = client.get(
            f"{URL}/rest/v1/decision_trace_outbox",
            headers=_admin_headers(),
            params={"limit": "1"},
        )
        assert sel_res.status_code in (401, 403) or "permission denied" in sel_res.text.lower()

        # Direct UPDATE fails (revoked)
        upd_res = client.patch(
            f"{URL}/rest/v1/decision_trace_outbox",
            headers=_admin_headers(),
            params={"event_id": f"eq.{uuid.uuid4()}"},
            json={"processing_state": "COMPLETED"},
        )
        assert upd_res.status_code in (401, 403) or "permission denied" in upd_res.text.lower()


# =========================================================================
# MANDATORY CONCURRENCY & LEASE TESTS 5 - 9
# =========================================================================

@pytest.mark.anyio
async def test_security_05_worker_can_claim_only_bounded_number() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        # Create 3 outbox events
        rev1, _, uni_id = _create_p6_outbox_event(client, run_id)
        rev2, _, _ = _create_p6_outbox_event(client, run_id)
        rev3, _, _ = _create_p6_outbox_event(client, run_id)

    outbox_repo = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
    try:
        # Claim with batch_size = 2 within this university
        claimed = await outbox_repo.claim_events(
            worker_id="bounded-worker",
            batch_size=2,
            university_id=uuid.UUID(uni_id),
        )
        assert len(claimed) == 2
    finally:
        await outbox_repo.close()


def test_security_06_two_concurrent_workers_do_not_receive_same_event() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        uni_id = None
        for _ in range(4):
            _, _, u = _create_p6_outbox_event(client, run_id)
            uni_id = u

    def claim_batch(worker_id: str) -> list[str]:
        with httpx.Client(timeout=10) as c:
            res = c.post(
                f"{URL}/rest/v1/rpc/claim_decision_trace_outbox_events",
                headers=_admin_headers(),
                json={
                    "p_worker_id": worker_id,
                    "p_batch_size": 2,
                    "p_lease_seconds": 60,
                    "p_university_id": uni_id,
                },
            )
            res.raise_for_status()
            return [row["event_id"] for row in res.json()]

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(claim_batch, "concurrent-worker-1")
        f2 = executor.submit(claim_batch, "concurrent-worker-2")
        batch1 = set(f1.result())
        batch2 = set(f2.result())

    # Disjoint batches: FOR UPDATE SKIP LOCKED ensures no collision
    overlap = batch1.intersection(batch2)
    assert len(overlap) == 0


@pytest.mark.anyio
async def test_security_07_expired_claim_can_be_safely_reclaimed() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        rev_id, _, uni_id = _create_p6_outbox_event(client, run_id)

    outbox_repo = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
    try:
        # Worker 1 claims with short lease (10 seconds)
        claimed1 = await outbox_repo.claim_events(
            worker_id="worker-w1",
            batch_size=10,
            lease_seconds=10,
            university_id=uuid.UUID(uni_id),
        )
        target = next((item for item in claimed1 if str(item.event_id) == rev_id), None)
        assert target is not None

        # Expire the lease manually in PostgreSQL
        _psql(f"update public.decision_trace_outbox set lease_expires_at = now() - interval '5 seconds' where event_id = '{rev_id}'::uuid;")

        # Worker 2 claims: should safely reclaim the expired event
        claimed2 = await outbox_repo.claim_events(
            worker_id="worker-w2",
            batch_size=10,
            lease_seconds=60,
            university_id=uuid.UUID(uni_id),
        )
        reclaimed = next((item for item in claimed2 if str(item.event_id) == rev_id), None)
        assert reclaimed is not None
        assert reclaimed.claim_token != target.claim_token
        assert reclaimed.attempt_count > target.attempt_count
    finally:
        await outbox_repo.close()


@pytest.mark.anyio
async def test_security_08_stale_claim_token_cannot_complete_or_release_newer_claim() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        rev_id, _, uni_id = _create_p6_outbox_event(client, run_id)

    outbox_repo = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
    try:
        # Worker A claims
        claimed_a = await outbox_repo.claim_events(
            worker_id="worker-a",
            batch_size=10,
            lease_seconds=10,
            university_id=uuid.UUID(uni_id),
        )
        item_a = next(item for item in claimed_a if str(item.event_id) == rev_id)

        # Lease expires
        _psql(f"update public.decision_trace_outbox set lease_expires_at = now() - interval '5 seconds' where event_id = '{rev_id}'::uuid;")

        # Worker B claims with new token
        claimed_b = await outbox_repo.claim_events(
            worker_id="worker-b",
            batch_size=10,
            lease_seconds=60,
            university_id=uuid.UUID(uni_id),
        )
        item_b = next(item for item in claimed_b if str(item.event_id) == rev_id)
        assert item_b.claim_token != item_a.claim_token

        # Stale Worker A attempts completion with old claim token -> rejected
        with pytest.raises(DecisionTracePersistenceError) as exc_complete:
            await outbox_repo.complete_event(
                event_id=item_a.event_id,
                claim_token=item_a.claim_token,
                completed_ledger_integrity_hash="a" * 64,
            )
        assert exc_complete.value.code == DecisionTraceErrorCode.STALE_CLAIM

        # Stale Worker A attempts release with old claim token -> rejected
        with pytest.raises(DecisionTracePersistenceError) as exc_release:
            await outbox_repo.release_event(
                event_id=item_a.event_id,
                claim_token=item_a.claim_token,
                error_class="TRANSIENT_P8_UNAVAILABLE",
            )
        assert exc_release.value.code == DecisionTraceErrorCode.STALE_CLAIM
    finally:
        await outbox_repo.close()


@pytest.mark.anyio
async def test_security_09_completed_event_cannot_be_reclaimed() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        rev_id, _, _ = _create_p6_outbox_event(client, run_id)

    outbox_repo = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
    ledger_repo = SupabaseDecisionTraceRepository(URL, SERVER_KEY)
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)
    try:
        # Process and complete
        summary = await processor.process_batch(worker_id="worker-c", batch_size=10)
        completed_item = next((r for r in summary.results if str(r.event_id) == rev_id), None)
        assert completed_item is not None
        assert completed_item.status == OutboxProcessingStatus.COMPLETED

        # Attempt to claim again -> completed event is never claimed
        next_claim = await outbox_repo.claim_events(worker_id="worker-c2", batch_size=10)
        assert not any(str(item.event_id) == rev_id for item in next_claim)
    finally:
        await outbox_repo.close()
        await ledger_repo.close()


# =========================================================================
# MANDATORY IMMUTABILITY & SCOPE TESTS 10 - 11, 17
# =========================================================================

def test_security_10_source_payload_cannot_be_mutated() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        rev_id, _, _ = _create_p6_outbox_event(client, run_id)

    # Attempt direct SQL update to event_type
    res = _psql(
        f"update public.decision_trace_outbox set event_type = 'TAMPERED' where event_id = '{rev_id}'::uuid;",
        check=False,
    )
    assert res.returncode != 0
    assert "Decision trace outbox event source is immutable" in res.stderr

    # Attempt direct SQL update to source_snapshot
    res_snap = _psql(
        f"update public.decision_trace_outbox set source_snapshot = '{{\"tampered\": true}}'::jsonb where event_id = '{rev_id}'::uuid;",
        check=False,
    )
    assert res_snap.returncode != 0
    assert "Decision trace outbox event source is immutable" in res_snap.stderr


@pytest.mark.anyio
async def test_security_11_cross_university_scope_cannot_leak() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        rev_id, _, uni_id = _create_p6_outbox_event(client, run_id)

    other_uni = uuid.uuid4()
    outbox_repo = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
    try:
        # Claim with a different university_id
        claimed = await outbox_repo.claim_events(
            worker_id="tenant-worker",
            batch_size=10,
            university_id=other_uni,
        )
        # Event belonging to uni_id must NOT be in the claimed batch
        assert not any(str(item.event_id) == rev_id for item in claimed)

        # Claim with the matching university_id
        matching = await outbox_repo.claim_events(
            worker_id="tenant-worker-2",
            batch_size=10,
            university_id=uuid.UUID(uni_id),
        )
        assert any(str(item.event_id) == rev_id for item in matching)
    finally:
        await outbox_repo.close()


def test_security_17_no_delete_path_exists_for_outbox_history() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        rev_id, _, _ = _create_p6_outbox_event(client, run_id)

    res = _psql(f"delete from public.decision_trace_outbox where event_id = '{rev_id}'::uuid;", check=False)
    assert res.returncode != 0
    assert "Decision trace outbox events are durable and cannot be deleted" in res.stderr


# =========================================================================
# MANDATORY INTEGRITY & PROCESSOR TESTS 12 - 16
# =========================================================================

@pytest.mark.anyio
async def test_security_12_malformed_event_fails_closed() -> None:
    # Event with missing parent_revision_data in repository
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        rev_id, _, _ = _create_p6_outbox_event(client, run_id)

    outbox_repo = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
    try:
        claimed = await outbox_repo.claim_events(worker_id="malform-worker", batch_size=10)
        item = next(c for c in claimed if str(c.event_id) == rev_id)

        # Tamper projection's outbox_required to False
        tampered_proj = item.projection.__class__(
            revision=item.projection.revision,
            outbox_required=False,
            outbox_event=item.projection.outbox_event,
        )
        tampered_event = ClaimedOutboxEvent(
            event_id=item.event_id,
            revision_id=item.revision_id,
            claim_token=item.claim_token,
            attempt_count=item.attempt_count,
            lease_expires_at=item.lease_expires_at,
            projection=tampered_proj,
        )

        ledger_repo = SupabaseDecisionTraceRepository(URL, SERVER_KEY)
        processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)
        result = await processor.process_event(tampered_event)

        assert result.status == OutboxProcessingStatus.PERMANENT_FAILURE
        assert result.error_code == OutboxErrorClass.CONTRACT_FAILURE.value

        # Check DB outbox status is PERMANENT_FAILURE
        state = _psql(f"select processing_state from public.decision_trace_outbox where event_id = '{rev_id}'::uuid;").stdout.strip()
        assert state == "PERMANENT_FAILURE"

        # Check no ledger entry was created
        ledger_count = _psql(f"select count(*) from public.decision_trace_ledger where ledger_entry_id = '{rev_id}';").stdout.strip()
        assert ledger_count == "0"
        await ledger_repo.close()
    finally:
        await outbox_repo.close()


@pytest.mark.anyio
async def test_security_13_mapper_integrity_failure_does_not_create_ledger_entry() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        rev_id, _, _ = _create_p6_outbox_event(client, run_id)

    outbox_repo = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
    ledger_repo = SupabaseDecisionTraceRepository(URL, SERVER_KEY)
    try:
        claimed = await outbox_repo.claim_events(worker_id="mapper-fail-worker", batch_size=10)
        item = next(c for c in claimed if str(c.event_id) == rev_id)

        # Corrupt snapshot content_fingerprint in memory
        corrupted_event = item.projection.outbox_event.__class__(
            event_id=item.projection.outbox_event.event_id,
            revision_id=item.projection.outbox_event.revision_id,
            owner_user_id=item.projection.outbox_event.owner_user_id,
            university_id=item.projection.outbox_event.university_id,
            major_id=item.projection.outbox_event.major_id,
            study_plan_id=item.projection.outbox_event.study_plan_id,
            study_plan_version=item.projection.outbox_event.study_plan_version,
            target_period_id=item.projection.outbox_event.target_period_id,
            revision=item.projection.outbox_event.revision,
            event_type=item.projection.outbox_event.event_type,
            snapshot_contract_version=item.projection.outbox_event.snapshot_contract_version,
            source_snapshot=dict(item.projection.outbox_event.source_snapshot) | {"content_fingerprint": "0" * 64},
            processing_state="PROCESSING",
        )
        corrupted_proj = item.projection.__class__(
            revision=item.projection.revision,
            outbox_required=item.projection.outbox_required,
            outbox_event=corrupted_event,
        )
        test_item = ClaimedOutboxEvent(
            event_id=item.event_id,
            revision_id=item.revision_id,
            claim_token=item.claim_token,
            attempt_count=item.attempt_count,
            lease_expires_at=item.lease_expires_at,
            projection=corrupted_proj,
        )

        processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)
        res = await processor.process_event(test_item)
        assert res.status == OutboxProcessingStatus.PERMANENT_FAILURE

        # Ledger remains untouched
        assert _psql(f"select count(*) from public.decision_trace_ledger where ledger_entry_id = '{rev_id}';").stdout.strip() == "0"
    finally:
        await outbox_repo.close()
        await ledger_repo.close()


@pytest.mark.anyio
async def test_security_14_ledger_append_failure_does_not_mark_completed() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        rev_id, _, _ = _create_p6_outbox_event(client, run_id)

    outbox_repo = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
    # Fake ledger repo that fails append with PERSISTENCE_UNAVAILABLE
    class FailingLedgerRepo:
        async def append(self, entry: CanonicalLedgerEntry) -> str:
            raise DecisionTracePersistenceError(DecisionTraceErrorCode.PERSISTENCE_UNAVAILABLE, "simulated down")

        async def load_student_entry(self, **kwargs):
            return None

    try:
        claimed = await outbox_repo.claim_events(worker_id="fail-append-worker", batch_size=10)
        item = next(c for c in claimed if str(c.event_id) == rev_id)

        processor = DecisionTraceOutboxProcessor(outbox_repo, FailingLedgerRepo())
        res = await processor.process_event(item)

        assert res.status == OutboxProcessingStatus.TRANSIENT_RETRY
        # Outbox event must NOT be completed; it must be PENDING with error
        state = _psql(f"select processing_state from public.decision_trace_outbox where event_id = '{rev_id}'::uuid;").stdout.strip()
        assert state == "PENDING"
    finally:
        await outbox_repo.close()


@pytest.mark.anyio
async def test_security_15_successful_processing_creates_exactly_one_ledger_entry() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        rev_id, _, _ = _create_p6_outbox_event(client, run_id)

    outbox_repo = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
    ledger_repo = SupabaseDecisionTraceRepository(URL, SERVER_KEY)
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)
    try:
        claimed = await outbox_repo.claim_events(worker_id="success-worker", batch_size=10)
        item = next(c for c in claimed if str(c.event_id) == rev_id)

        res = await processor.process_event(item)
        assert res.status == OutboxProcessingStatus.COMPLETED
        assert res.ledger_entry_id == rev_id
        assert res.integrity_hash is not None

        # Ledger row exists and is exactly 1
        ledger_count = _psql(f"select count(*) from public.decision_trace_ledger where ledger_entry_id = '{rev_id}';").stdout.strip()
        assert ledger_count == "1"

        # Outbox row is marked COMPLETED with verified hash
        row_state = _psql(f"select processing_state || '|' || completed_ledger_integrity_hash from public.decision_trace_outbox where event_id = '{rev_id}'::uuid;").stdout.strip()
        assert row_state == f"COMPLETED|{res.integrity_hash}"
    finally:
        await outbox_repo.close()
        await ledger_repo.close()


@pytest.mark.anyio
async def test_security_16_retry_after_ambiguous_failure_remains_idempotent() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        rev_id, _, _ = _create_p6_outbox_event(client, run_id)

    outbox_repo = SupabaseDecisionTraceOutboxRepository(URL, SERVER_KEY)
    ledger_repo = SupabaseDecisionTraceRepository(URL, SERVER_KEY)
    processor = DecisionTraceOutboxProcessor(outbox_repo, ledger_repo)
    try:
        # Step 1: Claim and append, but simulate crash right before outbox complete
        claimed = await outbox_repo.claim_events(worker_id="crash-worker-1", batch_size=10)
        item = next(c for c in claimed if str(c.event_id) == rev_id)

        # Manually append the entry directly through ledger_repo (simulating crash before complete)
        entry = processor._ledger_repo
        from app.decision_trace_persistence.p6_outbox_mapper import map_verified_mock_registration_submit
        canonical = map_verified_mock_registration_submit(item.projection)
        appended_id = await ledger_repo.append(canonical)
        assert appended_id == rev_id

        # Release or expire lease
        _psql(f"update public.decision_trace_outbox set lease_expires_at = now() - interval '5 seconds' where event_id = '{rev_id}'::uuid;")

        # Step 2: Retry with Worker 2
        claimed2 = await outbox_repo.claim_events(worker_id="retry-worker-2", batch_size=10)
        item2 = next(c for c in claimed2 if str(c.event_id) == rev_id)

        res2 = await processor.process_event(item2)
        # Idempotent match detected!
        assert res2.status == OutboxProcessingStatus.IDEMPOTENT_DUPLICATE
        assert res2.ledger_entry_id == rev_id

        # Exactly 1 ledger row exists (no duplicate)
        ledger_count = _psql(f"select count(*) from public.decision_trace_ledger where ledger_entry_id = '{rev_id}';").stdout.strip()
        assert ledger_count == "1"

        # Outbox event is COMPLETED
        state = _psql(f"select processing_state from public.decision_trace_outbox where event_id = '{rev_id}'::uuid;").stdout.strip()
        assert state == "COMPLETED"
    finally:
        await outbox_repo.close()
        await ledger_repo.close()


# =========================================================================
# MANDATORY SECURITY DEFINER & SEARCH PATH TEST 18
# =========================================================================

def test_security_18_all_new_rpcs_have_correct_search_path_and_grants() -> None:
    rpcs = [
        "claim_decision_trace_outbox_events",
        "complete_decision_trace_outbox_event",
        "release_decision_trace_outbox_event",
        "fail_decision_trace_outbox_event",
    ]
    for rpc in rpcs:
        # Verify SECURITY DEFINER
        secdef = _psql(f"select prosecdef from pg_proc where proname = '{rpc}';").stdout.strip()
        assert secdef == "t", f"{rpc} must be SECURITY DEFINER"

        # Verify safe search_path = pg_catalog, public
        config = _psql(f"select array_to_string(proconfig, ',') from pg_proc where proname = '{rpc}';").stdout.strip()
        assert "search_path=pg_catalog, public" in config, f"{rpc} must have safe explicit search_path"

        # Verify permissions: EXECUTE granted to service_role, revoked from public, anon, authenticated
        grants = _psql(
            f"select grantee || ':' || privilege_type from information_schema.routine_privileges where routine_name = '{rpc}';"
        ).stdout.strip().splitlines()
        grantees = {line.split(":")[0] for line in grants if line}
        assert "service_role" in grantees or "postgres" in grantees, f"service_role must have execute on {rpc}"
        assert "anon" not in grantees, f"anon must NOT have execute on {rpc}"
        assert "authenticated" not in grantees, f"authenticated must NOT have execute on {rpc}"
        assert "PUBLIC" not in grantees, f"PUBLIC must NOT have execute on {rpc}"
