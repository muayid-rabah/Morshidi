"""WC-046 typed HTTP contract and authenticated endpoint tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.routes.change_impact import get_change_impact_service
from app.change_impact.engine import evaluate_change_impact
from app.core.auth import CurrentUser, get_current_user
from app.main import app
from tests.test_change_impact_engine import TENANT, _policy


ACTOR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
STUDENT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class FakeService:
    def __init__(self):
        self.calls = []

    async def available_analyst_universities(self, actor):
        self.calls.append(("access", actor))
        return (TENANT,)

    async def evaluate_institutional(self, actor, delta, *, university_id=None):
        self.calls.append(("analyst", actor, delta, university_id))
        return evaluate_change_impact(delta, university_id=TENANT).model_copy(
            update={"audit_status": "LEDGER_PERSISTED"})

    async def evaluate_advisor(self, actor, student, delta):
        self.calls.append(("advisor", actor, student, delta))
        return evaluate_change_impact(delta, university_id=TENANT).model_copy(
            update={"audit_status": "LEDGER_PERSISTED"})


@pytest.fixture
def api():
    service = FakeService()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(ACTOR)
    app.dependency_overrides[get_change_impact_service] = lambda: service
    with TestClient(app) as client:
        yield client, service
    app.dependency_overrides.clear()


def test_both_change_impact_routes_require_authentication():
    app.dependency_overrides.clear()
    body = {"delta": _policy().model_dump(mode="json")}
    with TestClient(app) as client:
        assert client.post("/api/v1/institutional/change-impact/evaluate", json=body).status_code == 401
        assert client.get("/api/v1/institutional/change-impact/access").status_code == 401
        assert client.post(f"/api/v1/advisor/students/{STUDENT}/change-impact/evaluate",
                           json=body).status_code == 401


def test_analyst_access_and_evaluation_use_authenticated_principal(api):
    client, service = api
    access = client.get("/api/v1/institutional/change-impact/access")
    response = client.post("/api/v1/institutional/change-impact/evaluate",
                           json={"university_id": str(TENANT),
                                 "delta": _policy().model_dump(mode="json")})
    assert access.status_code == 200 and access.json()["university_ids"] == [str(TENANT)]
    assert response.status_code == 200, response.text
    assert response.json()["change_authority"] == "PROPOSED_ANALYST_CHANGE"
    assert response.json()["audit_status"] == "LEDGER_PERSISTED"
    assert service.calls[1][1] == ACTOR and service.calls[1][3] == TENANT


def test_advisor_target_comes_only_from_route(api):
    client, service = api
    response = client.post(f"/api/v1/advisor/students/{STUDENT}/change-impact/evaluate",
                           json={"delta": _policy().model_dump(mode="json")})
    assert response.status_code == 200
    assert service.calls[0][2] == UUID(STUDENT)


def test_unknown_and_client_controlled_audit_fields_are_rejected(api):
    client, service = api
    path = "/api/v1/institutional/change-impact/evaluate"
    delta = _policy().model_dump(mode="json")
    assert client.post(path, json={"delta": {**delta, "change_type": "ARBITRARY"}}).status_code == 422
    for name in ("ledger_entry_id", "integrity_hash", "actor_class", "outcome_reference", "evidence"):
        assert client.post(path, json={"delta": {**delta, name: "client"}}).status_code == 422
    assert client.post(path, json={"delta": delta, "student_user_id": STUDENT}).status_code == 422
    assert client.post(f"/api/v1/advisor/students/{STUDENT}/change-impact/evaluate",
                       json={"delta": delta, "university_id": str(TENANT)}).status_code == 422
    assert not service.calls
