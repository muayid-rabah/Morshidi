"""Real Local Supabase owner context for the read-only eligibility graph."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_decision_trace_persistence_service_local_supabase import (
    ANON_KEY, SERVER_KEY, URL, _create_profile, _create_user, _plan_scope,
)


pytestmark = pytest.mark.skipif(
    not all((URL, ANON_KEY, SERVER_KEY)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values",
)


def test_local_owned_profile_graph_uses_real_catalog_and_verified_auth():
    with httpx.Client(timeout=30) as raw:
        plan_id, _ = _plan_scope(raw)
        owner_id, owner_token = _create_user(raw, "wc007-owner")
        stranger_id, stranger_token = _create_user(raw, "wc007-stranger")
        _create_profile(raw, owner_id, plan_id)

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {owner_token}"}
        base = "/api/v1/me/eligibility"
        eligible = client.get(f"{base}/0200115/explanation-graph", headers=headers)
        blocked = client.get(f"{base}/1501112/explanation-graph?mode=why_not", headers=headers)
        review = client.get(f"{base}/1505311/explanation-graph", headers=headers)
        assert eligible.status_code == 200
        assert any(node["decision"] == "ELIGIBLE" for node in eligible.json()["nodes"])
        assert blocked.status_code == 200
        assert blocked.json()["mode"] == "why_not"
        assert any(node["decision"] == "NOT_ELIGIBLE" for node in blocked.json()["nodes"])
        assert review.status_code == 200
        assert any(node["decision"] == "REVIEW_REQUIRED" for node in review.json()["nodes"])
        for body in (eligible.json(), blocked.json(), review.json()):
            assert owner_id not in str(body) and stranger_id not in str(body)
            assert body["source_versions"] == []
        stranger = client.get(f"{base}/1501112/explanation-graph",
                              headers={"Authorization": f"Bearer {stranger_token}"})
        assert stranger.status_code == 404
