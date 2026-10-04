"""Authenticated owner-only eligibility graph route tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.test_student_api import OWNER, api, attempt


def test_requires_verified_auth_and_never_takes_student_or_tenant_scope():
    with TestClient(app) as client:
        assert client.get("/api/v1/me/eligibility/1501112/explanation-graph").status_code == 401


def test_own_graph_eligible_not_eligible_and_review(api):
    client, service = api
    from dataclasses import replace
    service.state = replace(service.state, attempts=(attempt(code="1501110"),))
    path = "/api/v1/me/eligibility/1501112/explanation-graph"
    eligible = client.get(path)
    assert eligible.status_code == 200
    assert eligible.json()["nodes"][0]["id"]
    assert eligible.json()["subject_reference"] == "1501112"
    assert eligible.json()["source_versions"] == []
    assert any(node["decision"] == "ELIGIBLE" for node in eligible.json()["nodes"])
    assert OWNER not in str(eligible.json())
    assert "student_user_id" not in str(eligible.json())
    service.state = replace(service.state, attempts=())
    blocked = client.get(path)
    assert blocked.status_code == 200 and blocked.json()["nodes"]
    assert any(node["decision"] == "NOT_ELIGIBLE" for node in blocked.json()["nodes"])
    review = client.get("/api/v1/me/eligibility/1505311/explanation-graph")
    assert review.status_code == 200
    assert any(node["decision"] == "REVIEW_REQUIRED" for node in review.json()["nodes"])


def test_why_not_is_bounded_to_existing_eligible_blockers(api):
    client, service = api
    from dataclasses import replace
    service.state = replace(service.state, attempts=())
    path = "/api/v1/me/eligibility/1501112/explanation-graph"
    result = client.get(path + "?mode=why_not&target=ELIGIBLE")
    assert result.status_code == 200 and result.json()["mode"] == "why_not"
    assert result.json()["target_decision"] == "ELIGIBLE"
    assert client.get(path + "?mode=why_not&target=NOT_ELIGIBLE").status_code == 422
    assert client.get(path + "?mode=unknown").status_code == 422
    assert client.get(path + "?target=ELIGIBLE").status_code == 422
    service.missing = True
    assert client.get(path).status_code == 404
    service.missing = False
    assert client.get("/api/v1/me/eligibility/unknown/explanation-graph").status_code == 404


def test_no_mutation_endpoint_or_arbitrary_context(api):
    client, _ = api
    path = "/api/v1/me/eligibility/1501112/explanation-graph"
    for method in (client.post, client.patch, client.delete):
        assert method(path).status_code == 405
    assert client.get(path + "?student_user_id=11111111-1111-1111-1111-111111111111").status_code == 422
    assert client.get(path + "?university_id=anything").status_code == 422
