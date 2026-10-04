"""Opt-in local-only integration for the real student and catalog adapters."""

from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest

from app.catalog.supabase_repository import SupabaseAcademicCatalogRepository
from app.rules.evaluator import evaluate_can_take
from app.rules.models import CanTakeRequest, Decision
from app.student.errors import StudentProfileNotFound
from app.student.supabase_repository import SupabaseStudentAcademicRepository

URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")
PLAN = os.getenv("MORSHIDI_LOCAL_STUDY_PLAN_ID")
pytestmark = pytest.mark.skipif(not all((URL, KEY, PLAN)), reason="set local MORSHIDI_LOCAL_SUPABASE_* values")


def test_local_student_repository_and_phase5_stack() -> None:
    async def run() -> None:
        user_a, user_b, user_failed = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        async with httpx.AsyncClient() as client:
            headers = {"apikey": KEY or "", "Authorization": f"Bearer {KEY or ''}"}
            try:
                for user in (user_a, user_b, user_failed):
                    response = await client.post(f"{URL}/auth/v1/admin/users", headers=headers, json={"id": user, "email": f"{user}@local.test", "email_confirm": True})
                    response.raise_for_status()
                profile = await client.post(f"{URL}/rest/v1/student_academic_profiles", headers={**headers, "Prefer": "return=representation"}, json={"owner_user_id": user_a, "study_plan_id": PLAN, "reported_cumulative_gpa": 3.25, "reported_gpa_scale": 4, "reported_earned_credit_hours": 15})
                profile.raise_for_status(); profile_id = profile.json()[0]["id"]
                courses = await client.get(f"{URL}/rest/v1/courses", headers=headers, params={"select": "id,course_code", "course_code": "in.(1501110,0300103)"})
                courses.raise_for_status(); ids = {row["course_code"]: row["id"] for row in courses.json()}
                attempts = await client.post(f"{URL}/rest/v1/student_course_attempts", headers=headers, json=[{"profile_id": profile_id, "course_id": ids["1501110"], "outcome": "PASSED"}, {"profile_id": profile_id, "course_id": ids["0300103"], "outcome": "PASSED"}])
                attempts.raise_for_status()
                failed_profile = await client.post(f"{URL}/rest/v1/student_academic_profiles", headers={**headers, "Prefer": "return=representation"}, json={"owner_user_id": user_failed, "study_plan_id": PLAN})
                failed_profile.raise_for_status(); failed_profile_id = failed_profile.json()[0]["id"]
                failed_attempt = await client.post(f"{URL}/rest/v1/student_course_attempts", headers=headers, json={"profile_id": failed_profile_id, "course_id": ids["1501110"], "outcome": "FAILED"})
                failed_attempt.raise_for_status()
                student = SupabaseStudentAcademicRepository(URL or "", KEY or "")
                catalog = SupabaseAcademicCatalogRepository(URL or "", KEY or "")
                try:
                    state = await student.load_student_academic_state(user_a)
                    assert state.owner_user_id == user_a and state.study_plan_id == PLAN
                    assert {a.course_code for a in state.attempts} == {"1501110", "0300103"}
                    assert all(a.outcome.value == "PASSED" for a in state.attempts)
                    assert (await student.load_student_academic_state(user_a)).attempts == state.attempts
                    with pytest.raises(StudentProfileNotFound): await student.load_student_academic_state(user_b)
                    failed_state = await student.load_student_academic_state(user_failed)
                    failed_result = evaluate_can_take(await catalog.load_target_rules(PLAN or "", "1501112"), CanTakeRequest(PLAN or "", "1501112", failed_state.attempts))
                    assert failed_result.decision is Decision.NOT_ELIGIBLE
                    for target, expected in (("1501112", Decision.ELIGIBLE), ("1505311", Decision.REVIEW_REQUIRED), ("1505320", Decision.REVIEW_REQUIRED)):
                        result = evaluate_can_take(await catalog.load_target_rules(PLAN or "", target), CanTakeRequest(PLAN or "", target, state.attempts))
                        assert result.decision is expected
                finally:
                    await student.close(); await catalog.close()
            finally:
                for user in (user_a, user_b, user_failed):
                    await client.delete(f"{URL}/auth/v1/admin/users/{user}", headers=headers)
    asyncio.run(run())
