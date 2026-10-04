"""Opt-in authenticated E2E against local Supabase and the real FastAPI app."""

import os
import uuid
from decimal import Decimal
from time import perf_counter

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
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values",
)


def test_local_authenticated_student_api_end_to_end() -> None:
    password = f"Local-{uuid.uuid4()}-Aa1!"
    emails = [f"phase64-{uuid.uuid4()}@local.test", f"phase64-{uuid.uuid4()}@local.test"]
    admin_headers = {"apikey": SERVER_KEY or "", "Authorization": f"Bearer {SERVER_KEY or ''}"}
    user_ids: list[str] = []
    tokens: list[str] = []
    with httpx.Client(timeout=10) as local:
        try:
            for email in emails:
                created = local.post(f"{URL}/auth/v1/admin/users", headers=admin_headers,
                    json={"email": email, "password": password, "email_confirm": True})
                created.raise_for_status(); user_ids.append(created.json()["id"])
                signed_in = local.post(f"{URL}/auth/v1/token", params={"grant_type": "password"},
                    headers={"apikey": ANON_KEY or ""}, json={"email": email, "password": password})
                signed_in.raise_for_status(); tokens.append(signed_in.json()["access_token"])

            auth_a = {"Authorization": f"Bearer {tokens[0]}"}
            auth_b = {"Authorization": f"Bearer {tokens[1]}"}
            with TestClient(app) as client:
                created_profile = client.post("/api/v1/me/academic-profile", headers=auth_a,
                    json={"study_plan_id": PLAN, "reported_cumulative_gpa": 3.25,
                        "reported_gpa_scale": 4, "reported_earned_credit_hours": 15})
                assert created_profile.status_code == 201
                assert client.get("/api/v1/me/academic-profile", headers=auth_a).json()["id"] == created_profile.json()["id"]
                policies = client.get("/api/v1/me/policies", headers=auth_a)
                assert policies.status_code == 200 and isinstance(policies.json(), list)
                missing_profile_policies = client.get("/api/v1/me/policies", headers=auth_b)
                assert missing_profile_policies.status_code == 200 and missing_profile_policies.json() == []

                failed = client.post("/api/v1/me/academic-profile/attempts", headers=auth_a,
                    json={"course_code": "1501110", "status": "FAILED", "raw_grade_text": "raw-failure"})
                assert failed.status_code == 201
                failed_id = failed.json()["id"]
                failed_eligibility = client.get("/api/v1/me/eligibility/1501112", headers=auth_a)
                assert failed_eligibility.status_code == 200
                assert failed_eligibility.json()["decision"] == "NOT_ELIGIBLE"

                passed = client.post("/api/v1/me/academic-profile/attempts", headers=auth_a,
                    json={"course_code": "1501110", "status": "PASSED", "raw_grade_text": "B+"})
                assert passed.status_code == 201
                passed_id = passed.json()["id"]
                eligibility_one = client.get("/api/v1/me/eligibility/1501112", headers=auth_a)
                eligibility_two = client.get("/api/v1/me/eligibility/1501112", headers=auth_a)
                assert eligibility_one.status_code == 200
                assert eligibility_one.json() == eligibility_two.json()
                assert eligibility_one.json()["decision"] == "ELIGIBLE"

                referenced = client.post("/api/v1/me/academic-profile/attempts", headers=auth_a,
                    json={"course_code": "0300103", "status": "PASSED"})
                assert referenced.status_code == 201
                referenced_id = referenced.json()["id"]
                listed = client.get("/api/v1/me/academic-profile/attempts", headers=auth_a)
                assert listed.status_code == 200
                assert "0300103" in {row["course_code"] for row in listed.json()}
                assert [row["course_code"] for row in listed.json()].count("1501110") == 2

                progress_one = client.get("/api/v1/me/academic-progress", headers=auth_a)
                progress_two = client.get("/api/v1/me/academic-progress", headers=auth_a)
                assert progress_one.status_code == 200
                assert progress_one.json() == progress_two.json()
                assert Decimal(progress_one.json()["plan_total_required_credits"]) == 132
                assert Decimal(progress_one.json()["completed_plan_credits"]) == 3
                assert Decimal(progress_one.json()["reported_earned_credit_hours"]) == 15
                assert "0300103" not in {row["course_code"] for row in progress_one.json()["courses"]}

                roadmap_started = perf_counter()
                roadmap = client.get("/api/v1/me/academic-roadmap", headers=auth_a)
                roadmap_ms = (perf_counter() - roadmap_started) * 1000
                assert roadmap.status_code == 200
                modeled = roadmap.json()
                assert modeled["study_plan_id"] == PLAN
                assert len(modeled["courses"]) == len(progress_one.json()["courses"])
                assert next(row for row in modeled["courses"] if row["course_code"] == "1501110")["state"] == "COMPLETED"
                assert "owner_user_id" not in modeled
                assert modeled["modeling_status"] == "NOT_REQUESTED"
                assert all(row["state"] != "PLANNED" for row in modeled["courses"])
                report = client.get("/api/v1/me/academic-report", headers=auth_a)
                assert report.status_code == 200
                assert report.headers["cache-control"] == "private, no-store"
                assert report.json()["modeled_state_marker"] == "MODELED_UNOFFICIAL"
                assert report.json()["snapshot_fingerprint"] == modeled["snapshot_fingerprint"]
                assert len(report.json()["courses"]) == len(modeled["courses"])
                planned = client.post("/api/v1/me/academic-roadmap/modeled-path", headers=auth_a,
                    json={"max_credit_hours_per_semester": 18, "max_semesters_ahead": 1, "max_paths": 1})
                assert planned.status_code == 200, planned.text[:300]
                assert planned.json()["snapshot_fingerprint"] == modeled["snapshot_fingerprint"]
                assert planned.json()["modeling_status"] in {"MODELED_PATH", "NO_VALID_PATH"}
                assert all(row["planned_order"] is not None for row in planned.json()["courses"]
                           if row["state"] == "PLANNED")
                print(f"local_roadmap_api_ms={roadmap_ms:.1f} course_count={len(modeled['courses'])}")

                updated_profile = client.patch("/api/v1/me/academic-profile", headers=auth_a,
                    json={"reported_cumulative_gpa": 3.5, "reported_gpa_scale": 4,
                        "reported_earned_credit_hours": 18})
                assert updated_profile.status_code == 200
                updated_progress = client.get("/api/v1/me/academic-progress", headers=auth_a).json()
                assert Decimal(updated_progress["reported_cumulative_gpa"]) == Decimal("3.5")
                assert Decimal(updated_progress["reported_gpa_scale"]) == 4
                assert Decimal(updated_progress["reported_earned_credit_hours"]) == 18
                assert Decimal(updated_progress["completed_plan_credits"]) == 3

                assert client.patch(f"/api/v1/me/academic-profile/attempts/{passed_id}", headers=auth_a,
                    json={"raw_grade_text": "A-"}).status_code == 200

                assert client.get("/api/v1/me/academic-profile", headers=auth_b).status_code == 404
                assert client.get("/api/v1/me/academic-progress", headers=auth_b).status_code == 404
                assert client.get("/api/v1/me/academic-roadmap", headers=auth_b).status_code == 404
                assert client.get("/api/v1/me/academic-report", headers=auth_b).status_code == 404
                assert client.patch(f"/api/v1/me/academic-profile/attempts/{passed_id}", headers=auth_b,
                    json={"status": "FAILED"}).status_code == 404

                rls_headers_a = {"apikey": ANON_KEY or "", "Authorization": f"Bearer {tokens[0]}"}
                rls_headers_b = {"apikey": ANON_KEY or "", "Authorization": f"Bearer {tokens[1]}"}
                anon_headers = {"apikey": ANON_KEY or ""}
                assert len(local.get(f"{URL}/rest/v1/student_academic_profiles", headers=rls_headers_a,
                    params={"select": "id", "owner_user_id": f"eq.{user_ids[0]}"}).json()) == 1
                assert len(local.get(f"{URL}/rest/v1/student_course_attempts", headers=rls_headers_a,
                    params={"select": "id"}).json()) == 3
                assert local.get(f"{URL}/rest/v1/student_academic_profiles", headers=rls_headers_b,
                    params={"select": "id", "owner_user_id": f"eq.{user_ids[0]}"}).json() == []
                assert local.get(f"{URL}/rest/v1/student_course_attempts", headers=rls_headers_b,
                    params={"select": "id", "id": f"eq.{passed_id}"}).json() == []
                protected_write = local.patch(f"{URL}/rest/v1/student_course_attempts", headers={
                    **rls_headers_a, "Prefer": "return=representation"},
                    params={"id": f"eq.{passed_id}"}, json={"raw_numeric_grade": 99})
                assert protected_write.status_code in (400, 401, 403)
                rls_mutation = local.patch(f"{URL}/rest/v1/student_course_attempts", headers={
                    **rls_headers_b, "Prefer": "return=representation"},
                    params={"id": f"eq.{passed_id}"}, json={"outcome": "WITHDRAWN"})
                rls_mutation.raise_for_status()
                assert rls_mutation.json() == []
                assert local.get(f"{URL}/rest/v1/student_academic_profiles", headers=anon_headers,
                    params={"select": "id"}).status_code in (401, 403)

                assert client.delete(f"/api/v1/me/academic-profile/attempts/{failed_id}", headers=auth_a).status_code == 204

                assert client.delete("/api/v1/me/academic-profile", headers=auth_a).status_code == 204
                remaining = local.get(f"{URL}/rest/v1/student_course_attempts", headers=admin_headers,
                    params={"select": "id", "id": f"in.({passed_id},{referenced_id})"})
                remaining.raise_for_status(); assert remaining.json() == []
        finally:
            for user_id in user_ids:
                local.delete(f"{URL}/auth/v1/admin/users/{user_id}", headers=admin_headers)
