"""Tests for student-facing policy API endpoints (WC-038).

AI EXPLAINS — DETERMINISTIC RULES DECIDE.
Verifies:
- Listing verified policy documents for the student's university.
- Viewing document detail with active verified version and cited passages.
- Cross-university tenant isolation (404 on other university documents).
- Filtering out unverified / superseded documents from student view.
- 401 when unauthenticated.
- Honest empty list when student has no profile.
"""

from __future__ import annotations

import uuid
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.api.routes.policies import get_policy_service, get_student_service
from app.core.auth import CurrentUser, get_current_user
from app.institutional_policy.service import (
    InMemoryPolicyReadStorage,
    StudentPolicyService,
)
from app.main import app
from app.services.student import StudentService
from app.student.errors import StudentProfileNotFound


class DummyStudentRepository:
    def __init__(self, university_map: dict[str, str] | None = None) -> None:
        self.university_map = university_map or {}

    async def resolve_student_university_id(self, owner: str) -> str:
        if owner not in self.university_map:
            raise StudentProfileNotFound("Student profile not found")
        return self.university_map[owner]


@pytest.fixture
def mock_policy_env():
    univ_a = "10000000-0000-0000-0000-000000000001"
    univ_b = "10000000-0000-0000-0000-000000000002"

    doc_a1_id = str(uuid.uuid4())
    doc_a2_id = str(uuid.uuid4())  # Unverified document
    doc_b1_id = str(uuid.uuid4())  # Belongs to Univ B

    ver_a1_id = str(uuid.uuid4())
    ver_a2_id = str(uuid.uuid4())
    ver_b1_id = str(uuid.uuid4())

    documents = [
        {
            "id": doc_a1_id,
            "university_id": univ_a,
            "document_code": "BYLAW-A1",
            "title": "تعليمات البكالوريوس جامعة أ",
            "authority_level": "university_council",
            "category": "academic_bylaws",
            "language": "ar",
        },
        {
            "id": doc_a2_id,
            "university_id": univ_a,
            "document_code": "BYLAW-A2-DRAFT",
            "title": "مسودة لائحة غير معتمدة",
            "authority_level": "department_council",
            "category": "examination_regulations",
            "language": "ar",
        },
        {
            "id": doc_b1_id,
            "university_id": univ_b,
            "document_code": "BYLAW-B1",
            "title": "تعليمات جامعة ب",
            "authority_level": "university_council",
            "category": "academic_bylaws",
            "language": "ar",
        },
    ]

    versions = [
        {
            "id": ver_a1_id,
            "document_id": doc_a1_id,
            "version_tag": "1.0",
            "status": "verified",
            "effective_start_date": "2026-09-01T00:00:00Z",
            "content_sha256": "a" * 64,
            "verified_at": "2026-09-01T00:00:00Z",
            "verified_by": "مجلس الجامعة",
        },
        {
            "id": ver_a2_id,
            "document_id": doc_a2_id,
            "version_tag": "0.1",
            "status": "unverified",  # NOT verified!
            "effective_start_date": "2026-09-01T00:00:00Z",
            "content_sha256": "b" * 64,
        },
        {
            "id": ver_b1_id,
            "document_id": doc_b1_id,
            "version_tag": "1.0",
            "status": "verified",
            "effective_start_date": "2026-09-01T00:00:00Z",
            "content_sha256": "c" * 64,
            "verified_at": "2026-09-01T00:00:00Z",
            "verified_by": "مجلس الجامعة",
        },
    ]

    passages = [
        {
            "id": str(uuid.uuid4()),
            "version_id": ver_a1_id,
            "passage_text": "المادة 1: تمنح الدرجة بعد استيفاء الخطة.",
            "locator_text": "المادة 1",
            "article_number": "1",
            "sequence_order": 0,
        },
        {
            "id": str(uuid.uuid4()),
            "version_id": ver_a1_id,
            "passage_text": "المادة 2: الحد الأدنى للمعدل التراكمي هو 2.0.",
            "locator_text": "المادة 2",
            "article_number": "2",
            "sequence_order": 1,
        },
        {
            "id": str(uuid.uuid4()),
            "version_id": ver_b1_id,
            "passage_text": "المادة 1: لوائح جامعة ب الخاصة.",
            "locator_text": "المادة 1",
            "article_number": "1",
            "sequence_order": 0,
        },
    ]

    storage = InMemoryPolicyReadStorage(documents, versions, passages)
    policy_service = StudentPolicyService(storage)

    student_user_id = str(uuid.uuid4())
    student_without_profile_id = str(uuid.uuid4())

    student_service = StudentService(
        repository=DummyStudentRepository(university_map={student_user_id: univ_a}),
        eligibility=None,
        catalog_repository=None,
    )

    return {
        "policy_service": policy_service,
        "student_service": student_service,
        "student_user_id": student_user_id,
        "student_without_profile_id": student_without_profile_id,
        "doc_a1_id": doc_a1_id,
        "doc_b1_id": doc_b1_id,
        "univ_a": univ_a,
        "univ_b": univ_b,
    }


def test_list_student_policies_returns_verified_only(mock_policy_env) -> None:
    env = mock_policy_env
    user = CurrentUser(user_id=env["student_user_id"])

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_policy_service] = lambda: env["policy_service"]
    app.dependency_overrides[get_student_service] = lambda: env["student_service"]

    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/me/policies")
            assert resp.status_code == 200
            data = resp.json()

            # Should return exactly 1 document: BYLAW-A1 (BYLAW-A2 is unverified, BYLAW-B1 is for Univ B)
            assert len(data) == 1
            doc = data[0]
            assert doc["document_code"] == "BYLAW-A1"
            assert doc["university_id"] == env["univ_a"]
            assert doc["passage_count"] == 2
            assert doc["active_version_tag"] == "1.0"
    finally:
        app.dependency_overrides.clear()


