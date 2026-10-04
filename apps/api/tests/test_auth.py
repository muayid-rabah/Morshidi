"""Focused tests for server-verified Supabase bearer authentication."""

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.auth import CurrentUser, get_current_user
from app.core.config import settings


def auth_app(handler) -> FastAPI:
    application = FastAPI()
    application.state.auth_http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    @application.get("/protected")
    async def protected(user: CurrentUser = Depends(get_current_user)):
        return {"user_id": user.user_id}

    return application


@pytest.fixture(autouse=True)
def configured_auth(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://auth.example")
    monkeypatch.setattr(settings, "supabase_secret_key", SecretStr("test-secret-never-exposed"))


def test_valid_token_is_verified_by_auth_server() -> None:
    def handler(request: httpx.Request):
        assert request.url.path == "/auth/v1/user"
        assert request.headers["authorization"] == "Bearer valid-token"
        return httpx.Response(200, json={"id": "11111111-1111-1111-1111-111111111111"})
    application = auth_app(handler)
    with TestClient(application) as client:
        response = client.get("/protected", headers={"Authorization": "Bearer valid-token"})
    assert response.status_code == 200
    assert response.json()["user_id"] == "11111111-1111-1111-1111-111111111111"


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer "])
def test_missing_malformed_and_empty_bearer_are_401(authorization) -> None:
    application = auth_app(lambda request: pytest.fail("Auth server must not be called"))
    headers = {} if authorization is None else {"Authorization": authorization}
    with TestClient(application) as client:
        response = client.get("/protected", headers=headers)
    assert response.status_code == 401


def test_invalid_token_malformed_response_and_timeout_are_safe_401() -> None:
    handlers = [
        lambda request: httpx.Response(401, json={"message": "token details"}),
        lambda request: httpx.Response(200, content=b"{"),
        lambda request: httpx.Response(200, json={"id": "not-a-uuid"}),
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("token secret", request=request)),
    ]
    for handler in handlers:
        application = auth_app(handler)
        with TestClient(application) as client:
            response = client.get("/protected", headers={"Authorization": "Bearer private-user-token"})
        assert response.status_code == 401
        assert "private-user-token" not in response.text
        assert "test-secret-never-exposed" not in response.text
