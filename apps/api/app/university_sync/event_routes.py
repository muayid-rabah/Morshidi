from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.auth import CurrentUser, get_current_user
from app.core.config import settings
from app.university_sync.events import UniversityEventStore

router = APIRouter(prefix="/api/v1", tags=["university live events"])
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]
EventType = Literal[
    "grade.posted", "record.updated", "registration.opened", "registration.closed",
    "offering.updated", "section.opened", "section.closed", "schedule.changed", "plan.updated",
]


class UniversityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    type: EventType
    version: int = Field(ge=1)
    occurredAt: datetime
    studentId: str | None = Field(default=None, pattern=r"^\d{9}$")
    payload: dict[str, object]
    idempotencyKey: str = Field(min_length=1, max_length=160)

    @field_validator("occurredAt")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event timestamp must include a timezone")
        return value


def _event_store(request: Request) -> UniversityEventStore:
    store = getattr(request.app.state, "university_event_store", None)
    if store is None:
        raise HTTPException(503, detail={"kind": "error", "code": "EVENT_STORE_UNAVAILABLE"})
    return store


def student_scope_from_email(email: str | None) -> str:
    match = re.fullmatch(r"(\d{9})@std\.morshidi\.edu\.jo", (email or "").strip().lower())
    if not match:
        raise HTTPException(403, detail={"kind": "error", "code": "STUDENT_SCOPE_REQUIRED"})
    return match.group(1)


def verify_signature(raw: bytes, signature: str | None, secret: str | None) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest() if secret else ""
    return bool(secret and signature and hmac.compare_digest(expected, signature))


@router.post("/uni/webhook", status_code=202)
async def receive_university_event(request: Request, x_uni_signature: str | None = Header(default=None)):
    secret = settings.uni_webhook_secret.get_secret_value() if settings.uni_webhook_secret else ""
    raw = await request.body()
    if len(raw) > 128 * 1024:
        raise HTTPException(413, detail={"kind": "error", "code": "EVENT_TOO_LARGE"})
    if not verify_signature(raw, x_uni_signature, secret):
        raise HTTPException(401, detail={"kind": "error", "code": "INVALID_EVENT_SIGNATURE"})
    try:
        parsed = UniversityEvent.model_validate_json(raw)
    except ValueError:
        raise HTTPException(422, detail={"kind": "error", "code": "INVALID_EVENT"}) from None
    try:
        return await _event_store(request).ingest(parsed.model_dump(by_alias=True, mode="json"))
    except Exception:
        raise HTTPException(503, detail={"kind": "error", "code": "EVENT_STORE_UNAVAILABLE"}) from None


@router.get("/me/university-notifications")
async def my_university_notifications(user: AuthenticatedUser, request: Request, since: str | None = None):
    try:
        return await _event_store(request).list_notifications(student_scope_from_email(user.email), since)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, detail={"kind": "error", "code": "NOTIFICATIONS_UNAVAILABLE"}) from None


@router.get("/me/university-stream")
async def my_university_stream(user: AuthenticatedUser, request: Request, since: str | None = None):
    student_id = student_scope_from_email(user.email)
    store = _event_store(request)

    async def stream():
        cursor = since
        yield "retry: 3000\n\n"
        while not await request.is_disconnected():
            try:
                rows = await store.list_notifications(student_id, cursor)
                for row in reversed(rows):
                    payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                    yield f"data: {payload}\n\n"
                    if isinstance(row.get("created_at"), str):
                        cursor = row["created_at"]
            except Exception:
                yield "event: sync-error\ndata: {}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(stream(), media_type="text/event-stream; charset=utf-8", headers={
        "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
    })