def test_get_policy_detail_success(mock_policy_env) -> None:
    env = mock_policy_env
    user = CurrentUser(user_id=env["student_user_id"])

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_policy_service] = lambda: env["policy_service"]
    app.dependency_overrides[get_student_service] = lambda: env["student_service"]

    try:
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/me/policies/{env['doc_a1_id']}")
            assert resp.status_code == 200
            data = resp.json()

            assert data["id"] == env["doc_a1_id"]
            assert data["document_code"] == "BYLAW-A1"
            assert data["active_version"]["version_tag"] == "1.0"
            assert len(data["passages"]) == 2
            assert data["passages"][0]["article_number"] == "1"
            assert data["passages"][1]["article_number"] == "2"
    finally:
        app.dependency_overrides.clear()


def test_cross_university_policy_access_returns_404(mock_policy_env) -> None:
    env = mock_policy_env
    user = CurrentUser(user_id=env["student_user_id"])

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_policy_service] = lambda: env["policy_service"]
    app.dependency_overrides[get_student_service] = lambda: env["student_service"]

    try:
        with TestClient(app) as client:
            # Student from Univ A attempts to access Univ B's policy doc_b1_id
            resp = client.get(f"/api/v1/me/policies/{env['doc_b1_id']}")
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_student_without_profile_returns_empty_list(mock_policy_env) -> None:
    env = mock_policy_env
    user = CurrentUser(user_id=env["student_without_profile_id"])

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_policy_service] = lambda: env["policy_service"]
    app.dependency_overrides[get_student_service] = lambda: env["student_service"]

    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/me/policies")
            assert resp.status_code == 200
            assert resp.json() == []
    finally:
        app.dependency_overrides.clear()


def test_unauthenticated_request_returns_401() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/me/policies")
        assert resp.status_code == 401


def _override_policy_dependencies(env: dict[str, Any]) -> None:
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id=env["student_user_id"])
    app.dependency_overrides[get_policy_service] = lambda: env["policy_service"]
    app.dependency_overrides[get_student_service] = lambda: env["student_service"]


@pytest.mark.parametrize(
    "params",
    [
        {"q": ""},
        {"q": "   "},
        {"q": "x" * 241},
        {"q": "BYLAW", "limit": 0},
        {"q": "BYLAW", "limit": 21},
    ],
)
def test_policy_search_rejects_invalid_query_and_limit(params: dict[str, Any], mock_policy_env: dict[str, Any]) -> None:
    _override_policy_dependencies(mock_policy_env)
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/me/policies/search", params=params).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_policy_search_returns_exact_verified_tenant_result_and_stable_order(mock_policy_env: dict[str, Any]) -> None:
    env = mock_policy_env
    _override_policy_dependencies(env)
    try:
        with TestClient(app) as client:
            first = client.get("/api/v1/me/policies/search", params={"q": "\u0627\u0644\u0645\u0627\u062f\u0629", "limit": 10, "university_id": env["univ_b"]})
            second = client.get("/api/v1/me/policies/search", params={"q": "\u0627\u0644\u0645\u0627\u062f\u0629", "limit": 10})
            assert first.status_code == second.status_code == 200
            assert first.json() == second.json()
            rows = first.json()
            assert rows and all(row["document_id"] == env["doc_a1_id"] for row in rows)
            assert all(row["document_code"] == "BYLAW-A1" for row in rows)
            assert rows[0]["passage_text"].startswith("\u0627\u0644\u0645\u0627\u062f\u0629")
            assert rows[0]["locator_text"] == "\u0627\u0644\u0645\u0627\u062f\u0629 1"
            assert rows[0]["article_number"] == "1"
            assert rows[0]["status"] == "verified"
            return
            assert rows[0]["passage_text"].startswith("Ø§Ù„Ù…Ø§Ø¯Ø©")
            assert rows[0]["locator_text"] == "Ø§Ù„Ù…Ø§Ø¯Ø© 1"
            assert rows[0]["article_number"] == "1"
            assert rows[0]["status"] == "verified"
    finally:
        app.dependency_overrides.clear()


def test_policy_search_empty_result_and_unauthenticated_denial(mock_policy_env: dict[str, Any]) -> None:
    _override_policy_dependencies(mock_policy_env)
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/me/policies/search", params={"q": "لا_تطابق"}).json() == []
    finally:
        app.dependency_overrides.clear()
    with TestClient(app) as client:
        assert client.get("/api/v1/me/policies/search", params={"q": "BYLAW"}).status_code == 401


def test_policy_without_embedding_credentials_keeps_browsing_and_lexical_search(mock_policy_env: dict[str, Any]) -> None:
    _override_policy_dependencies(mock_policy_env)
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/me/policies").status_code == 200
            assert client.get("/api/v1/me/policies/search", params={"q": "BYLAW", "mode": "lexical"}).status_code == 200
            semantic = client.get("/api/v1/me/policies/search", params={"q": "BYLAW", "mode": "semantic"})
            assert semantic.status_code == 503
            assert semantic.json() == {"detail": "Semantic policy search is temporarily unavailable"}
    finally:
        app.dependency_overrides.clear()
