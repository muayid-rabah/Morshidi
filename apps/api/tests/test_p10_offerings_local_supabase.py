"""Real Local Supabase Auth/membership isolation for the P10 API boundary."""

from __future__ import annotations

from uuid import uuid4
from time import perf_counter
import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.offerings.fake_provider import FAKE_PERIOD, FAKE_UNIVERSITY_ID, FakeUniversityOfferingProvider, fake_snapshot
from app.offerings.simulation import fingerprint
from tests.p10_synthetic_fixture import (
    PERIOD_ID, seed_catalog, synthetic_p6_demand, synthetic_principals,
)
from tests.test_decision_trace_persistence_service_local_supabase import (
    ANON_KEY, SERVER_KEY, URL, _create_user, _plan_scope, _server_headers,
)

pytestmark = pytest.mark.skipif(not all((URL, SERVER_KEY, ANON_KEY)),
                                reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values")


def test_p10_fictional_tenant_real_auth_provider_lifecycle():
    """Repeated local runs reuse catalog identities and remove ephemeral principals."""
    with httpx.Client(timeout=35) as raw:
        seed_catalog(raw)
        seed_catalog(raw)
        with synthetic_principals(raw) as principal:
            student_headers = {"Authorization": f"Bearer {principal['student']}"}
            analyst_headers = {"Authorization": f"Bearer {principal['analyst']}"}
            outsider_headers = {"Authorization": f"Bearer {principal['outsider']}"}
            provider = FakeUniversityOfferingProvider()
            original = fingerprint(fake_snapshot())
            params = {"university_id": FAKE_UNIVERSITY_ID,
                      "target_period_id": PERIOD_ID, "course_code": "CS101"}
            timings = {}
            with TestClient(app) as client:
                app.state.course_offering_provider = provider

                started = perf_counter()
                student = client.get("/api/v1/me/offerings/CS101",
                                     params={"period_key": FAKE_PERIOD}, headers=student_headers)
                timings["student_http_ms"] = round((perf_counter() - started) * 1000, 2)
                assert student.status_code == 200, student.text
                assert student.json()["source_type"] == "SYNTHETIC"
                assert "SYNTHETIC" in student.json()["provenance"]
                assert student.json()["operational_state"] == "SECTION_OPEN"
                assert len(student.json()["sections"]) == 2
                unknown = client.get("/api/v1/me/offerings/HIST101",
                                     params={"period_key": FAKE_PERIOD}, headers=student_headers)
                assert unknown.status_code == 200, unknown.text
                assert unknown.json()["operational_state"] == "SECTION_UNKNOWN_CAPACITY"
                assert unknown.json()["sections"][0]["capacity"] is None
                assert client.get("/api/v1/institutional/capacity", params=params,
                                  headers=student_headers).status_code == 403
                foreign_student = client.get("/api/v1/me/offerings/CS101",
                                             params={"period_key": FAKE_PERIOD},
                                             headers=outsider_headers)
                assert foreign_student.status_code == 200, foreign_student.text
                assert foreign_student.json()["operational_state"] == "PROVIDER_UNAVAILABLE"
                assert foreign_student.json()["sections"] == []
                assert client.get("/api/v1/institutional/capacity", params=params,
                                  headers=outsider_headers).status_code == 403

                started = perf_counter()
                capacity = client.get("/api/v1/institutional/capacity", params=params,
                                      headers=analyst_headers)
                timings["capacity_http_ms"] = round((perf_counter() - started) * 1000, 2)
                assert capacity.status_code == 200, capacity.text
                assert capacity.json()["source_type"] == "SYNTHETIC"
                assert capacity.json()["demand_status"] in {"INSUFFICIENT_DATA", "SUPPRESSED"}
                assert capacity.json()["observed_intent_demand"] is None
                assert capacity.json()["seat_gap"] is None

                # The DB remains free of immutable P6 test intents. Feed real P6
                # aggregate outputs through the same JWT/analyst-gated route.
                original_demand_service = app.state.institutional_demand_service

                class SyntheticAggregateService:
                    def __init__(self, owners):
                        self.aggregate = synthetic_p6_demand(owners)

                    async def demand(self, subject, *, university_id, target_period_id):
                        assert str(university_id) == FAKE_UNIVERSITY_ID
                        assert str(target_period_id) == PERIOD_ID
                        return SimpleNamespace(demand=self.aggregate)

                try:
                    app.state.institutional_demand_service = SyntheticAggregateService(2)
                    disclosed = client.get("/api/v1/institutional/capacity", params=params,
                                           headers=analyst_headers)
                    assert disclosed.status_code == 200, disclosed.text
                    assert disclosed.json()["demand_status"] == "AVAILABLE"
                    assert disclosed.json()["observed_intent_demand"] == 2
                    assert disclosed.json()["seat_gap"] == -58
                    assert "p10-ephemeral-owner" not in disclosed.text

                    app.state.institutional_demand_service = SyntheticAggregateService(1)
                    suppressed = client.get("/api/v1/institutional/capacity", params=params,
                                            headers=analyst_headers)
                    assert suppressed.status_code == 200, suppressed.text
                    assert suppressed.json()["status"] == "SUPPRESSED"
                    assert suppressed.json()["observed_intent_demand"] is None
                    assert suppressed.json()["supplied_section_capacity"] is None
                    assert suppressed.json()["seat_gap"] is None
                    suppressed_scenario = client.post(
                        "/api/v1/institutional/capacity/simulation",
                        json={**params, "kind": "CHANGE_CAPACITY",
                              "section_id": "SYN-CS101-A", "capacity": 40},
                        headers=analyst_headers)
                    assert suppressed_scenario.status_code == 200, suppressed_scenario.text
                    assert suppressed_scenario.json()["modeled_assumed_gap"] is None
                    suppressed_sweep = client.post(
                        "/api/v1/institutional/capacity/sensitivity",
                        json={**params, "kind": "CAPACITY", "section_id": "SYN-CS101-A",
                              "start": 30, "stop": 50, "step": 10}, headers=analyst_headers)
                    assert suppressed_sweep.status_code == 200, suppressed_sweep.text
                    assert all(point["modeled_demand"] is None and point["modeled_gap"] is None
                               for point in suppressed_sweep.json()["points"])
                finally:
                    app.state.institutional_demand_service = original_demand_service

                scenario = {**params, "kind": "CHANGE_CAPACITY",
                            "section_id": "SYN-CS101-A", "capacity": 40}
                started = perf_counter()
                first = client.post("/api/v1/institutional/capacity/simulation",
                                    json=scenario, headers=analyst_headers)
                timings["scenario_http_ms"] = round((perf_counter() - started) * 1000, 2)
                assert first.status_code == 200, first.text
                assert first.json()["modeled_course_seat_delta"] == 10
                replay = client.post("/api/v1/institutional/capacity/simulation",
                                     json=scenario, headers=analyst_headers)
                assert replay.status_code == 200, replay.text
                assert replay.json()["scenario_fingerprint"] == first.json()["scenario_fingerprint"]
                changed = client.post("/api/v1/institutional/capacity/simulation",
                                      json={**scenario, "capacity": 50}, headers=analyst_headers)
                assert changed.status_code == 200, changed.text
                assert changed.json()["scenario_fingerprint"] != first.json()["scenario_fingerprint"]
                for modeled in (
                    {**params, "kind": "ADD_SECTION", "section_id": "MODELLED-CS101-C", "capacity": 20},
                    {**params, "kind": "SHIFT_TIME", "section_id": "SYN-CS101-A",
                     "day": 2, "starts_at": "12:00", "ends_at": "14:00"},
                    {**params, "kind": "COURSE_NOT_AVAILABLE_IN_MODELED_PERIOD", "section_id": ""},
                ):
                    result = client.post("/api/v1/institutional/capacity/simulation",
                                         json=modeled, headers=analyst_headers)
                    assert result.status_code == 200, result.text

                started = perf_counter()
                sweep = client.post("/api/v1/institutional/capacity/sensitivity",
                                    json={**params, "kind": "CAPACITY", "section_id": "SYN-CS101-A",
                                          "start": 30, "stop": 50, "step": 10},
                                    headers=analyst_headers)
                timings["sensitivity_http_ms"] = round((perf_counter() - started) * 1000, 2)
                assert sweep.status_code == 200, sweep.text
                assert [p["assumption_value"] for p in sweep.json()["points"]] == [30, 40, 50]
                assert all(p["modeled_demand"] is None and p["modeled_gap"] is None
                           for p in sweep.json()["points"])
                assert fingerprint(asyncio.run(provider.load_snapshot(FAKE_UNIVERSITY_ID, FAKE_PERIOD))) == original

                class StaleProvider:
                    async def load_snapshot(self, university_id, period_key):
                        return fake_snapshot(stale=True)

                app.state.course_offering_provider = StaleProvider()
                stale = client.get("/api/v1/me/offerings/CS101",
                                   params={"period_key": FAKE_PERIOD}, headers=student_headers)
                assert stale.status_code == 200 and stale.json()["operational_state"] == "SNAPSHOT_STALE"
                stale_capacity = client.get("/api/v1/institutional/capacity", params=params,
                                            headers=analyst_headers)
                assert stale_capacity.status_code == 200
                assert stale_capacity.json()["freshness_status"] == "STALE"

                app.state.course_offering_provider = provider
                unavailable = client.get("/api/v1/me/offerings/CS101",
                                         params={"period_key": "NOT-A-PROVIDER-PERIOD"},
                                         headers=student_headers)
                assert unavailable.status_code == 200
                assert unavailable.json()["operational_state"] == "PROVIDER_UNAVAILABLE"

                class CrossScopedProvider:
                    async def load_snapshot(self, university_id, period_key):
                        from dataclasses import replace
                        return replace(fake_snapshot(), university_id=str(uuid4()))

                app.state.course_offering_provider = CrossScopedProvider()
                cross_scope = client.get("/api/v1/institutional/capacity", params=params,
                                         headers=analyst_headers)
                assert cross_scope.status_code == 503
                app.state.course_offering_provider = provider
            print("P10 local HTTP/service timings (ms):", timings)
        for table, column, identifier in (
            ("student_academic_profiles", "owner_user_id", principal["student_id"]),
            ("student_academic_profiles", "owner_user_id", principal["outsider_id"]),
            ("institutional_memberships", "subject_user_id", principal["analyst_id"]),
        ):
            rows = raw.get(f"{URL}/rest/v1/{table}", headers=_server_headers(),
                           params={"select": "id", column: f"eq.{identifier}"})
            assert rows.status_code == 200 and rows.json() == []


def test_real_auth_analyst_gate_cross_tenant_and_no_synthetic_leak():
    marker = uuid4().hex
    namespace = f"p10-{marker}"
    with httpx.Client(timeout=35) as raw:
        plan, university = _plan_scope(raw)
        plan_courses = raw.get(f"{URL}/rest/v1/study_plan_courses", headers=_server_headers(),
                               params={"select": "course_id", "study_plan_id": f"eq.{plan}", "limit": "1"})
        assert plan_courses.status_code == 200 and plan_courses.json()
        course_row = raw.get(f"{URL}/rest/v1/courses", headers=_server_headers(),
                             params={"select": "course_code", "id": f"eq.{plan_courses.json()[0]['course_id']}"})
        assert course_row.status_code == 200 and course_row.json()
        course_code = course_row.json()[0]["course_code"]
        analyst, analyst_token = _create_user(raw, "p10-analyst")
        outsider, outsider_token = _create_user(raw, "p10-outsider")
        student, student_token = _create_user(raw, "p10-student")
        profile = raw.post(f"{URL}/rest/v1/student_academic_profiles", headers=_server_headers(),
                           json={"owner_user_id": student, "study_plan_id": plan})
        assert profile.status_code == 201, profile.text
        period = raw.post(f"{URL}/rest/v1/mock_registration_target_periods",
                          headers=_server_headers(), json={
                              "university_id": university, "provider_namespace": namespace,
                              "period_key": marker, "period_class": "SYNTHETIC_SANDBOX_PERIOD",
                              "verified_provider_source": False, "source_version": "p10-local-test:v1",
                          })
        assert period.status_code == 201, period.text
        period_id = period.json()[0]["id"]
        membership = raw.post(f"{URL}/rest/v1/institutional_memberships",
                              headers=_server_headers(), json={
                                  "subject_user_id": analyst, "university_id": university,
                                  "provider_namespace": namespace, "role": "INSTITUTIONAL_ANALYST",
                                  "active": True, "authority_source": "P10_LOCAL_TEST",
                                  "authority_source_version": "v1",
                              })
        assert membership.status_code == 201, membership.text
        path = "/api/v1/institutional/capacity"
        params = {"university_id": university, "target_period_id": period_id,
                  "course_code": "CS101"}
        with TestClient(app) as client:
            student_view = client.get(f"/api/v1/me/offerings/{course_code}",
                                      params={"period_key": marker},
                                      headers={"Authorization": f"Bearer {student_token}"})
            assert student_view.status_code == 200, student_view.text
            assert student_view.headers["Cache-Control"] == "private, no-store"
            assert student_view.json()["operational_state"] == "PROVIDER_UNAVAILABLE"
            assert student_view.json()["sections"] == []
            assert student not in student_view.text
            outsider_student = client.get(f"/api/v1/me/offerings/{course_code}",
                                          params={"period_key": marker},
                                          headers={"Authorization": f"Bearer {outsider_token}"})
            assert outsider_student.status_code == 404
            no_auth = client.get(path, params=params)
            assert no_auth.status_code == 401
            denied = client.get(path, params=params,
                                headers={"Authorization": f"Bearer {outsider_token}"})
            assert denied.status_code == 403
            foreign = client.get(path, params={**params, "university_id": str(uuid4())},
                                 headers={"Authorization": f"Bearer {analyst_token}"})
            assert foreign.status_code == 403
            response = client.get(path, params=params,
                                  headers={"Authorization": f"Bearer {analyst_token}"})
            assert response.status_code == 200, response.text
            assert response.headers["Cache-Control"] == "private, no-store"
            assert response.json()["status"] == "PROVIDER_UNAVAILABLE"
            assert response.json()["supplied_section_capacity"] is None
            assert response.json()["provenance"] is None
            assert analyst not in response.text and outsider not in response.text
            cannot_model = client.post(f"{path}/simulation", headers={
                "Authorization": f"Bearer {analyst_token}"}, json={
                    "university_id": university, "target_period_id": period_id,
                    "kind": "ADD_SECTION", "section_id": "MODELLED-CS101-A",
                    "course_code": "CS101", "capacity": 30,
                })
            assert cannot_model.status_code == 409
