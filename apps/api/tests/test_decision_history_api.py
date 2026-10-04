"""Authenticated, read-only Decision History API projection tests."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.decision_history import get_decision_trace_service
from app.core.auth import CurrentUser, get_current_user
from app.main import app
from tests.test_decision_history import (
    OTHER, STUDENT, UNIVERSITY, Repository, Scope, entry,
)
from app.decision_trace import RedactionProfile
from app.decision_trace_persistence import DecisionTraceService


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(STUDENT))
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def configure(*rows, university=UNIVERSITY):
    service = DecisionTraceService(Repository(rows), Scope(university), None)
    app.dependency_overrides[get_decision_trace_service] = lambda: service


def test_empty_history_is_exact_empty_array(client):
    configure()
    response = client.get("/api/v1/me/decision-history")
    assert response.status_code == 200 and response.json() == []


def test_list_and_detail_are_allowlisted_and_student_scoped(client):
    own = entry()
    configure(own, entry(student=OTHER), entry(profile=RedactionProfile.ADVISOR_SAFE))
    listed = client.get("/api/v1/me/decision-history")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["ledger_entry_id"] == own.ledger_entry_id
    assert "actor_id" not in listed.json()[0]
    assert "integrity_hash" not in listed.json()[0]
    detail = client.get(f"/api/v1/me/decision-history/{own.ledger_entry_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["integrity_status"] == "VERIFIED"
    assert body["source_versions"] == ["catalog:v1", "policy:v1"]
    assert len(body["evidence"]) == 2 and body["evidence"][1]["uri"] is None
    for forbidden in ("actor_id", "student_user_id", "university_id", "integrity_hash",
                      "previous_entry_hash", "outcome_reference", "scenario_id", "input_state_reference"):
        assert forbidden not in body


def test_cross_owner_tenant_restricted_and_unknown_detail_are_indistinguishable(client):
    own = entry()
    restricted = entry(profile=RedactionProfile.ADVISOR_SAFE)
    configure(own, restricted)
    for target in (restricted.ledger_entry_id, str(uuid4())):
        response = client.get(f"/api/v1/me/decision-history/{target}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Decision record was not found"
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(OTHER))
    assert client.get(f"/api/v1/me/decision-history/{own.ledger_entry_id}").status_code == 404
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(STUDENT))
    configure(own, university=uuid4())
    assert client.get(f"/api/v1/me/decision-history/{own.ledger_entry_id}").status_code == 404


def test_tampered_hash_returns_safe_integrity_failure(client):
    original = entry()
    configure(replace(original, source_engine_version="tampered"))
    for path in ("/api/v1/me/decision-history", f"/api/v1/me/decision-history/{original.ledger_entry_id}"):
        response = client.get(path)
        assert response.status_code == 409
        assert response.json()["detail"] == "Decision record integrity could not be verified"
        assert "tampered" not in str(response.json())


def test_corrupt_restricted_trace_still_looks_not_found(client):
    restricted = entry(profile=RedactionProfile.ADVISOR_SAFE)
    configure(replace(restricted, source_engine_version="tampered"))
    response = client.get(f"/api/v1/me/decision-history/{restricted.ledger_entry_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Decision record was not found"


@pytest.mark.parametrize("query", ["?limit=0", "?limit=51", "?before_entry_id=abc",
                                   "?before_created_at=2026-09-28T12:00:00Z",
                                   "?before_created_at=2026-09-28T12:00:00Z&before_entry_id=bad,id"])
def test_pagination_bounds_and_cursor_validation(client, query):
    configure()
    assert client.get(f"/api/v1/me/decision-history{query}").status_code == 422


def test_persistence_unavailable_is_safe_503(client):
    class BrokenRepository(Repository):
        async def list_student_entries(self, **kwargs):
            from app.decision_trace_persistence import DecisionTraceErrorCode, DecisionTracePersistenceError
            raise DecisionTracePersistenceError(DecisionTraceErrorCode.PERSISTENCE_UNAVAILABLE, "private table detail")

    app.dependency_overrides[get_decision_trace_service] = lambda: DecisionTraceService(
        BrokenRepository(), Scope(), None
    )
    response = client.get("/api/v1/me/decision-history")
    assert response.status_code == 503 and "private" not in str(response.json())


def test_no_browser_write_endpoint_exists(client):
    configure()
    for method in (client.post, client.patch, client.delete):
        assert method("/api/v1/me/decision-history").status_code == 405


def test_unauthenticated_gets_401():
    with TestClient(app) as client:
        assert client.get("/api/v1/me/decision-history").status_code == 401
        assert client.get(f"/api/v1/me/decision-history/{uuid4()}").status_code == 401
