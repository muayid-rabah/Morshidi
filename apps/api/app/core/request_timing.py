"""Privacy-safe request lifecycle timing for the ASGI boundary."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
import logging
from time import perf_counter
from typing import Any
from uuid import uuid4


request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("uvicorn.error")

_SAFE_SEGMENTS = frozenset({
    "api", "v1", "me", "health", "academic-progress", "academic-profile",
    "attempts", "degree-paths", "explanation-graph", "advisor", "policies",
    "eligibility", "course-recommendations", "semester-plans", "student",
    "institutional", "ai-query", "change-impact", "decision-history",
})


def safe_path(path: str) -> str:
    """Retain static route shape while redacting IDs, course codes, and unknown segments."""
    return "/" + "/".join(
        segment if segment in _SAFE_SEGMENTS else "{parameter}"
        for segment in path.strip("/").split("/") if segment
    )


class RequestTimingMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex
        token = request_id_context.set(request_id)
        method = scope.get("method", "UNKNOWN")
        path = safe_path(scope.get("path", ""))
        started_at = datetime.now(timezone.utc).isoformat()
        started = perf_counter()
        status = 500
        logger.info(
            "request_start request_id=%s method=%s path=%s request_start=%s",
            request_id, method, path, started_at,
        )

        async def timed_send(message: dict[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, timed_send)
        finally:
            logger.info(
                "request_end request_id=%s method=%s path=%s request_start=%s request_end=%s duration_ms=%.1f status=%s",
                request_id, method, path, started_at,
                datetime.now(timezone.utc).isoformat(), (perf_counter() - started) * 1000,
                status,
            )
            request_id_context.reset(token)
