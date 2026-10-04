"""Request timing logs retain route shape without leaking private path segments."""

import logging

import pytest

from app.core.request_timing import RequestTimingMiddleware, request_id_context, safe_path


def test_safe_path_redacts_student_ids_and_course_codes() -> None:
    assert safe_path("/api/v1/me/eligibility/1501332") == "/api/v1/me/eligibility/{parameter}"
    assert safe_path("/api/v1/me/decision-history/private-id") == "/api/v1/me/decision-history/{parameter}"


@pytest.mark.anyio
async def test_request_timing_logs_start_end_status_without_query_or_headers(caplog) -> None:
    seen_ids: list[str] = []

    async def endpoint(scope, receive, send):
        seen_ids.append(request_id_context.get())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    messages = []

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http", "method": "GET", "path": "/api/v1/me/eligibility/1501332",
        "query_string": b"secret=query", "headers": [(b"authorization", b"Bearer private-token")],
    }
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        await RequestTimingMiddleware(endpoint)(scope, receive, send)

    assert messages[0]["status"] == 200
    assert seen_ids[0] != "-"
    text = caplog.text
    assert "request_start" in text and "request_end" in text
    assert "status=200" in text
    assert "1501332" not in text
    assert "private-token" not in text
    assert "secret=query" not in text
    assert request_id_context.get() == "-"
