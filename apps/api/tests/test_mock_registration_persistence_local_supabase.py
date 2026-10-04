"""Opt-in P6.4 runtime persistence/security validation against local Supabase."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import uuid

import httpx
import pytest

from app.mock_registration.models import IntentLifecycle, TargetPeriodClass
from app.mock_registration_persistence.repository import SupabaseMockRegistrationRepository

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
        "Prefer": "return=representation",
    }


def _user_headers(token: str) -> dict[str, str]:
    return {
        "apikey": ANON_KEY or "",
        "Authorization": f"Bearer {token}",
        "Prefer": "return=representation",
    }


def _create_user(client: httpx.Client, email: str, password: str) -> tuple[str, str]:
    created = client.post(
        f"{URL}/auth/v1/admin/users",
        headers=_admin_headers(),
        json={"email": email, "password": password, "email_confirm": True},
    )
    created.raise_for_status()
    signed_in = client.post(
        f"{URL}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": ANON_KEY or ""},
        json={"email": email, "password": password},
    )
    signed_in.raise_for_status()
    return created.json()["id"], signed_in.json()["access_token"]


def _rpc_payload(
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
    lifecycle: str = "SUBMITTED",
    validation: str = "VALID",
    reasons: list[str] | None = None,
) -> dict[str, object]:
    return {
        "p_intent_id": intent_id,
        "p_owner_user_id": owner_id,
        "p_university_id": university_id,
        "p_major_id": major_id,
        "p_study_plan_id": plan_id,
        "p_study_plan_version": "plan-runtime:v1",
        "p_target_period_id": period_id,
        "p_expected_current_revision": expected,
        "p_lifecycle_status": lifecycle,
        "p_validation_status": validation,
        "p_content_fingerprint": fingerprint,
        "p_intent_provenance": "SYNTHETIC_SANDBOX_INTENT",
        "p_intent_source_version": "runtime-intent:v1",
        "p_validation_reason_codes": reasons or [],
        "p_catalog_source_versions": ["runtime-catalog:v1"],
        "p_prerequisite_source_versions": ["runtime-prerequisite:v1"],
        "p_progress_state_version": "runtime-progress:v1",
        "p_progress_state_reference": None,
        "p_phase5_policy_version": "phase5:v1",
        "p_phase6_policy_version": "phase6:v1",
        "p_p6_contract_version": "1.0",
        "p_target_period_source_version": "runtime-period:v1",
        "p_transparency_notice_version": "runtime-notice:v1",
        "p_actor_class": "APPLICATION_SERVICE",
        "p_course_ids": course_ids,
        "p_course_codes": course_codes,
    }


def _persist(client: httpx.Client, payload: dict[str, object]) -> httpx.Response:
    return client.post(
        f"{URL}/rest/v1/rpc/persist_mock_registration_revision",
        headers=_admin_headers(),
        json=payload,
    )


def test_p6_4_local_runtime_persistence_and_security_contract() -> None:
    run_id = uuid.uuid4()
    password = f"Local-{run_id}-Aa1!"
    emails = [f"p64-{label}-{run_id}@local.test" for label in ("owner-a", "owner-b", "analyst")]

    with httpx.Client(timeout=20) as client:
        identities = [_create_user(client, email, password) for email in emails]
        (owner_a, token_a), (owner_b, token_b), (analyst, analyst_token) = identities

        plans = client.get(
            f"{URL}/rest/v1/study_plans",
            headers=_admin_headers(),
            params={"select": "id,major_id,majors(faculties(university_id))", "limit": "1"},
        )
        plans.raise_for_status()
        plan = plans.json()[0]
        plan_id = plan["id"]
        major_id = plan["major_id"]
        university_id = plan["majors"]["faculties"]["university_id"]

        plan_courses = client.get(
            f"{URL}/rest/v1/study_plan_courses",
            headers=_admin_headers(),
            params={
                "select": "course_id,courses(course_code)",
                "study_plan_id": f"eq.{plan_id}",
                "active": "eq.true",
                "order": "display_order.asc",
                "limit": "2",
            },
        )
        plan_courses.raise_for_status()
        course_pairs = sorted(
            ((row["courses"]["course_code"], row["course_id"]) for row in plan_courses.json()),
            key=lambda item: item[0],
        )
        assert len(course_pairs) == 2
        course_codes = [item[0] for item in course_pairs]
        course_ids = [item[1] for item in course_pairs]

        period = client.post(
            f"{URL}/rest/v1/mock_registration_target_periods",
            headers=_admin_headers(),
            json={
                "university_id": university_id,
                "provider_namespace": f"synthetic-runtime-{run_id}",
                "period_key": "p6.4-runtime-period",
                "period_class": "SYNTHETIC_SANDBOX_PERIOD",
                "verified_provider_source": False,
                "source_version": "runtime-period:v1",
            },
        )
        period.raise_for_status()
        period_id = period.json()[0]["id"]

        first_intent = str(uuid.uuid4())
        first = _rpc_payload(
            intent_id=first_intent,
            owner_id=owner_a,
            university_id=university_id,
            major_id=major_id,
            plan_id=plan_id,
            period_id=period_id,
            expected=None,
            fingerprint="1" * 64,
            course_ids=[course_ids[0]],
            course_codes=[course_codes[0]],
        )
        first_response = _persist(client, first)
        first_response.raise_for_status()
        assert first_response.json()[0]["result_kind"] == "INSERTED"
        assert first_response.json()[0]["persisted_revision"] == 1

        replay = _persist(client, {**first, "p_intent_id": str(uuid.uuid4())})
        replay.raise_for_status()
        assert replay.json()[0]["result_kind"] == "IDEMPOTENT_REPLAY"

        conflicting_replay = _persist(
            client,
            {**first, "p_content_fingerprint": "2" * 64},
        )
        conflicting_replay.raise_for_status()
        assert conflicting_replay.json()[0]["result_kind"] == "PERSISTENCE_CONFLICT"

        next_payload = _rpc_payload(
            intent_id=str(uuid.uuid4()), owner_id=owner_a,
            university_id=university_id, major_id=major_id, plan_id=plan_id,
            period_id=period_id, expected=1, fingerprint="3" * 64,
            course_ids=[course_ids[1]], course_codes=[course_codes[1]],
        )
        next_response = _persist(client, next_payload)
        next_response.raise_for_status()
        assert next_response.json()[0]["result_kind"] == "INSERTED"
        assert next_response.json()[0]["persisted_revision"] == 2

        stale = _persist(
            client,
            _rpc_payload(
                intent_id=str(uuid.uuid4()), owner_id=owner_a,
                university_id=university_id, major_id=major_id, plan_id=plan_id,
                period_id=period_id, expected=1, fingerprint="4" * 64,
                course_ids=[course_ids[0]], course_codes=[course_codes[0]],
            ),
        )
        stale.raise_for_status()
        assert stale.json()[0]["result_kind"] == "REVISION_CONFLICT"

        concurrent_payloads = [
            _rpc_payload(
                intent_id=str(uuid.uuid4()), owner_id=owner_a,
                university_id=university_id, major_id=major_id, plan_id=plan_id,
                period_id=period_id, expected=2, fingerprint=character * 64,
                course_ids=[course_ids[index]], course_codes=[course_codes[index]],
            )
            for index, character in enumerate(("5", "6"))
        ]

        def concurrent_write(payload: dict[str, object]) -> str:
            with httpx.Client(timeout=20) as concurrent_client:
                response = _persist(concurrent_client, payload)
                response.raise_for_status()
                return response.json()[0]["result_kind"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(concurrent_write, concurrent_payloads))
        assert sorted(outcomes) == ["INSERTED", "REVISION_CONFLICT"]

        history = client.get(
            f"{URL}/rest/v1/mock_registration_intent_revisions",
            headers=_admin_headers(),
            params={
                "select": "id,intent_id,revision,lifecycle_status,content_fingerprint",
                "owner_user_id": f"eq.{owner_a}",
                "target_period_id": f"eq.{period_id}",
                "order": "revision.asc",
            },
        )
        history.raise_for_status()
        assert [row["revision"] for row in history.json()] == [1, 2, 3]
        revision_three = history.json()[-1]

        withdrawal = _persist(
            client,
            _rpc_payload(
                intent_id=str(uuid.uuid4()), owner_id=owner_a,
                university_id=university_id, major_id=major_id, plan_id=plan_id,
                period_id=period_id, expected=3, fingerprint="7" * 64,
                course_ids=[], course_codes=[], lifecycle="WITHDRAWN",
            ),
        )
        withdrawal.raise_for_status()
        assert withdrawal.json()[0]["result_kind"] == "INSERTED"
        assert withdrawal.json()[0]["persisted_revision"] == 4

        review = _persist(
            client,
            _rpc_payload(
                intent_id=str(uuid.uuid4()), owner_id=owner_b,
                university_id=university_id, major_id=major_id, plan_id=plan_id,
                period_id=period_id, expected=None, fingerprint="8" * 64,
                course_ids=[course_ids[0]], course_codes=[course_codes[0]],
                validation="REVIEW_REQUIRED",
                reasons=["MOCK_REG_ELIGIBILITY_REVIEW_REQUIRED"],
            ),
        )
        review.raise_for_status()
        assert review.json()[0]["result_kind"] == "INSERTED"

        invalid_intent = str(uuid.uuid4())
        invalid = _persist(
            client,
            {
                **_rpc_payload(
                    intent_id=invalid_intent, owner_id=owner_b,
                    university_id=university_id, major_id=major_id, plan_id=plan_id,
                    period_id=period_id, expected=1, fingerprint="9" * 64,
                    course_ids=[course_ids[0]], course_codes=[course_codes[0]],
                ),
                "p_validation_status": "INVALID",
            },
        )
        assert invalid.status_code == 400
        absent_invalid = client.get(
            f"{URL}/rest/v1/mock_registration_intent_revisions",
            headers=_admin_headers(),
            params={"select": "id", "intent_id": f"eq.{invalid_intent}"},
        )
        absent_invalid.raise_for_status()
        assert absent_invalid.json() == []

        atomic_intent = str(uuid.uuid4())
        atomic = _persist(
            client,
            _rpc_payload(
                intent_id=atomic_intent, owner_id=owner_b,
                university_id=university_id, major_id=major_id, plan_id=plan_id,
                period_id=period_id, expected=1, fingerprint="a" * 64,
                course_ids=[course_ids[0], course_ids[1]],
                course_codes=[course_codes[0], "ZZZ-NOT-THE-COURSE"],
            ),
        )
        assert atomic.status_code == 400
        absent_atomic = client.get(
            f"{URL}/rest/v1/mock_registration_intent_revisions",
            headers=_admin_headers(),
            params={"select": "id", "intent_id": f"eq.{atomic_intent}"},
        )
        absent_atomic.raise_for_status()
        assert absent_atomic.json() == []

        duplicate = _persist(
            client,
            _rpc_payload(
                intent_id=str(uuid.uuid4()), owner_id=owner_b,
                university_id=university_id, major_id=major_id, plan_id=plan_id,
                period_id=period_id, expected=1, fingerprint="b" * 64,
                course_ids=[course_ids[0], course_ids[0]],
                course_codes=[course_codes[0], course_codes[0]],
            ),
        )
        assert duplicate.status_code == 400

        own_headers = client.get(
            f"{URL}/rest/v1/mock_registration_intent_revisions",
            headers=_user_headers(token_a), params={"select": "id,revision", "order": "revision.asc"},
        )
        own_headers.raise_for_status()
        assert [row["revision"] for row in own_headers.json()] == [1, 2, 3, 4]
        other_headers = client.get(
            f"{URL}/rest/v1/mock_registration_intent_revisions",
            headers=_user_headers(token_b),
            params={"select": "id", "id": f"eq.{revision_three['id']}"},
        )
        other_headers.raise_for_status()
        assert other_headers.json() == []
        other_children = client.get(
            f"{URL}/rest/v1/mock_registration_intent_courses",
            headers=_user_headers(token_b), params={"select": "id"},
        )
        other_children.raise_for_status()
        assert len(other_children.json()) == 1

        direct_insert = client.post(
            f"{URL}/rest/v1/mock_registration_intent_revisions",
            headers=_user_headers(token_a), json={},
        )
        direct_update = client.patch(
            f"{URL}/rest/v1/mock_registration_intent_revisions",
            headers=_user_headers(token_a),
            params={"id": f"eq.{revision_three['id']}"},
            json={"content_fingerprint": "f" * 64},
        )
        direct_delete = client.delete(
            f"{URL}/rest/v1/mock_registration_intent_revisions",
            headers=_user_headers(token_a),
            params={"id": f"eq.{revision_three['id']}"},
        )
        assert {direct_insert.status_code, direct_update.status_code, direct_delete.status_code} <= {401, 403}

        anon = client.get(
            f"{URL}/rest/v1/mock_registration_intent_revisions",
            headers={"apikey": ANON_KEY or ""}, params={"select": "id"},
        )
        assert anon.status_code in (401, 403)

        membership = client.post(
            f"{URL}/rest/v1/institutional_memberships",
            headers=_admin_headers(),
            json={
                "subject_user_id": analyst,
                "university_id": university_id,
                "provider_namespace": f"synthetic-runtime-{run_id}",
                "role": "INSTITUTIONAL_ANALYST",
                "authority_source": "SYNTHETIC_TEST_AUTHORITY",
                "authority_source_version": "runtime-membership:v1",
            },
        )
        membership.raise_for_status()
        membership_id = membership.json()[0]["id"]
        self_promote = client.post(
            f"{URL}/rest/v1/institutional_memberships",
            headers=_user_headers(analyst_token), json={
                "subject_user_id": analyst, "university_id": university_id,
                "provider_namespace": "forged", "role": "INSTITUTIONAL_ANALYST",
                "authority_source": "FORGED", "authority_source_version": "forged:v1",
            },
        )
        self_change = client.patch(
            f"{URL}/rest/v1/institutional_memberships",
            headers=_user_headers(analyst_token),
            params={"id": f"eq.{membership_id}"}, json={"active": False},
        )
        membership_read = client.get(
            f"{URL}/rest/v1/institutional_memberships",
            headers=_user_headers(analyst_token), params={"select": "id"},
        )
        assert self_promote.status_code in (401, 403)
        assert self_change.status_code in (401, 403)
        assert membership_read.status_code in (401, 403)
        analyst_raw = client.get(
            f"{URL}/rest/v1/mock_registration_intent_revisions",
            headers=_user_headers(analyst_token), params={"select": "id"},
        )
        analyst_raw.raise_for_status()
        assert analyst_raw.json() == []

        foreign_university = client.post(
            f"{URL}/rest/v1/universities",
            headers=_admin_headers(),
            json={
                "name_ar": f"جامعة اختبار اصطناعية {run_id}",
                "name_en": f"Synthetic Runtime University {run_id}",
                "country": "Synthetic",
            },
        )
        foreign_university.raise_for_status()
        foreign_university_id = foreign_university.json()[0]["id"]
        foreign_period = client.post(
            f"{URL}/rest/v1/mock_registration_target_periods",
            headers=_admin_headers(),
            json={
                "university_id": foreign_university_id,
                "provider_namespace": f"synthetic-foreign-{run_id}",
                "period_key": "foreign-runtime-period",
                "period_class": "SYNTHETIC_SANDBOX_PERIOD",
                "source_version": "runtime-period:v1",
            },
        )
        foreign_period.raise_for_status()
        cross_university = _persist(
            client,
            _rpc_payload(
                intent_id=str(uuid.uuid4()), owner_id=owner_b,
                university_id=university_id, major_id=major_id, plan_id=plan_id,
                period_id=foreign_period.json()[0]["id"], expected=None,
                fingerprint="c" * 64, course_ids=[course_ids[0]],
                course_codes=[course_codes[0]],
            ),
        )
        assert cross_university.status_code == 400

        final_history = client.get(
            f"{URL}/rest/v1/mock_registration_intent_revisions",
            headers=_admin_headers(),
            params={"select": "revision,lifecycle_status", "owner_user_id": f"eq.{owner_a}", "order": "revision.asc"},
        )
        final_history.raise_for_status()
        assert final_history.json() == [
            {"revision": 1, "lifecycle_status": "SUBMITTED"},
            {"revision": 2, "lifecycle_status": "SUBMITTED"},
            {"revision": 3, "lifecycle_status": "SUBMITTED"},
            {"revision": 4, "lifecycle_status": "WITHDRAWN"},
        ]

        async def verify_repository_mapping() -> None:
            repository = SupabaseMockRegistrationRepository(URL or "", SERVER_KEY or "")
            try:
                loaded_period = await repository.load_target_period(
                    uuid.UUID(period_id), uuid.UUID(university_id)
                )
                assert loaded_period.period_class is TargetPeriodClass.SYNTHETIC_SANDBOX_PERIOD
                loaded_history = await repository.load_revision_history(
                    owner_user_id=uuid.UUID(owner_a),
                    university_id=uuid.UUID(university_id),
                    major_id=uuid.UUID(major_id),
                    study_plan_id=uuid.UUID(plan_id),
                    study_plan_version="plan-runtime:v1",
                    target_period_id=uuid.UUID(period_id),
                )
                assert [item.revision for item in loaded_history] == [1, 2, 3, 4]
                assert loaded_history[-1].lifecycle_status is IntentLifecycle.WITHDRAWN
                assert loaded_history[-1].courses == ()
                candidates = await repository.load_institution_period_candidates(
                    university_id=uuid.UUID(university_id),
                    target_period_id=uuid.UUID(period_id),
                    study_plan_id=uuid.UUID(plan_id),
                )
                assert len(candidates) == 5
                loaded_membership = await repository.load_active_membership(
                    subject_user_id=uuid.UUID(analyst),
                    university_id=uuid.UUID(university_id),
                )
                assert loaded_membership.role == "INSTITUTIONAL_ANALYST"
            finally:
                await repository.close()

        asyncio.run(verify_repository_mapping())
