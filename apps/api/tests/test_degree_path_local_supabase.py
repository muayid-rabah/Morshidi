"""Opt-in real Plan 12 degree path planner integration tests against local Supabase (Phase 9.3).

These tests run only when local Supabase credentials are configured via:
    MORSHIDI_LOCAL_SUPABASE_URL
    MORSHIDI_LOCAL_SUPABASE_SERVER_KEY
    MORSHIDI_LOCAL_SUPABASE_ANON_KEY
    MORSHIDI_LOCAL_STUDY_PLAN_ID
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal

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


def test_real_plan12_degree_paths_scenarios_and_isolation() -> None:
    password = f"Local-{uuid.uuid4()}-Aa1!"
    email_a = f"local-degree-path-a-{uuid.uuid4()}@example.com"
    email_b = f"local-degree-path-b-{uuid.uuid4()}@example.com"
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
                # PART 15: Cross-user isolation - User B without profile -> 404
                # -----------------------------------------------------------
                resp_b_noprofile = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_b,
                    json={"max_credit_hours_per_semester": 15},
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

                paths_a = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={
                        "max_credit_hours_per_semester": 15,
                        "max_courses_per_semester": 5,
                        "max_semesters_ahead": 3,
                        "max_paths": 3,
                    },
                )
                assert paths_a.status_code == 200
                data_a = paths_a.json()

                assert data_a["degree_path_policy_version"] == "1.0"
                assert data_a["planning_scope"] == "MODELED_DEGREE_PATH_ONLY"
                assert len(data_a["paths"]) <= 3
                assert len(data_a["paths"]) >= 1

                for path in data_a["paths"]:
                    for sem in path["semesters"]:
                        opt = sem["plan_option"]
                        assert opt["total_courses"] <= 5
                        assert float(opt["total_credit_hours"]) <= 15.0
                        for c in opt["courses"]:
                            # No review-required or referenced-only courses planned
                            assert c["course_code"] not in ("1505311", "1505320", "0300103")

                # -----------------------------------------------------------
                # SCENARIO B: Verified Chain
                # 0300153 -> 1501110 -> 1501112 -> 1501221
                # -----------------------------------------------------------
                # Add 0300153 PASSED
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "0300153", "status": "PASSED"},
                )

                paths_chain = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 3},
                ).json()

                for path in paths_chain["paths"]:
                    course_semesters: dict[str, int] = {}
                    for sem in path["semesters"]:
                        for c in sem["plan_option"]["courses"]:
                            course_semesters[c["course_code"]] = sem["semester_index"]

                    # If 1501110 and 1501112 are both planned, 1501110 must precede 1501112
                    if "1501110" in course_semesters and "1501112" in course_semesters:
                        assert course_semesters["1501110"] < course_semesters["1501112"]
                    # If 1501112 and 1501221 are both planned, 1501112 must precede 1501221
                    if "1501112" in course_semesters and "1501221" in course_semesters:
                        assert course_semesters["1501112"] < course_semesters["1501221"]

                # -----------------------------------------------------------
                # SCENARIO C: In-Progress
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "1501110", "status": "IN_PROGRESS"},
                )
                paths_in_prog = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 2},
                ).json()

                assert "1501110" in paths_in_prog["persisted_in_progress_courses"]
                for path in paths_in_prog["paths"]:
                    for sem in path["semesters"]:
                        codes = [c["course_code"] for c in sem["plan_option"]["courses"]]
                        assert "1501110" not in codes
                        # 1501112 remains locked because 1501110 is IN_PROGRESS (never auto-passed)
                        assert "1501112" not in codes

                # -----------------------------------------------------------
                # SCENARIO D: Zero-Credit Required Courses
                # 0200115 (تنمية المجتمع والعمل التطوعي) & 1509999 (حلقة بحث)
                # -----------------------------------------------------------
                for path in data_a["paths"]:
                    for sem in path["semesters"]:
                        for c in sem["plan_option"]["courses"]:
                            if c["course_code"] in ("0200115", "1509999"):
                                assert float(c["credit_hours"]) == 0.0

                # -----------------------------------------------------------
                # SCENARIO E: Review Required Never Selected
                # 1505311, 1505320
                # -----------------------------------------------------------
                for path in paths_chain["paths"]:
                    for sem in path["semesters"]:
                        codes = [c["course_code"] for c in sem["plan_option"]["courses"]]
                        assert "1505311" not in codes
                        assert "1505320" not in codes

                # -----------------------------------------------------------
                # SCENARIO F: Referenced Only Accepted as History
                # 0300103 (الإحصاء والاحتمالات)
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "0300103", "status": "PASSED"},
                )
                paths_ref = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 2},
                ).json()
                for path in paths_ref["paths"]:
                    for sem in path["semesters"]:
                        codes = [c["course_code"] for c in sem["plan_option"]["courses"]]
                        assert "0300103" not in codes

                # -----------------------------------------------------------
                # SCENARIO G: Failed History
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "0200104", "status": "FAILED"},
                )
                paths_failed = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 2},
                ).json()
                for path in paths_failed["paths"]:
                    for sem in path["semesters"]:
                        for c in sem["plan_option"]["courses"]:
                            if c["course_code"] == "0200104":
                                assert c["previously_attempted"] is True

                # -----------------------------------------------------------
                # SCENARIO H: Horizon Reached
                # -----------------------------------------------------------
                paths_h1 = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 1},
                ).json()
                assert len(paths_h1["paths"]) >= 1
                for path in paths_h1["paths"]:
                    assert path["semester_count"] == 1
                    assert path["status"] == "HORIZON_REACHED"

                # -----------------------------------------------------------
                # SCENARIO I: max_paths Prefix Equivalence
                # -----------------------------------------------------------
                paths_p1 = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 2, "max_paths": 1},
                ).json()
                paths_p3 = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 2, "max_paths": 3},
                ).json()
                assert len(paths_p1["paths"]) == 1
                assert len(paths_p3["paths"]) >= 1
                # First path of p3 is structurally identical to the only path of p1
                assert paths_p1["paths"][0]["priority_tuple"] == paths_p3["paths"][0]["priority_tuple"]

                # -----------------------------------------------------------
                # SCENARIO J: High-Credit Ceiling vs Standard
                # -----------------------------------------------------------
                paths_12 = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={"max_credit_hours_per_semester": 12, "max_semesters_ahead": 1, "max_paths": 1},
                ).json()
                paths_18 = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={"max_credit_hours_per_semester": 18, "max_semesters_ahead": 1, "max_paths": 1},
                ).json()
                cred_12 = float(paths_12["paths"][0]["semesters"][0]["plan_option"]["total_credit_hours"])
                cred_18 = float(paths_18["paths"][0]["semesters"][0]["plan_option"]["total_credit_hours"])
                assert cred_12 <= 12.0
                assert cred_18 <= 18.0
                assert cred_18 >= cred_12

                # -----------------------------------------------------------
                # PART 16: Determinism
                # -----------------------------------------------------------
                call_1 = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={
                        "max_credit_hours_per_semester": 15,
                        "max_courses_per_semester": 5,
                        "max_semesters_ahead": 2,
                        "max_paths": 2,
                    },
                ).json()
                call_2 = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_a,
                    json={
                        "max_credit_hours_per_semester": 15,
                        "max_courses_per_semester": 5,
                        "max_semesters_ahead": 2,
                        "max_paths": 2,
                    },
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
                paths_b = client.post(
                    "/api/v1/me/degree-paths",
                    headers=auth_b,
                    json={"max_credit_hours_per_semester": 15, "max_semesters_ahead": 2},
                ).json()
                # User B has no attempts, so User A's in-progress course is not present in User B's result
                assert "1501110" not in paths_b["persisted_in_progress_courses"]

        finally:
            _delete_user(http, user_a_id, admin_headers)
            _delete_user(http, user_b_id, admin_headers)

