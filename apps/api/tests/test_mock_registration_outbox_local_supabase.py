"""Real local PostgreSQL evidence for the P6 transactional P8-source outbox."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import uuid
from datetime import datetime

import httpx
import pytest

from app.decision_trace import canonical_ledger_payload, verify_integrity_hash
from app.decision_trace_persistence import (
    P6DecisionTraceOutboxEvent,
    TrustedP6OutboxProjection,
    map_verified_mock_registration_submit,
)
from app.mock_registration.models import IntentLifecycle, IntentProvenance, ValidationStatus
from app.mock_registration.registries import ReasonCode
from app.mock_registration_persistence.models import PersistedIntentCourse, PersistedIntentRevision


URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
SERVER_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")
ANON_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_ANON_KEY")
pytestmark = pytest.mark.skipif(
    not all((URL, SERVER_KEY, ANON_KEY)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values",
)


def _admin_headers() -> dict[str, str]:
    return {"apikey": SERVER_KEY or "", "Authorization": f"Bearer {SERVER_KEY or ''}", "Prefer": "return=representation"}


def _user_headers(token: str) -> dict[str, str]:
    return {"apikey": ANON_KEY or "", "Authorization": f"Bearer {token}", "Prefer": "return=representation"}


def _psql(sql: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Use the verified isolated local Supabase PostgreSQL owner only for DB assertions."""
    result = subprocess.run(
        ["docker", "exec", "supabase_db_Morshidi", "psql", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
        check=False, capture_output=True, text=True,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def _create_user(client: httpx.Client, run_id: uuid.UUID) -> tuple[str, str]:
    password = f"Outbox-{run_id}-Aa1!"
    response = client.post(
        f"{URL}/auth/v1/admin/users", headers=_admin_headers(),
        json={"email": f"outbox-owner-{run_id}@local.test", "password": password, "email_confirm": True},
    )
    response.raise_for_status()
    signed_in = client.post(
        f"{URL}/auth/v1/token", params={"grant_type": "password"}, headers={"apikey": ANON_KEY or ""},
        json={"email": f"outbox-owner-{run_id}@local.test", "password": password},
    )
    signed_in.raise_for_status()
    return response.json()["id"], signed_in.json()["access_token"]


def _context(client: httpx.Client, run_id: uuid.UUID) -> tuple[str, str, str, list[str], list[str], str]:
    plans = client.get(
        f"{URL}/rest/v1/study_plans", headers=_admin_headers(),
        params={"select": "id,major_id,majors(faculties(university_id))", "limit": "1"},
    )
    plans.raise_for_status()
    plan = plans.json()[0]
    courses = client.get(
        f"{URL}/rest/v1/study_plan_courses", headers=_admin_headers(),
        params={"select": "course_id,courses(course_code)", "study_plan_id": f"eq.{plan['id']}", "active": "eq.true", "order": "display_order.asc", "limit": "2"},
    )
    courses.raise_for_status()
    pairs = sorted(((row["courses"]["course_code"], row["course_id"]) for row in courses.json()), key=lambda item: item[0])
    assert len(pairs) == 2
    university_id = plan["majors"]["faculties"]["university_id"]
    period = client.post(
        f"{URL}/rest/v1/mock_registration_target_periods", headers=_admin_headers(),
        json={
            "university_id": university_id, "provider_namespace": f"outbox-{run_id}",
            "period_key": "outbox-local-period", "period_class": "SYNTHETIC_SANDBOX_PERIOD",
            "source_version": "outbox-period:v1",
        },
    )
    period.raise_for_status()
    return plan["id"], plan["major_id"], university_id, [pair[1] for pair in pairs], [pair[0] for pair in pairs], period.json()[0]["id"]


def _payload(*, intent_id: str, owner_id: str, university_id: str, major_id: str, plan_id: str, period_id: str, expected: int | None, fingerprint: str, course_ids: list[str], course_codes: list[str]) -> dict[str, object]:
    return {
        "p_intent_id": intent_id, "p_owner_user_id": owner_id, "p_university_id": university_id,
        "p_major_id": major_id, "p_study_plan_id": plan_id, "p_study_plan_version": "outbox-plan:v1",
        "p_target_period_id": period_id, "p_expected_current_revision": expected,
        "p_lifecycle_status": "SUBMITTED", "p_validation_status": "VALID",
        "p_content_fingerprint": fingerprint, "p_intent_provenance": "SYNTHETIC_SANDBOX_INTENT",
        "p_intent_source_version": "outbox-intent:v1", "p_validation_reason_codes": [],
        "p_catalog_source_versions": ["outbox-catalog:v1"], "p_prerequisite_source_versions": ["outbox-prerequisite:v1"],
        "p_progress_state_version": "outbox-progress:v1", "p_progress_state_reference": None,
        "p_phase5_policy_version": "phase5:v1", "p_phase6_policy_version": "phase6:v1",
        "p_p6_contract_version": "1.0", "p_target_period_source_version": "outbox-period:v1",
        "p_transparency_notice_version": "outbox-notice:v1", "p_actor_class": "APPLICATION_SERVICE",
        "p_course_ids": course_ids, "p_course_codes": course_codes,
    }


def _persist(client: httpx.Client, payload: dict[str, object], headers: dict[str, str] | None = None) -> httpx.Response:
    return client.post(f"{URL}/rest/v1/rpc/persist_mock_registration_revision", headers=headers or _admin_headers(), json=payload)


def _outbox(client: httpx.Client, revision_id: str) -> dict[str, object]:
    # service_role has deliberately no outbox table grant; inspect through the local DB owner.
    result = _psql(
        "select json_build_object("
        "'event_id', event_id, 'revision_id', revision_id, 'owner_user_id', owner_user_id, "
        "'university_id', university_id, 'major_id', major_id, 'study_plan_id', study_plan_id, "
        "'study_plan_version', study_plan_version, 'target_period_id', target_period_id, "
        "'revision', revision, 'event_type', event_type, "
        "'snapshot_contract_version', snapshot_contract_version, 'processing_state', processing_state, "
        "'attempt_count', attempt_count, 'source_snapshot', source_snapshot)::text "
        f"from public.decision_trace_outbox where revision_id = '{revision_id}'::uuid;"
    )
    assert result.stdout.strip(), "expected local outbox event"
    return json.loads(result.stdout)


def _revision(revision_id: str) -> dict[str, object]:
    result = _psql(
        "select json_build_object("
        "'revision_id', revision.id, 'intent_id', revision.intent_id, "
        "'owner_user_id', revision.owner_user_id, 'university_id', revision.university_id, "
        "'major_id', revision.major_id, 'study_plan_id', revision.study_plan_id, "
        "'study_plan_version', revision.study_plan_version, 'target_period_id', revision.target_period_id, "
        "'revision', revision.revision, 'lifecycle_status', revision.lifecycle_status, "
        "'validation_status', revision.validation_status, 'content_fingerprint', revision.content_fingerprint, "
        "'intent_provenance', revision.intent_provenance, 'intent_source_version', revision.intent_source_version, "
        "'validation_reason_codes', revision.validation_reason_codes, "
        "'catalog_source_versions', revision.catalog_source_versions, "
        "'prerequisite_source_versions', revision.prerequisite_source_versions, "
        "'progress_state_version', revision.progress_state_version, "
        "'progress_state_reference', revision.progress_state_reference, "
        "'phase5_policy_version', revision.phase5_policy_version, "
        "'phase6_policy_version', revision.phase6_policy_version, "
        "'p6_contract_version', revision.p6_contract_version, "
        "'target_period_source_version', revision.target_period_source_version, "
        "'transparency_notice_version', revision.transparency_notice_version, "
        "'actor_class', revision.actor_class, 'outbox_required', revision.outbox_required, "
        "'created_at', revision.created_at, "
        "'courses', (select coalesce(json_agg(json_build_object("
        "'course_id', course.course_id, 'course_code', course.course_code, "
        "'selection_order', course.selection_order) order by course.selection_order), '[]'::json) "
        "from public.mock_registration_intent_courses course where course.revision_id = revision.id))::text "
        f"from public.mock_registration_intent_revisions revision where revision.id = '{revision_id}'::uuid;"
    )
    assert result.stdout.strip(), "expected local P6 revision"
    return json.loads(result.stdout)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _trusted_mapper_projection(revision_id: str) -> TrustedP6OutboxProjection:
    """Owner-side read is test evidence only; runtime service-role projection is blocked."""
    row = _revision(revision_id)
    revision = PersistedIntentRevision(
        revision_id=uuid.UUID(str(row["revision_id"])), intent_id=uuid.UUID(str(row["intent_id"])),
        owner_user_id=uuid.UUID(str(row["owner_user_id"])), university_id=uuid.UUID(str(row["university_id"])),
        major_id=uuid.UUID(str(row["major_id"])), study_plan_id=uuid.UUID(str(row["study_plan_id"])),
        study_plan_version=str(row["study_plan_version"]), target_period_id=uuid.UUID(str(row["target_period_id"])),
        revision=int(row["revision"]), lifecycle_status=IntentLifecycle(str(row["lifecycle_status"])),
        validation_status=ValidationStatus(str(row["validation_status"])), content_fingerprint=str(row["content_fingerprint"]),
        intent_provenance=IntentProvenance(str(row["intent_provenance"])), intent_source_version=str(row["intent_source_version"]),
        validation_reason_codes=tuple(ReasonCode(value) for value in row["validation_reason_codes"]),
        catalog_source_versions=tuple(row["catalog_source_versions"]), prerequisite_source_versions=tuple(row["prerequisite_source_versions"]),
        progress_state_version=str(row["progress_state_version"]), progress_state_reference=row["progress_state_reference"],
        phase5_policy_version=str(row["phase5_policy_version"]), phase6_policy_version=str(row["phase6_policy_version"]),
        p6_contract_version=str(row["p6_contract_version"]), target_period_source_version=str(row["target_period_source_version"]),
        transparency_notice_version=str(row["transparency_notice_version"]), transparency_acknowledged_at=_utc(str(row["created_at"])),
        actor_class=str(row["actor_class"]), created_at=_utc(str(row["created_at"])),
        courses=tuple(PersistedIntentCourse(uuid.UUID(item["course_id"]), item["course_code"], item["selection_order"]) for item in row["courses"]),
    )
    event = _outbox(client=None, revision_id=revision_id)
    return TrustedP6OutboxProjection(
        revision=revision, outbox_required=bool(row["outbox_required"]),
        outbox_event=P6DecisionTraceOutboxEvent(
            event_id=uuid.UUID(event["event_id"]), revision_id=uuid.UUID(event["revision_id"]),
            owner_user_id=uuid.UUID(event["owner_user_id"]), university_id=uuid.UUID(event["university_id"]),
            major_id=uuid.UUID(event["major_id"]), study_plan_id=uuid.UUID(event["study_plan_id"]),
            study_plan_version=str(event["study_plan_version"]), target_period_id=uuid.UUID(event["target_period_id"]),
            revision=int(event["revision"]), event_type=str(event["event_type"]),
            snapshot_contract_version=str(event["snapshot_contract_version"]), source_snapshot=event["source_snapshot"],
            processing_state=str(event["processing_state"]),
        ),
    )


def test_p6_transactional_outbox_atomicity_idempotency_security_and_snapshot() -> None:
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        owner_id, owner_token = _create_user(client, run_id)
        plan_id, major_id, university_id, course_ids, course_codes, period_id = _context(client, run_id)
        first = _payload(
            intent_id=str(uuid.uuid4()), owner_id=owner_id, university_id=university_id,
            major_id=major_id, plan_id=plan_id, period_id=period_id, expected=None,
            fingerprint="a" * 64, course_ids=[course_ids[0]], course_codes=[course_codes[0]],
        )
        inserted = _persist(client, first)
        inserted.raise_for_status()
        row = inserted.json()[0]
        assert set(row) == {"result_kind", "persisted_revision_id", "persisted_revision", "persisted_fingerprint"}
        assert row["result_kind"] == "INSERTED" and row["persisted_revision"] == 1
        revision_id = row["persisted_revision_id"]
        event = _outbox(client, revision_id)
        revision = _revision(revision_id)
        assert revision["outbox_required"] is True
        assert event["event_id"] == revision_id == event["revision_id"]
        assert event["event_type"] == "MOCK_REGISTRATION_SUBMIT"
        assert event["snapshot_contract_version"] == "1.0"
        assert event["processing_state"] == "PENDING" and event["attempt_count"] == 0
        snapshot = event["source_snapshot"]
        for key in (
            "revision_id", "intent_id", "owner_user_id", "university_id", "major_id",
            "study_plan_id", "study_plan_version", "target_period_id", "revision",
            "lifecycle_status", "validation_status", "content_fingerprint",
            "intent_provenance", "intent_source_version", "validation_reason_codes",
            "catalog_source_versions", "prerequisite_source_versions", "progress_state_version",
            "progress_state_reference", "phase5_policy_version", "phase6_policy_version",
            "p6_contract_version", "target_period_source_version",
            "transparency_notice_version", "actor_class", "courses",
        ):
            assert snapshot[key] == revision[key], key
        assert snapshot["revision_id"] == revision_id and snapshot["intent_id"] == first["p_intent_id"]
        assert snapshot["owner_user_id"] == owner_id and snapshot["university_id"] == university_id
        assert snapshot["validation_status"] == "VALID" and snapshot["content_fingerprint"] == "a" * 64
        assert snapshot["courses"] == [{"course_id": course_ids[0], "course_code": course_codes[0], "selection_order": 1}]
        assert _utc(snapshot["created_at"]) == _utc(revision["created_at"])
        assert "integrity_hash" not in snapshot and "provenance_class" not in snapshot and "evidence_references" not in snapshot

        replay = _persist(client, {**first, "p_intent_id": str(uuid.uuid4())})
        replay.raise_for_status()
        assert replay.json()[0]["result_kind"] == "IDEMPOTENT_REPLAY"
        assert replay.json()[0]["persisted_revision_id"] == revision_id
        assert _psql(f"select count(*) from public.decision_trace_outbox where revision_id = '{revision_id}'::uuid;").stdout.strip() == "1"

        concurrent = _payload(
            intent_id=str(uuid.uuid4()), owner_id=owner_id, university_id=university_id,
            major_id=major_id, plan_id=plan_id, period_id=period_id, expected=1,
            fingerprint="b" * 64, course_ids=[course_ids[1]], course_codes=[course_codes[1]],
        )
        equivalent = {**concurrent, "p_intent_id": str(uuid.uuid4())}
        def submit(value: dict[str, object]) -> str:
            with httpx.Client(timeout=30) as worker:
                response = _persist(worker, value)
                response.raise_for_status()
                return response.json()[0]["result_kind"]
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(submit, (concurrent, equivalent))) == ["IDEMPOTENT_REPLAY", "INSERTED"]
        second_id = _psql(
            f"select id::text from public.mock_registration_intent_revisions where owner_user_id='{owner_id}'::uuid and target_period_id='{period_id}'::uuid and revision=2;"
        ).stdout.strip()
        assert second_id and _psql(f"select count(*) from public.decision_trace_outbox where revision_id='{second_id}'::uuid;").stdout.strip() == "1"

        stale = _persist(client, {**concurrent, "p_intent_id": str(uuid.uuid4()), "p_content_fingerprint": "c" * 64, "p_expected_current_revision": 1})
        stale.raise_for_status()
        assert stale.json()[0]["result_kind"] == "REVISION_CONFLICT"
        assert _psql(f"select count(*) from public.decision_trace_outbox where owner_user_id='{owner_id}'::uuid;").stdout.strip() == "2"

        invalid_intent = str(uuid.uuid4())
        invalid = _persist(client, {**first, "p_intent_id": invalid_intent, "p_expected_current_revision": 2, "p_content_fingerprint": "d" * 64, "p_validation_status": "INVALID"})
        assert invalid.status_code == 400
        assert _psql(f"select count(*) from public.mock_registration_intent_revisions where intent_id='{invalid_intent}'::uuid;").stdout.strip() == "0"

        direct_get = client.get(f"{URL}/rest/v1/decision_trace_outbox", headers=_user_headers(owner_token), params={"select": "event_id"})
        direct_insert = client.post(f"{URL}/rest/v1/decision_trace_outbox", headers=_user_headers(owner_token), json={})
        direct_update = client.patch(f"{URL}/rest/v1/decision_trace_outbox", headers=_user_headers(owner_token), params={"revision_id": f"eq.{revision_id}"}, json={"processing_state": "COMPLETED"})
        direct_delete = client.delete(f"{URL}/rest/v1/decision_trace_outbox", headers=_user_headers(owner_token), params={"revision_id": f"eq.{revision_id}"})
        assert {direct_get.status_code, direct_insert.status_code, direct_update.status_code, direct_delete.status_code} <= {401, 403}
        denied_rpc = _persist(client, first, _user_headers(owner_token))
        assert denied_rpc.status_code in (401, 403)

        no_parent = _psql(
            "insert into public.decision_trace_outbox (event_id, revision_id, owner_user_id, university_id, major_id, study_plan_id, study_plan_version, target_period_id, revision, event_type, snapshot_contract_version, source_snapshot) "
            f"values ('{uuid.uuid4()}', '{uuid.uuid4()}', '{owner_id}', '{university_id}', '{major_id}', '{plan_id}', 'x', '{period_id}', 99, 'MOCK_REGISTRATION_SUBMIT', '1.0', '{{}}'::jsonb);",
            check=False,
        )
        assert no_parent.returncode != 0
        immutable = _psql(
            f"update public.decision_trace_outbox set source_snapshot='{{}}'::jsonb where revision_id='{revision_id}'::uuid;",
            check=False,
        )
        assert immutable.returncode != 0 and "immutable" in immutable.stderr.lower()
        immutable_marker = _psql(
            f"update public.mock_registration_intent_revisions set outbox_required=false where id='{revision_id}'::uuid;",
            check=False,
        )
        assert immutable_marker.returncode != 0 and "immutable" in immutable_marker.stderr.lower()

        withdrawn = _persist(client, _payload(
            intent_id=str(uuid.uuid4()), owner_id=owner_id, university_id=university_id,
            major_id=major_id, plan_id=plan_id, period_id=period_id, expected=2,
            fingerprint="9" * 64, course_ids=[], course_codes=[],
        ) | {"p_lifecycle_status": "WITHDRAWN"})
        withdrawn.raise_for_status()
        assert withdrawn.json()[0]["result_kind"] == "INSERTED"
        withdrawn_id = withdrawn.json()[0]["persisted_revision_id"]
        assert _revision(withdrawn_id)["outbox_required"] is False
        assert _psql(f"select count(*) from public.decision_trace_outbox where revision_id='{withdrawn_id}'::uuid;").stdout.strip() == "0"


def test_required_outbox_failure_rolls_back_and_legacy_replay_does_not_backfill() -> None:
    run_id = uuid.uuid4()
    trigger_name = f"outbox_test_abort_{run_id.hex}"
    function_name = f"outbox_test_abort_fn_{run_id.hex}"
    with httpx.Client(timeout=30) as client:
        owner_id, _ = _create_user(client, run_id)
        plan_id, major_id, university_id, course_ids, course_codes, period_id = _context(client, run_id)
        prior = _persist(client, _payload(
            intent_id=str(uuid.uuid4()), owner_id=owner_id, university_id=university_id,
            major_id=major_id, plan_id=plan_id, period_id=period_id, expected=None,
            fingerprint="0" * 64, course_ids=[course_ids[0]], course_codes=[course_codes[0]],
        ))
        prior.raise_for_status()
        prior_revision_id = prior.json()[0]["persisted_revision_id"]
        prior_before = _revision(prior_revision_id)
        prior_event_before = _outbox(client, prior_revision_id)
        failed_intent = str(uuid.uuid4())
        _psql(
            f"create function public.{function_name}() returns trigger language plpgsql as $$ begin if new.owner_user_id = '{owner_id}'::uuid then raise exception 'synthetic local outbox failure'; end if; return new; end; $$; "
            f"create trigger {trigger_name} before insert on public.decision_trace_outbox for each row execute function public.{function_name}();"
        )
        try:
            failed = _persist(client, _payload(
                intent_id=failed_intent, owner_id=owner_id, university_id=university_id,
                major_id=major_id, plan_id=plan_id, period_id=period_id, expected=1,
                fingerprint="e" * 64, course_ids=[course_ids[0]], course_codes=[course_codes[0]],
            ))
            assert failed.status_code == 400
        finally:
            _psql(f"drop trigger if exists {trigger_name} on public.decision_trace_outbox; drop function if exists public.{function_name}();")
        assert _psql(f"select count(*) from public.mock_registration_intent_revisions where intent_id='{failed_intent}'::uuid;").stdout.strip() == "0"
        assert _psql(
            "select count(*) from public.mock_registration_intent_courses course "
            "join public.mock_registration_intent_revisions revision on revision.id = course.revision_id "
            f"where revision.intent_id='{failed_intent}'::uuid;"
        ).stdout.strip() == "0"
        assert _psql(f"select count(*) from public.decision_trace_outbox where owner_user_id='{owner_id}'::uuid;").stdout.strip() == "1"
        assert _revision(prior_revision_id) == prior_before
        assert _outbox(client, prior_revision_id) == prior_event_before

        legacy_revision_id, legacy_intent_id = str(uuid.uuid4()), str(uuid.uuid4())
        _psql(
            "insert into public.mock_registration_intent_revisions (id, intent_id, owner_user_id, university_id, major_id, study_plan_id, study_plan_version, target_period_id, revision, lifecycle_status, validation_status, content_fingerprint, intent_provenance, intent_source_version, progress_state_version, phase5_policy_version, phase6_policy_version, p6_contract_version, target_period_source_version, transparency_notice_version, actor_class) "
            f"values ('{legacy_revision_id}', '{legacy_intent_id}', '{owner_id}', '{university_id}', '{major_id}', '{plan_id}', 'legacy-plan:v1', '{period_id}', 1, 'SUBMITTED', 'VALID', '{'f' * 64}', 'SYNTHETIC_SANDBOX_INTENT', 'legacy-intent:v1', 'legacy-progress:v1', 'phase5:v1', 'phase6:v1', '1.0', 'outbox-period:v1', 'legacy-notice:v1', 'APPLICATION_SERVICE'); "
            "insert into public.mock_registration_intent_courses (revision_id, course_id, course_code, selection_order) "
            f"values ('{legacy_revision_id}', '{course_ids[0]}', '{course_codes[0]}', 1);"
        )
        legacy = _persist(client, _payload(
            intent_id=str(uuid.uuid4()), owner_id=owner_id, university_id=university_id,
            major_id=major_id, plan_id=plan_id, period_id=period_id, expected=None,
            fingerprint="f" * 64, course_ids=[course_ids[0]], course_codes=[course_codes[0]],
        ) | {"p_study_plan_version": "legacy-plan:v1", "p_intent_source_version": "legacy-intent:v1", "p_progress_state_version": "legacy-progress:v1", "p_transparency_notice_version": "legacy-notice:v1"})
        legacy.raise_for_status()
        assert legacy.json()[0]["result_kind"] == "IDEMPOTENT_REPLAY"
        assert legacy.json()[0]["persisted_revision_id"] == legacy_revision_id
        assert _revision(legacy_revision_id)["outbox_required"] is False
        assert _psql(f"select count(*) from public.decision_trace_outbox where revision_id='{legacy_revision_id}'::uuid;").stdout.strip() == "0"


def test_required_outbox_replay_rejects_missing_or_mismatched_event() -> None:
    """Synthetic owner-side fixtures isolate required-replay corruption paths locally."""
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        owner_id, _ = _create_user(client, run_id)
        plan_id, major_id, university_id, course_ids, course_codes, period_id = _context(client, run_id)

        missing_id, missing_intent = str(uuid.uuid4()), str(uuid.uuid4())
        missing_version = "required-missing:v1"
        _psql(
            "insert into public.mock_registration_intent_revisions (id, intent_id, owner_user_id, university_id, major_id, study_plan_id, study_plan_version, target_period_id, revision, lifecycle_status, validation_status, content_fingerprint, intent_provenance, intent_source_version, progress_state_version, phase5_policy_version, phase6_policy_version, p6_contract_version, target_period_source_version, transparency_notice_version, actor_class, outbox_required) "
            f"values ('{missing_id}', '{missing_intent}', '{owner_id}', '{university_id}', '{major_id}', '{plan_id}', '{missing_version}', '{period_id}', 1, 'SUBMITTED', 'VALID', '{'1' * 64}', 'SYNTHETIC_SANDBOX_INTENT', 'required-intent:v1', 'required-progress:v1', 'phase5:v1', 'phase6:v1', '1.0', 'outbox-period:v1', 'required-notice:v1', 'APPLICATION_SERVICE', true); "
            "insert into public.mock_registration_intent_courses (revision_id, course_id, course_code, selection_order) "
            f"values ('{missing_id}', '{course_ids[0]}', '{course_codes[0]}', 1);"
        )
        missing = _persist(client, _payload(
            intent_id=str(uuid.uuid4()), owner_id=owner_id, university_id=university_id,
            major_id=major_id, plan_id=plan_id, period_id=period_id, expected=None,
            fingerprint="1" * 64, course_ids=[course_ids[0]], course_codes=[course_codes[0]],
        ) | {
            "p_study_plan_version": missing_version,
            "p_intent_source_version": "required-intent:v1",
            "p_progress_state_version": "required-progress:v1",
            "p_transparency_notice_version": "required-notice:v1",
        })
        assert missing.status_code == 400
        assert "Required P6 outbox event is missing for replay" in missing.text
        assert _psql(f"select count(*) from public.decision_trace_outbox where revision_id='{missing_id}'::uuid;").stdout.strip() == "0"

        mismatch_id, mismatch_intent = str(uuid.uuid4()), str(uuid.uuid4())
        mismatch_version = "required-mismatch:v1"
        _psql(
            "insert into public.mock_registration_intent_revisions (id, intent_id, owner_user_id, university_id, major_id, study_plan_id, study_plan_version, target_period_id, revision, lifecycle_status, validation_status, content_fingerprint, intent_provenance, intent_source_version, progress_state_version, phase5_policy_version, phase6_policy_version, p6_contract_version, target_period_source_version, transparency_notice_version, actor_class, outbox_required) "
            f"values ('{mismatch_id}', '{mismatch_intent}', '{owner_id}', '{university_id}', '{major_id}', '{plan_id}', '{mismatch_version}', '{period_id}', 1, 'SUBMITTED', 'VALID', '{'2' * 64}', 'SYNTHETIC_SANDBOX_INTENT', 'required-intent:v1', 'required-progress:v1', 'phase5:v1', 'phase6:v1', '1.0', 'outbox-period:v1', 'required-notice:v1', 'APPLICATION_SERVICE', true); "
            "insert into public.mock_registration_intent_courses (revision_id, course_id, course_code, selection_order) "
            f"values ('{mismatch_id}', '{course_ids[0]}', '{course_codes[0]}', 1); "
            "insert into public.decision_trace_outbox (event_id, revision_id, owner_user_id, university_id, major_id, study_plan_id, study_plan_version, target_period_id, revision, event_type, snapshot_contract_version, source_snapshot) "
            "select revision.id, revision.id, revision.owner_user_id, revision.university_id, revision.major_id, revision.study_plan_id, revision.study_plan_version, revision.target_period_id, 999, 'MOCK_REGISTRATION_SUBMIT', '1.0', "
            "jsonb_build_object('revision_id', revision.id, 'intent_id', revision.intent_id, 'owner_user_id', revision.owner_user_id, 'university_id', revision.university_id, 'major_id', revision.major_id, 'study_plan_id', revision.study_plan_id, 'study_plan_version', revision.study_plan_version, 'target_period_id', revision.target_period_id, 'revision', 999, 'lifecycle_status', 'SUBMITTED', 'validation_status', revision.validation_status, 'content_fingerprint', revision.content_fingerprint, 'intent_provenance', revision.intent_provenance, 'intent_source_version', revision.intent_source_version, 'validation_reason_codes', revision.validation_reason_codes, 'catalog_source_versions', revision.catalog_source_versions, 'prerequisite_source_versions', revision.prerequisite_source_versions, 'progress_state_version', revision.progress_state_version, 'progress_state_reference', revision.progress_state_reference, 'phase5_policy_version', revision.phase5_policy_version, 'phase6_policy_version', revision.phase6_policy_version, 'p6_contract_version', revision.p6_contract_version, 'target_period_source_version', revision.target_period_source_version, 'transparency_notice_version', revision.transparency_notice_version, 'actor_class', revision.actor_class, 'created_at', revision.created_at, 'courses', '[]'::jsonb) "
            f"from public.mock_registration_intent_revisions revision where revision.id='{mismatch_id}'::uuid;"
        )
        mismatch = _persist(client, _payload(
            intent_id=str(uuid.uuid4()), owner_id=owner_id, university_id=university_id,
            major_id=major_id, plan_id=plan_id, period_id=period_id, expected=None,
            fingerprint="2" * 64, course_ids=[course_ids[0]], course_codes=[course_codes[0]],
        ) | {
            "p_study_plan_version": mismatch_version,
            "p_intent_source_version": "required-intent:v1",
            "p_progress_state_version": "required-progress:v1",
            "p_transparency_notice_version": "required-notice:v1",
        })
        assert mismatch.status_code == 400
        assert "Required P6 outbox event integrity mismatch during replay" in mismatch.text


def test_real_required_p6_outbox_maps_without_ledger_append_or_state_transition() -> None:
    """MAP-01/14/15: real local source facts map; no runtime outbox read grant is claimed."""
    run_id = uuid.uuid4()
    with httpx.Client(timeout=30) as client:
        owner_id, _ = _create_user(client, run_id)
        plan_id, major_id, university_id, course_ids, course_codes, period_id = _context(client, run_id)
        created = _persist(client, _payload(
            intent_id=str(uuid.uuid4()), owner_id=owner_id, university_id=university_id,
            major_id=major_id, plan_id=plan_id, period_id=period_id, expected=None,
            fingerprint="7" * 64, course_ids=[course_ids[0]], course_codes=[course_codes[0]],
        ) | {"p_actor_class": "STUDENT_AUTHENTICATED"})
        created.raise_for_status()
        revision_id = created.json()[0]["persisted_revision_id"]
        before_ledger = _psql(
            f"select count(*) from public.decision_trace_ledger where ledger_entry_id='{revision_id}';"
        ).stdout.strip()
        projection = _trusted_mapper_projection(revision_id)
        entry = map_verified_mock_registration_submit(projection)

        assert entry.ledger_entry_id == revision_id
        assert entry.student_user_id == owner_id
        assert entry.university_id == university_id
        assert entry.source_engine == "P6_MOCK_REGISTRATION_VALIDATION"
        assert entry.evidence_references[0].source == "P6_INTENT_COURSE_SET"
        assert len(entry.evidence_references) == 3
        assert all(item.locator is None and item.uri is None for item in entry.evidence_references)
        assert verify_integrity_hash(entry)
        assert canonical_ledger_payload(entry) == canonical_ledger_payload(
            map_verified_mock_registration_submit(_trusted_mapper_projection(revision_id))
        )
        assert _psql(
            f"select count(*) from public.decision_trace_ledger where ledger_entry_id='{revision_id}';"
        ).stdout.strip() == before_ledger == "0"
        assert _outbox(client, revision_id)["processing_state"] == "PENDING"
