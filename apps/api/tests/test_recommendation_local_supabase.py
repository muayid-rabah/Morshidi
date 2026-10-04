"""Opt-in real Plan 12 recommendation integration tests against local Supabase.

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


def test_real_plan12_recommendations_scenarios_and_isolation() -> None:
    password = f"Local-{uuid.uuid4()}-Aa1!"
    email_a = f"rec-a-{uuid.uuid4()}@local.test"
    email_b = f"rec-b-{uuid.uuid4()}@local.test"
    admin_headers = {"apikey": SERVER_KEY or "", "Authorization": f"Bearer {SERVER_KEY or ''}"}

    with httpx.Client(timeout=15) as http:
        user_a_id, token_a = _create_user(http, email_a, password, admin_headers)
        user_b_id, token_b = _create_user(http, email_b, password, admin_headers)

        auth_a = {"Authorization": f"Bearer {token_a}"}
        auth_b = {"Authorization": f"Bearer {token_b}"}

        try:
            with TestClient(app) as client:
                # -----------------------------------------------------------
                # PART 12: Cross-user isolation - User B has no profile yet -> 404
                # -----------------------------------------------------------
                b_missing = client.get("/api/v1/me/course-recommendations", headers=auth_b)
                assert b_missing.status_code == 404
                assert b_missing.json()["error_code"] == "STUDENT_RESOURCE_NOT_FOUND"

                # -----------------------------------------------------------
                # SCENARIO A: Empty history for User A
                # -----------------------------------------------------------
                create_a = client.post(
                    "/api/v1/me/academic-profile",
                    headers=auth_a,
                    json={"study_plan_id": PLAN},
                )
                assert create_a.status_code == 201

                rec_empty = client.get("/api/v1/me/course-recommendations", headers=auth_a)
                assert rec_empty.status_code == 200
                data_empty = rec_empty.json()

                assert data_empty["recommendation_policy_version"] == "1.0"
                assert data_empty["study_plan_id"] == PLAN
                assert len(data_empty["ranked_recommendations"]) > 0

                ranked_codes = [c["course_code"] for c in data_empty["ranked_recommendations"]]
                review_codes = [c["course_code"] for c in data_empty["review_required_courses"]]

                # No referenced-only non-plan course in ranking
                assert "0300103" not in ranked_codes
                assert "0200150" not in ranked_codes

                # Review-required courses must be separated (Scenario F)
                assert "1505311" in review_codes
                assert "1505320" in review_codes
                assert "1505311" not in ranked_codes
                assert "1505320" not in ranked_codes

                # Deterministic ordering: check sequential ranks
                ranks = [c["rank"] for c in data_empty["ranked_recommendations"]]
                assert ranks == list(range(1, len(ranks) + 1))

                # Zero-credit required courses (0200115, 1509999) must rank
                assert "0200115" in ranked_codes
                assert "1509999" in ranked_codes

                # -----------------------------------------------------------
                # PART 13: Determinism - calling twice produces identical JSON
                # -----------------------------------------------------------
                rec_empty_again = client.get("/api/v1/me/course-recommendations", headers=auth_a)
                assert rec_empty_again.status_code == 200
                assert rec_empty.json() == rec_empty_again.json()

                # -----------------------------------------------------------
                # SCENARIO G: Limit semantics (?limit=3)
                # -----------------------------------------------------------
                rec_lim3 = client.get("/api/v1/me/course-recommendations?limit=3", headers=auth_a)
                assert rec_lim3.status_code == 200
                data_lim3 = rec_lim3.json()
                assert len(data_lim3["ranked_recommendations"]) == 3
                assert data_lim3["ranked_recommendations"] == data_empty["ranked_recommendations"][:3]
                # review_required is not trimmed by limit
                assert len(data_lim3["review_required_courses"]) == len(data_empty["review_required_courses"])

                # -----------------------------------------------------------
                # SCENARIO B: Passed prerequisite (0300153 PASSED -> 1501110)
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "0300153", "status": "PASSED"},
                )
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "1501110", "status": "PASSED"},
                )

                rec_passed = client.get("/api/v1/me/course-recommendations", headers=auth_a)
                assert rec_passed.status_code == 200
                codes_after_pass = [c["course_code"] for c in rec_passed.json()["ranked_recommendations"]]

                # 1501110 is COMPLETED -> excluded from ranked recommendations
                assert "1501110" not in codes_after_pass
                # 1501112 requires 1501110 -> now ELIGIBLE and ranked
                assert "1501112" in codes_after_pass

                # -----------------------------------------------------------
                # SCENARIO C: In-progress exclusion
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "1501112", "status": "IN_PROGRESS"},
                )
                rec_in_prog = client.get("/api/v1/me/course-recommendations", headers=auth_a)
                assert rec_in_prog.status_code == 200
                data_in_prog = rec_in_prog.json()
                codes_in_prog = [c["course_code"] for c in data_in_prog["ranked_recommendations"]]
                assert "1501112" not in codes_in_prog
                assert "1501112" in data_in_prog["excluded_in_progress"]

                # -----------------------------------------------------------
                # SCENARIO D: Previous failure
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "0200104", "status": "FAILED"},
                )
                rec_failed = client.get("/api/v1/me/course-recommendations", headers=auth_a)
                assert rec_failed.status_code == 200
                cand_0200104 = next(
                    c for c in rec_failed.json()["ranked_recommendations"]
                    if c["course_code"] == "0200104"
                )
                assert cand_0200104["previously_attempted"] is True
                assert "PREVIOUSLY_ATTEMPTED" in cand_0200104["reason_codes"]
                assert cand_0200104["course_state"] == "ATTEMPTED_NOT_COMPLETED"

                # -----------------------------------------------------------
                # SCENARIO E: Referenced-only history
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile/attempts",
                    headers=auth_a,
                    json={"course_code": "0300103", "status": "PASSED"},
                )
                rec_ref = client.get("/api/v1/me/course-recommendations", headers=auth_a)
                assert rec_ref.status_code == 200
                all_codes = (
                    [c["course_code"] for c in rec_ref.json()["ranked_recommendations"]]
                    + [c["course_code"] for c in rec_ref.json()["review_required_courses"]]
                )
                assert "0300103" not in all_codes

                # -----------------------------------------------------------
                # PART 12: Cross-user isolation - Create profile for User B
                # -----------------------------------------------------------
                client.post(
                    "/api/v1/me/academic-profile",
                    headers=auth_b,
                    json={"study_plan_id": PLAN},
                )
                rec_b = client.get("/api/v1/me/course-recommendations", headers=auth_b)
                assert rec_b.status_code == 200
                codes_b = [c["course_code"] for c in rec_b.json()["ranked_recommendations"]]

                # User B has no attempts, so 0300153 is eligible for User B (it has no prereqs)
                assert "0300153" in codes_b
                # 1501110 requires 0300153, so 1501110 is NOT eligible yet for User B
                assert "1501110" not in codes_b
                # User B never has User A's excluded_in_progress
                assert "1501112" not in rec_b.json()["excluded_in_progress"]

        finally:
            _delete_user(http, user_a_id, admin_headers)
            _delete_user(http, user_b_id, admin_headers)
