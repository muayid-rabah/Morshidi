"""Verified Supabase Auth boundary for self-service API routes."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    email: str | None = None


_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """Verify the bearer token with Supabase Auth; never decode claims locally."""
    auth_started = perf_counter()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    token = credentials.credentials.strip()
    if not token or not settings.supabase_url or not settings.supabase_secret_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication")
    try:
        response = await request.app.state.auth_http_client.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "apikey": settings.supabase_secret_key.get_secret_value(),
                "Authorization": f"Bearer {token}",
            },
        )
        body: Any = response.json() if response.status_code == 200 else None
    except (httpx.RequestError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication") from None
    user_id = body.get("id") if isinstance(body, dict) else None
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication")
    try:
        normalized_user_id = str(UUID(user_id))
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication") from None
    request.state.auth_ms = round((perf_counter() - auth_started) * 1000, 1)
    email = body.get("email") if isinstance(body, dict) else None
    return CurrentUser(normalized_user_id, email if isinstance(email, str) else None)
