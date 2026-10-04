"""Authenticated answer endpoint with synthetic evidence and an empty corpus."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.api.routes.policies import get_policy_answer_service, get_student_service
from app.core.auth import CurrentUser, get_current_user
from app.institutional_policy.answering import PolicyAnswerService
from app.institutional_policy.service import InMemoryPolicyReadStorage, StudentPolicyService
from app.main import app
from app.services.student import StudentService
from tests.test_policy_answering import FakePolicies, FakeProvider, UNIVERSITY, WITHDRAWAL, answered
from tests.test_policy_api import DummyStudentRepository


USER = "20000000-0000-0000-0000-000000000001"


@pytest.fixture
def answer_client():
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=USER)
    app.dependency_overrides[get_student_service] = lambda: StudentService(
        repository=DummyStudentRepository({USER: UNIVERSITY}),
        eligibility=None,
        catalog_repository=None,
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_current_production_like_empty_corpus_abstains_without_generation(answer_client):
    provider = FakeProvider(answered())
    app.dependency_overrides[get_policy_answer_service] = lambda: PolicyAnswerService(
        StudentPolicyService(InMemoryPolicyReadStorage()), provider
    )
    response = answer_client.post("/api/v1/me/policies/answer", json={
        "question": "ما سياسة الانسحاب من المساق؟"
    })
    assert response.status_code == 200
    assert response.json() == {
        "status": "ABSTAINED", "answer": None, "language": "ar", "citations": [],
        "retrieval_mode": "hybrid", "abstention_reason": "NO_VERIFIED_POLICY_EVIDENCE",
        "handoff": None,
    }
    assert provider.calls == []


def test_answer_endpoint_returns_only_server_constructed_exact_citation(answer_client):
    provider = FakeProvider(answered())
    app.dependency_overrides[get_policy_answer_service] = lambda: PolicyAnswerService(
        FakePolicies((WITHDRAWAL,)), provider
    )
    response = answer_client.post("/api/v1/me/policies/answer", json={
        "question": "ما سياسة الانسحاب؟", "limit": 6,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ANSWERED" and body["answer"]
    assert len(body["citations"]) == 1
    assert body["citations"][0]["passage_text"] == WITHDRAWAL["passage_text"]
    assert body["citations"][0]["passage_sha256"] == WITHDRAWAL["passage_sha256"]
    assert "semantic_similarity" not in body["citations"][0]
    assert "university_id" not in body


def test_handoff_endpoint_never_calls_generation(answer_client):
    policies = FakePolicies((WITHDRAWAL,))
    provider = FakeProvider(answered())
    app.dependency_overrides[get_policy_answer_service] = lambda: PolicyAnswerService(policies, provider)
    response = answer_client.post("/api/v1/me/policies/answer", json={
        "question": "هل يمكنني تسجيل مادة الذكاء الاصطناعي؟"
    })
    assert response.status_code == 200
    assert response.json()["status"] == "HANDOFF_REQUIRED"
    assert response.json()["handoff"]["target_engine"] == "ELIGIBILITY_ENGINE"
    assert response.json()["answer"] is None and response.json()["citations"] == []
    assert policies.calls == provider.calls == []


@pytest.mark.parametrize("body", [
    {"question": " "}, {"question": "??"}, {"question": "a" * 501},
    {"question": "withdrawal", "limit": 9},
    {"question": "withdrawal", "university_id": UNIVERSITY},
])
def test_answer_request_rejects_invalid_or_client_tenant_input(answer_client, body):
    app.dependency_overrides[get_policy_answer_service] = lambda: PolicyAnswerService(
        StudentPolicyService(InMemoryPolicyReadStorage())
    )
    assert answer_client.post("/api/v1/me/policies/answer", json=body).status_code == 422


def test_answer_endpoint_requires_authentication():
    with TestClient(app) as client:
        assert client.post("/api/v1/me/policies/answer", json={
            "question": "What is the withdrawal policy?"
        }).status_code == 401
