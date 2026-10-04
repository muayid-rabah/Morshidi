"""Real Local Supabase ownership, advisor assignment, tenant, and analyst denial."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_decision_trace_persistence_service_local_supabase import (
    ANON_KEY, SERVER_KEY, URL, _assignment, _create_profile, _create_user,
    _membership, _plan_scope, _server_headers,
)
from tests.test_decision_trace_persistence_local_supabase import _foreign_university_id


pytestmark = pytest.mark.skipif(
    not all((URL, ANON_KEY, SERVER_KEY)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values",
)


def test_local_student_and_exact_assigned_advisor_graphs_with_denial_matrix():
    with httpx.Client(timeout=30) as raw:
        plan_id, university_id = _plan_scope(raw)
        student, student_token = _create_user(raw, "graph-student")
        other_student, other_token = _create_user(raw, "graph-other")
        advisor, advisor_token = _create_user(raw, "graph-advisor")
        unassigned, unassigned_token = _create_user(raw, "graph-unassigned")
        inactive, inactive_token = _create_user(raw, "graph-inactive")
        analyst, analyst_token = _create_user(raw, "graph-analyst")
        foreign, foreign_token = _create_user(raw, "graph-foreign")
        _create_profile(raw, student, plan_id)
        _create_profile(raw, other_student, plan_id)
        for principal in (advisor, unassigned, inactive):
            _membership(raw, principal, university_id, "ACADEMIC_ADVISOR")
        _membership(raw, analyst, university_id, "INSTITUTIONAL_ANALYST")
        _membership(raw, foreign, _foreign_university_id(raw), "ACADEMIC_ADVISOR")
        _assignment(raw, advisor, student, university_id)
        inactive_assignment = _assignment(raw, inactive, student, university_id)
        disabled = raw.patch(
            f"{URL}/rest/v1/advisor_student_assignments",
            headers=_server_headers(), params={"id": f"eq.{inactive_assignment}"},
            json={"is_active": False},
        )
        assert disabled.status_code in (200, 204), disabled.text

    student_headers = {"Authorization": f"Bearer {student_token}"}
    advisor_headers = {"Authorization": f"Bearer {advisor_token}"}
    with TestClient(app) as client:
        rec = client.get("/api/v1/me/course-recommendations/explanation-graph?limit=3",
                         headers=student_headers)
        assert rec.status_code == 200, rec.text
        assert rec.json()["policy_versions"] and rec.json()["source_versions"] == []
        planner_body = {"max_credit_hours": "15", "max_courses": 5, "max_options": 1}
        planner = client.post("/api/v1/me/semester-plans/explanation-graph",
                              headers=student_headers, json=planner_body)
        assert planner.status_code == 200, planner.text
        path_body = {"max_credit_hours_per_semester": "15", "max_courses_per_semester": 5,
                     "max_semesters_ahead": 1, "max_paths": 1}
        path = client.post("/api/v1/me/degree-paths/explanation-graph",
                           headers=student_headers, json=path_body)
        assert path.status_code == 200, path.text
        base = f"/api/v1/advisor/students/{student}"
        advisor_routes = (
            client.get(base + "/eligibility/0200115/explanation-graph", headers=advisor_headers),
            client.get(base + "/course-recommendations/explanation-graph?limit=3", headers=advisor_headers),
            client.post(base + "/semester-plans/explanation-graph", headers=advisor_headers, json=planner_body),
            client.post(base + "/degree-paths/explanation-graph", headers=advisor_headers, json=path_body),
        )
        assert all(response.status_code == 200 for response in advisor_routes), [
            response.status_code for response in advisor_routes
        ]
        for response in (rec, planner, path, *advisor_routes):
            body = str(response.json())
            assert student not in body and other_student not in body and advisor not in body
        for token in (unassigned_token, inactive_token, analyst_token, foreign_token):
            denied = client.get(base + "/course-recommendations/explanation-graph",
                                headers={"Authorization": f"Bearer {token}"})
            assert denied.status_code == 403
            assert denied.json() == {"detail": "Advisor graph access denied"}
        assert client.get(f"/api/v1/advisor/students/{other_student}/course-recommendations/explanation-graph",
                          headers=advisor_headers).status_code == 403
        assert client.get(base + "/course-recommendations/explanation-graph",
                          headers={"Authorization": f"Bearer {other_token}"}).status_code == 403
