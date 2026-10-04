"""Opt-in real Plan 12 semester planner integration tests against local Supabase (Phase 8.3).

These tests run only when local Supabase credentials are configured via:
    MORSHIDI_LOCAL_SUPABASE_URL
    MORSHIDI_LOCAL_SUPABASE_SERVER_KEY
    MORSHIDI_LOCAL_SUPABASE_ANON_KEY
    MORSHIDI_LOCAL_STUDY_PLAN_ID
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app

URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
SERVER_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")
ANON_KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_ANON_KEY")
PLAN = os.getenv("MORSHIDI_LOCAL_STUDY_PLAN_ID")

pytestmark = pytest.mark.skipif(
    not all((URL, SERVER_KEY, ANON_KEY, PLAN)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values to run integration tests",
)


def _create_user(client: httpx.Client, email: str, password: str, admin_headers: dict[str, str]) -> tuple[str, str]:
    created = client.post(
        f"{URL}/auth/v1/admin/users",
        headers=admin_headers,
        json={"email": email, "password": password, "email_confirm": True},
    )
    created.raise_for_status()
    user_id = created.json()["id"]

    signed_in = client.post(
        f"{URL}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": ANON_KEY or ""},
        json={"email": email, "password": password},
    )
    signed_in.raise_for_status()
    token = signed_in.json()["access_token"]
    return user_id, token


def _delete_user(client: httpx.Client, user_id: str, admin_headers: dict[str, str]) -> None:
    try:
        client.delete(f"{URL}/auth/v1/admin/users/{user_id}", headers=admin_headers)
    except Exception:
        pass


def test_real_plan12_semester_planner_scenarios_and_isolation() -> None:
    password = f"Local-{uuid.uuid4()}-Aa1!"
    email_a = f"local-planner-a-{uuid.uuid4()}@example.com"
    email_b = f"local-planner-b-{uuid.uuid4()}@example.com"
    admin_headers = {
        "apikey": SERVER_KEY or "",
        "Authorization": f"Bearer {SERVER_KEY}",
    }

    with httpx.Client(timeout=30.0) as http:
        user_a_id, token_a = _create_user(http, email_a, password, admin_headers)
        user_b_id, token_b = _create_user(http, email_b, password, admin_headers)
        try:
            with TestClient(app) as client:
                auth_a = {"Authorization": f"Bearer {token_a}"}
                auth_b = {"Authorization": f"Bearer {token_b}"}

                # -----------------------------------------------------------
                # PART 11: Cross-user isolation - User B without profile -> 404
                # -----------------------------------------------------------
                resp_b_noprofile = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_b,
                    json={"max_credit_hours": 15},
                )
                assert resp_b_noprofile.status_code == 404
                assert resp_b_noprofile.json()["error_code"] == "STUDENT_RESOURCE_NOT_FOUND"

                # -----------------------------------------------------------
                # SCENARIO A: Empty history (AI Plan 12 profile)
                # -----------------------------------------------------------
                create_profile_res = client.post(
                    "/api/v1/me/academic-profile",
                    headers=auth_a,
                    json={"study_plan_id": PLAN},
                )
                assert create_profile_res.status_code == 201

                plans_a = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_a,
                    json={"max_credit_hours": 15, "max_courses": 6, "max_options": 5},
                )
                assert plans_a.status_code == 200
                data_a = plans_a.json()

                assert data_a["semester_planner_policy_version"] == "1.0"
                assert data_a["planning_scope"] == "ACADEMIC_STRUCTURE_ONLY"
                assert data_a["candidate_window_size"] == 15
                assert len(data_a["plan_options"]) <= 5

                # Compare with recommendations to verify candidates come from Phase 7 ranking
                recs_a = client.get("/api/v1/me/course-recommendations", headers=auth_a)
                assert recs_a.status_code == 200
                ranked_recs = [c["course_code"] for c in recs_a.json()["ranked_recommendations"]]

                for opt in data_a["plan_options"]:
                    assert opt["total_courses"] <= 6
                    assert float(opt["total_credit_hours"]) <= 15.0
                    for course in opt["courses"]:
                        assert course["course_code"] in ranked_recs

                # -----------------------------------------------------------
                # SCENARIO B: Same-semester prerequisite chain
                # Verified chain: 0300153 -> 1501110 -> 1501112
                # -----------------------------------------------------------
                # Pass 0300153: makes 1501110 ELIGIBLE, but 1501112 NOT_ELIGIBLE
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "0300153", "status": "PASSED"},
                )

                plans_chain = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_a,
                    json={"max_credit_hours": 15},
                )
                assert plans_chain.status_code == 200
                for opt in plans_chain.json()["plan_options"]:
                    opt_codes = {c["course_code"] for c in opt["courses"]}
                    # 1501110 and 1501112 NEVER appear together in same semester plan
                    assert not ("1501110" in opt_codes and "1501112" in opt_codes)
                    if "1501110" in opt_codes:
                        # 1501112 may appear in newly_eligible_course_codes
                        assert "1501112" in opt["newly_eligible_course_codes"]

                # -----------------------------------------------------------
                # SCENARIO C: In-progress exclusion
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "1501110", "status": "IN_PROGRESS"},
                )
                plans_in_prog = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_a,
                    json={"max_credit_hours": 15},
                )
                assert plans_in_prog.status_code == 200
                data_in_prog = plans_in_prog.json()
                assert "1501110" in data_in_prog["excluded_in_progress"]
                for opt in data_in_prog["plan_options"]:
                    codes = {c["course_code"] for c in opt["courses"]}
                    assert "1501110" not in codes

                # -----------------------------------------------------------
                # SCENARIO D: Previous failure
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "0200104", "status": "FAILED"},
                )
                plans_failed = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_a,
                    json={"max_credit_hours": 15},
                )
                assert plans_failed.status_code == 200
                # If 0200104 is planned, previous attempt context is retained
                for opt in plans_failed.json()["plan_options"]:
                    for course in opt["courses"]:
                        if course["course_code"] == "0200104":
                            assert course["previously_attempted"] is True
                            assert "INCLUDES_PREVIOUSLY_ATTEMPTED_COURSE" in opt["reason_codes"]

                # -----------------------------------------------------------
                # SCENARIO E: Zero-credit request
                # -----------------------------------------------------------
                plans_zero = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_a,
                    json={"max_credit_hours": 0},
                )
                assert plans_zero.status_code == 200
                for opt in plans_zero.json()["plan_options"]:
                    assert float(opt["total_credit_hours"]) == 0.0

                # -----------------------------------------------------------
                # SCENARIO F: Review required courses never appear in plan
                # Real Plan 12: 1505311, 1505320
                # -----------------------------------------------------------
                for opt in plans_failed.json()["plan_options"]:
                    codes = {c["course_code"] for c in opt["courses"]}
                    assert "1505311" not in codes
                    assert "1505320" not in codes

                # -----------------------------------------------------------
                # SCENARIO G: Referenced-only passed course
                # Real Plan 12: 0300103
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "0300103", "status": "PASSED"},
                )
                plans_ref = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_a,
                    json={"max_credit_hours": 15},
                )
                assert plans_ref.status_code == 200
                for opt in plans_ref.json()["plan_options"]:
                    codes = {c["course_code"] for c in opt["courses"]}
                    assert "0300103" not in codes

                # -----------------------------------------------------------
                # SCENARIO H: max_options prefix behavior
                # -----------------------------------------------------------
                plans_opt5 = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_a,
                    json={"max_credit_hours": 15, "max_options": 5},
                ).json()
                plans_opt2 = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_a,
                    json={"max_credit_hours": 15, "max_options": 2},
                ).json()
                assert len(plans_opt2["plan_options"]) <= 2
                prefix = plans_opt5["plan_options"][:len(plans_opt2["plan_options"])]
                for opt2, opt5 in zip(plans_opt2["plan_options"], prefix):
                    assert [c["course_code"] for c in opt2["courses"]] == [c["course_code"] for c in opt5["courses"]]

                # -----------------------------------------------------------
                # PART 12: Determinism (Byte-identical / exact structural response)
                # -----------------------------------------------------------
                call_1 = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_a,
                    json={"max_credit_hours": 15, "max_courses": 5, "max_options": 3},
                ).json()
                call_2 = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_a,
                    json={"max_credit_hours": 15, "max_courses": 5, "max_options": 3},
                ).json()
                assert call_1 == call_2

                # -----------------------------------------------------------
                # User B creates own profile: strictly isolated
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile",
                    headers=auth_b,
                    json={"study_plan_id": PLAN},
                )
                plans_b = client.post(
                    "/api/v1/me/semester-plans",
                    headers=auth_b,
                    json={"max_credit_hours": 15},
                ).json()
                # User B has no attempts, so 1501110 is NOT in excluded_in_progress for User B
                assert "1501110" not in plans_b["excluded_in_progress"]

        finally:
            _delete_user(http, user_a_id, admin_headers)
            _delete_user(http, user_b_id, admin_headers)

