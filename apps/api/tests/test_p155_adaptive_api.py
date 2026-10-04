"""Owner-derived transport boundary for the P15.5 batch read."""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.routes.student import get_student_service
from app.core.auth import CurrentUser, get_current_user
from app.main import app
from apps.api.tests.test_p155_adaptive import _snapshot

OWNER = "11111111-1111-1111-1111-111111111111"


class FakeService:
    def __init__(self):
        self.owners = []

    async def get_adaptive_course_intelligence(self, owner):
        self.owners.append(owner)
        return _snapshot(Decimal(90))


def test_adaptive_requires_authentication():
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        response = client.get("/api/v1/me/adaptive-course-intelligence")
    assert response.status_code == 401


def test_adaptive_owner_is_derived_and_response_is_private():
    service = FakeService()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    app.dependency_overrides[get_student_service] = lambda: service
    try:
        with TestClient(app) as client:
            spoof = client.get("/api/v1/me/adaptive-course-intelligence?student_id=someone-else")
            response = client.get("/api/v1/me/adaptive-course-intelligence")
        assert spoof.status_code == 422
        assert response.status_code == 200
        assert service.owners == [OWNER]
        assert response.headers["cache-control"] == "private, no-store"
        assert len(response.json()["courses"]) == 3
    finally:
        app.dependency_overrides.clear()
