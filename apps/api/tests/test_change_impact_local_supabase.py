"""Real Local Supabase WC-046 authorization, audit, retry and no-write evidence."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.catalog.supabase_repository import SupabaseAcademicCatalogRepository
from app.rules.models import PrerequisiteLogicStatus
from tests.test_decision_trace_persistence_service_local_supabase import (
    ANON_KEY, SERVER_KEY, URL, _assignment, _create_profile, _create_user,
    _membership, _plan_scope, _server_headers, _user_headers,
)
from tests.test_decision_trace_persistence_local_supabase import _foreign_university_id


pytestmark = pytest.mark.skipif(
    not all((URL, ANON_KEY, SERVER_KEY)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values",
)


def _rows(raw: httpx.Client, table: str, **filters):
    response = raw.get(f"{URL}/rest/v1/{table}", headers=_server_headers(),
                       params={"select": "*", **filters})
    assert response.status_code == 200, f"{table} snapshot unavailable"
    return response.json()


def _academic_snapshot(raw: httpx.Client, student: str, plan: str):
    profiles = _rows(raw, "student_academic_profiles", owner_user_id=f"eq.{student}")
    assert len(profiles) == 1
    profile_id = profiles[0]["id"]
    plan_courses = _rows(raw, "study_plan_courses", study_plan_id=f"eq.{plan}")
    ids = ",".join(row["id"] for row in plan_courses)
    return {
        "profile": profiles,
        "attempts": _rows(raw, "student_course_attempts", profile_id=f"eq.{profile_id}"),
        "plan_courses": plan_courses,
        "requirements": _rows(raw, "requirement_groups", study_plan_id=f"eq.{plan}"),
        "dependencies": _rows(raw, "course_dependency_groups",
                              study_plan_course_id=f"in.({ids})"),
        "mock_registration": _rows(raw, "mock_registration_intent_revisions",
                                   owner_user_id=f"eq.{student}"),
    }


def _trace_count(raw: httpx.Client, actor: str) -> int:
    return len(_rows(raw, "decision_trace_ledger", actor_id=f"eq.{actor}"))


def test_local_change_impact_is_scoped_audited_idempotent_and_no_write():
    with httpx.Client(timeout=35) as raw:
        plan, university = _plan_scope(raw)
        student, student_token = _create_user(raw, "impact-student")
        analyst, analyst_token = _create_user(raw, "impact-analyst")
        advisor, advisor_token = _create_user(raw, "impact-advisor")
        outsider, outsider_token = _create_user(raw, "impact-outsider")
        foreign, foreign_token = _create_user(raw, "impact-foreign")
        _create_profile(raw, student, plan)
        _membership(raw, analyst, university, "INSTITUTIONAL_ANALYST")
        _membership(raw, advisor, university, "ACADEMIC_ADVISOR")
        _membership(raw, foreign, _foreign_university_id(raw), "INSTITUTIONAL_ANALYST")
        _assignment(raw, advisor, student, university)
        plan_rows = raw.get(f"{URL}/rest/v1/study_plan_courses", headers=_server_headers(),
                            params={"select": "credit_hours,courses(course_code)",
                                    "study_plan_id": f"eq.{plan}"})
        assert plan_rows.status_code == 200
        credit_row = next(row for row in plan_rows.json()
                          if Decimal(str(row["credit_hours"])) > 0
                          and Decimal(str(row["credit_hours"])) < 30)
        old_credit = Decimal(str(credit_row["credit_hours"]))
        before = _academic_snapshot(raw, student, plan)
        analyst_count = _trace_count(raw, analyst)
        advisor_count = _trace_count(raw, advisor)

        policy_delta = {
            "change_type": "POLICY_VERSION_CHANGE", "document_code": "POLICY-TEST",
            "affected_topic": "ACADEMIC_REGULATION", "old_version": "v1",
            "new_version": "v2", "provenance_reference": f"local-{uuid4().hex}",
        }
        course_delta = {
            "change_type": "COURSE_CREDIT_HOURS_CHANGE", "study_plan_id": plan,
            "course_code": credit_row["courses"]["course_code"],
            "old_credit_hours": str(old_credit), "new_credit_hours": str(old_credit + 1),
            "old_version": "catalog-v1", "new_version": "proposed-v2",
            "provenance_reference": f"local-{uuid4().hex}",
        }
        async def load_catalog():
            repository = SupabaseAcademicCatalogRepository(URL or "", SERVER_KEY or "")
            try:
                return await repository.load_plan_eligibility_catalog(plan)
            finally:
                await repository.close()
        eligibility = asyncio.run(load_catalog())
        target = next(rule for rule in eligibility.plan_courses
                      if rule.prerequisite_logic_status is PrerequisiteLogicStatus.VERIFIED
                      and rule.dependency_groups)
        old_group = target.dependency_groups[0]
        additional = next(rule.course_code for rule in eligibility.plan_courses
                          if rule.course_code != target.course_code
                          and rule.course_code not in old_group.option_course_codes)
        prerequisite_delta = {
            "change_type": "PREREQUISITE_GROUP_CHANGE", "study_plan_id": plan,
            "target_course_code": target.course_code,
            "group_number": old_group.group_number,
            "dependency_type": old_group.dependency_type.value,
            "old_option_course_codes": list(old_group.option_course_codes),
            "new_option_course_codes": [*old_group.option_course_codes, additional],
            "old_version": "catalog-v1", "new_version": "proposed-v2",
            "provenance_reference": f"local-{uuid4().hex}",
        }
        institutional_path = "/api/v1/institutional/change-impact/evaluate"
        advisor_path = f"/api/v1/advisor/students/{student}/change-impact/evaluate"
        with TestClient(app) as client:
            analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
            advisor_headers = {"Authorization": f"Bearer {advisor_token}"}
            access = client.get("/api/v1/institutional/change-impact/access",
                                headers=analyst_headers)
            assert access.status_code == 200 and university in access.json()["university_ids"]
            first = client.post(institutional_path, headers=analyst_headers,
                                json={"university_id": university, "delta": policy_delta})
            assert first.status_code == 200, first.text
            assert first.json()["impact_status"] == "REVIEW_REQUIRED"
            assert first.json()["audit_status"] == "LEDGER_PERSISTED"
            retry = client.post(institutional_path, headers=analyst_headers,
                                json={"university_id": university, "delta": policy_delta})
            assert retry.status_code == 200, retry.text
            assert retry.json()["change_id"] == first.json()["change_id"]
            individual = client.post(advisor_path, headers=advisor_headers,
                                     json={"delta": course_delta})
            assert individual.status_code == 200, individual.text
            assert individual.json()["audit_status"] == "LEDGER_PERSISTED"
            assert student not in individual.text and advisor not in individual.text
            prerequisite = client.post(institutional_path, headers=analyst_headers,
                                       json={"university_id": university,
                                             "delta": prerequisite_delta})
            assert prerequisite.status_code == 200, prerequisite.text
            assert prerequisite.json()["impact_status"] == "CHANGED"
            assert target.course_code in prerequisite.json()["structurally_affected_courses"]
            for token in (student_token, outsider_token, foreign_token):
                denied = client.post(institutional_path,
                                     headers={"Authorization": f"Bearer {token}"},
                                     json={"university_id": university, "delta": policy_delta})
                assert denied.status_code == 403
            for token in (analyst_token, outsider_token, foreign_token, student_token):
                denied = client.post(advisor_path,
                                     headers={"Authorization": f"Bearer {token}"},
                                     json={"delta": course_delta})
                assert denied.status_code == 403
            browser_write = raw.post(f"{URL}/rest/v1/decision_trace_ledger",
                                     headers=_user_headers(analyst_token), json={})
            assert browser_write.status_code in (401, 403, 404)
        after = _academic_snapshot(raw, student, plan)
        assert after == before
        assert _trace_count(raw, analyst) == analyst_count + 2
        assert _trace_count(raw, advisor) == advisor_count + 1
        missing_table = raw.get(f"{URL}/rest/v1/change_impact_reports", headers=_server_headers())
        assert missing_table.status_code == 404
