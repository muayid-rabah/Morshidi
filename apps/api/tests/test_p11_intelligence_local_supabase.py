"""Real Local Supabase Auth, membership, ownership and aggregate-only P11 route proof."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.offerings.fake_provider import FAKE_UNIVERSITY_ID
from app.p11_intelligence.fake_provider import FAKE_PLAN_ID
from tests.p10_synthetic_fixture import seed_catalog, synthetic_principals
from tests.test_decision_trace_persistence_service_local_supabase import ANON_KEY, SERVER_KEY, URL

pytestmark = pytest.mark.skipif(not all((URL, SERVER_KEY, ANON_KEY)),
                                reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values")


def test_p11_real_auth_owner_scope_analyst_gate_and_no_raw_cohort_rows():
    with httpx.Client(timeout=35) as raw:
        seed_catalog(raw)
        with synthetic_principals(raw) as principals:
            student = {"Authorization": f"Bearer {principals['student']}"}
            analyst = {"Authorization": f"Bearer {principals['analyst']}"}
            outsider = {"Authorization": f"Bearer {principals['outsider']}"}
            scope = {"university_id": FAKE_UNIVERSITY_ID, "study_plan_id": FAKE_PLAN_ID,
                     "entry_period": "SYN-2025-FALL", "period": "SYN-2026-FALL"}
            with TestClient(app) as client:
                assert client.get("/api/v1/me/intelligence").status_code == 401
                owner = client.get("/api/v1/me/intelligence", headers=student)
                assert owner.status_code == 200, owner.text
                assert owner.json()["skills"]["status"] == "AVAILABLE"
                assert owner.json()["risk"] == "NOT_EXPOSED_TO_STUDENTS"
                foreign = client.get("/api/v1/me/intelligence", headers=outsider)
                assert foreign.status_code == 200, foreign.text
                assert foreign.json()["source_type"] == "UNAVAILABLE"
                assert client.get("/api/v1/institutional/cohorts", params=scope, headers=student).status_code == 403
                assert client.get("/api/v1/institutional/cohorts", params=scope, headers=outsider).status_code == 403
                allowed = client.get("/api/v1/institutional/cohorts", params=scope, headers=analyst)
                assert allowed.status_code == 200, allowed.text
                assert allowed.json()["status"] == "AVAILABLE" and allowed.json()["size"] == 6
                assert "anonymous-" not in allowed.text
                assert allowed.headers["cache-control"] == "private, no-store"
                app.state.p11_cohort_threshold = 7
                suppressed = client.get("/api/v1/institutional/cohorts", params=scope, headers=analyst)
                assert suppressed.status_code == 200 and suppressed.json()["status"] == "SUPPRESSED"
                assert suppressed.json()["size"] is None and suppressed.json()["metrics"] is None
