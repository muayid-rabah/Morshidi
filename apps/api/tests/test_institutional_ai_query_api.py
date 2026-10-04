"""WC-039 authenticated HTTP request/response minimization."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes.institutional_ai_query import get_query_service
from app.core.auth import CurrentUser, get_current_user
from app.main import app
from tests.test_institutional_ai_query import ACTOR, TENANT, request


class FakeService:
    def __init__(self):
        self.calls = []

    async def available_analyst_universities(self, actor):
        self.calls.append(("access", actor))
        return (TENANT,)

    async def evaluate(self, actor, body):
        self.calls.append(("evaluate", actor, body))
        from app.institutional_ai_query.models import InstitutionalAIQueryResponse, QueryStatus
        return InstitutionalAIQueryResponse(status=QueryStatus.ABSTAINED,
                                            abstention_reason="NO_APPROVED_METRIC")


@pytest.fixture
def api():
    service = FakeService()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(ACTOR)
    app.dependency_overrides[get_query_service] = lambda: service
    with TestClient(app) as client:
        yield client, service
    app.dependency_overrides.clear()


def test_unauthenticated_request_is_rejected():
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        assert client.post("/api/v1/institutional/ai-query",
                           json=request().model_dump(mode="json")).status_code == 401


def test_access_and_evaluate_use_verified_principal(api):
    client, service = api
    assert client.get("/api/v1/institutional/ai-query/access").json()["university_ids"] == [str(TENANT)]
    response = client.post("/api/v1/institutional/ai-query",
                           json=request().model_dump(mode="json"))
    assert response.status_code == 200 and response.json()["status"] == "ABSTAINED"
    assert service.calls[1][1] == ACTOR


@pytest.mark.parametrize("field,value", [
    ("student_user_id", ACTOR), ("sql", "SELECT 1"), ("filters", []),
    ("metric_id", "INST_SIG_DECLARED_DEMAND_COUNT"), ("table", "students"),
    ("where", "true"),
])
def test_browser_cannot_submit_arbitrary_execution_fields(api, field, value):
    client, service = api
    response = client.post("/api/v1/institutional/ai-query",
                           json={**request().model_dump(mode="json"), field: value})
    assert response.status_code == 422 and not service.calls


def test_question_and_course_bounds_are_enforced(api):
    client, service = api
    body = request().model_dump(mode="json")
    for changed in ({"question": "short"}, {"question": "x" * 301},
                    {"course_code": "CS101; DROP TABLE students"}):
        assert client.post("/api/v1/institutional/ai-query",
                           json={**body, **changed}).status_code == 422
    assert not service.calls
