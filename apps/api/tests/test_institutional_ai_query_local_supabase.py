"""Real Local Supabase WC-039 tenant, suppression, no-write, no-ledger proof."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_institutional_ai_query import Interpreter
from tests.test_decision_trace_persistence_service_local_supabase import (
    ANON_KEY, SERVER_KEY, URL, _create_user, _plan_scope, _server_headers,
)


pytestmark = pytest.mark.skipif(not all((URL, SERVER_KEY, ANON_KEY)),
                                reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values")


def _rows(raw, table, **filters):
    response = raw.get(f"{URL}/rest/v1/{table}", headers=_server_headers(),
                       params={"select": "*", **filters})
    assert response.status_code == 200, f"{table} snapshot unavailable"
    return response.json()


def _snapshot(raw, student, analyst, plan):
    profiles = _rows(raw, "student_academic_profiles", owner_user_id=f"eq.{student}")
    profile_id = profiles[0]["id"]
    return {
        "profile": profiles,
        "attempts": _rows(raw, "student_course_attempts", profile_id=f"eq.{profile_id}"),
        "intents": _rows(raw, "mock_registration_intent_revisions", owner_user_id=f"eq.{student}"),
        "memberships": _rows(raw, "institutional_memberships", subject_user_id=f"eq.{analyst}"),
        "catalog": _rows(raw, "study_plan_courses", study_plan_id=f"eq.{plan}"),
        "ledger": _rows(raw, "decision_trace_ledger", actor_id=f"eq.{analyst}"),
    }


def test_local_query_inherits_suppression_and_never_writes_or_ledgers():
    marker = uuid4().hex
    namespace = f"wc039-{marker}"
    with httpx.Client(timeout=35) as raw:
        plan, university = _plan_scope(raw)
        course = _rows(raw, "study_plan_courses", study_plan_id=f"eq.{plan}")[0]
        course_code = raw.get(f"{URL}/rest/v1/courses", headers=_server_headers(),
                              params={"select": "course_code", "id": f"eq.{course['course_id']}"}).json()[0]["course_code"]
        student, student_token = _create_user(raw, "wc039-student")
        analyst, analyst_token = _create_user(raw, "wc039-analyst")
        outsider, outsider_token = _create_user(raw, "wc039-outsider")
        inactive, inactive_token = _create_user(raw, "wc039-inactive")
        profile = raw.post(f"{URL}/rest/v1/student_academic_profiles", headers=_server_headers(),
                           json={"owner_user_id": student, "study_plan_id": plan})
        assert profile.status_code == 201
        period = raw.post(f"{URL}/rest/v1/mock_registration_target_periods",
                          headers=_server_headers(), json={
                              "university_id": university, "provider_namespace": namespace,
                              "period_key": marker, "period_class": "SYNTHETIC_SANDBOX_PERIOD",
                              "verified_provider_source": False, "source_version": "wc039:synthetic:v1",
                          })
        assert period.status_code == 201
        period_id = period.json()[0]["id"]
        for user, active in ((analyst, True), (inactive, False)):
            membership = raw.post(f"{URL}/rest/v1/institutional_memberships",
                                  headers=_server_headers(), json={
                                      "subject_user_id": user, "university_id": university,
                                      "provider_namespace": namespace, "role": "INSTITUTIONAL_ANALYST",
                                      "active": active, "authority_source": "WC039_LOCAL_TEST",
                                      "authority_source_version": "v1",
                                  })
            assert membership.status_code == 201
        body = {"question": "كم الطلب المعلن على هذه المادة؟", "target_period_id": period_id,
                "study_plan_id": plan, "course_code": course_code, "university_id": university}
        with TestClient(app) as client:
            app.state.institutional_ai_query_service._interpreter = Interpreter()
            student_auth = {"Authorization": f"Bearer {student_token}"}
            created = client.post("/api/v1/me/mock-registration/revisions", headers=student_auth,
                                  json={"target_period_id": period_id, "course_codes": [course_code],
                                        "expected_current_revision": None,
                                        "transparency_notice_version": "synthetic-wc039:v1"})
            assert created.status_code == 201, created.text
            before = _snapshot(raw, student, analyst, plan)
            path = "/api/v1/institutional/ai-query"
            analyst_auth = {"Authorization": f"Bearer {analyst_token}"}
            access = client.get(f"{path}/access", headers=analyst_auth)
            assert access.status_code == 200 and university in access.json()["university_ids"]
            answered = client.post(path, headers=analyst_auth, json=body)
            assert answered.status_code == 200, answered.text
            payload = answered.json()
            assert payload["status"] == "ANSWERED"
            assert payload["interpretation"]["metric_id"] == "INST_SIG_DECLARED_DEMAND_COUNT"
            assert payload["result"]["status"] == "SUPPRESSED"
            assert payload["result"]["value"] is None
            assert "owner_user_id" not in answered.text and student not in answered.text
            assert "trace_id" not in answered.text and "sql" not in answered.text.lower()
            assert payload["query_fingerprint"] and len(payload["query_fingerprint"]) == 64
            for key, invalid in (("target_period_id", str(uuid4())),
                                 ("study_plan_id", str(uuid4())),
                                 ("course_code", "UNKNOWN999")):
                missing = client.post(path, headers=analyst_auth, json={**body, key: invalid})
                assert missing.status_code == 200 and missing.json()["status"] == "ABSTAINED"
                assert missing.json()["abstention_reason"] == "SCOPE_UNAVAILABLE"
            for token in (student_token, outsider_token, inactive_token):
                denied = client.post(path, headers={"Authorization": f"Bearer {token}"}, json=body)
                assert denied.status_code == 403
            foreign = client.post(path, headers=analyst_auth,
                                  json={**body, "university_id": str(uuid4())})
            assert foreign.status_code == 403
            individual = client.post(path, headers=analyst_auth,
                                     json={**body, "question": "أعطني أسماء الطلاب ومعدلاتهم"})
            assert individual.status_code == 200 and individual.json()["status"] == "ABSTAINED"
            assert _snapshot(raw, student, analyst, plan) == before
        absent = raw.get(f"{URL}/rest/v1/institutional_ai_query_history", headers=_server_headers())
        assert absent.status_code == 404
