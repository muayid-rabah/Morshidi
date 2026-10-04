"""Authenticated, owner-derived student conversation history and continuation."""

from __future__ import annotations

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.routes.advisor import get_advisor_service
from app.api.routes.student import get_student_service
from app.api.schemas.advisor import AdvisorResponse
from app.core.auth import CurrentUser, get_current_user
from app.services.advisor import AdvisorService
from app.services.student import StudentService
from app.student_conversation.context import bounded_conversation_context, extract_explicit_preferences
from app.student_conversation.store import (ConversationNotFound, ConversationUnavailable,
                                            SupabaseConversationStore)

router = APIRouter(prefix="/api/v1/me/conversations", tags=["student-conversations"],
                   dependencies=[Depends(get_current_user)])
User = Annotated[CurrentUser, Depends(get_current_user)]
Student = Annotated[StudentService, Depends(get_student_service)]
Advisor = Annotated[AdvisorService, Depends(get_advisor_service)]


class NewThread(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="New conversation", min_length=1, max_length=120)


class NewMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)


class RenameThread(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)


class MessageReply(BaseModel):
    thread_id: UUID
    user_message: dict
    assistant_message: dict
    advisor: AdvisorResponse


def _store(request: Request) -> SupabaseConversationStore:
    store = getattr(request.app.state, "student_conversation_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Conversation storage unavailable")
    return store


async def _scope(user: CurrentUser, student: StudentService) -> tuple[str, str, str]:
    owner = str(user.user_id)
    state, institution = await asyncio.gather(
        student.get_profile(owner), student.resolve_student_university_id(owner))
    return owner, institution, state.profile_id


def _not_found(error: ConversationNotFound) -> HTTPException:
    return HTTPException(status_code=404, detail="Conversation not found")


@router.get("")
async def list_threads(user: User, student: Student, request: Request,
                       offset: int = 0) -> list[dict]:
    if offset < 0 or offset > 100000:
        raise HTTPException(status_code=422, detail="Invalid history offset")
    owner, institution, _ = await _scope(user, student)
    return await _store(request).list_threads(owner, institution, offset=offset)


@router.post("", status_code=201)
async def create_thread(body: NewThread, user: User, student: Student, request: Request) -> dict:
    owner, institution, profile_id = await _scope(user, student)
    return await _store(request).create_thread(owner, institution, profile_id, body.title.strip())


@router.get("/preferences")
async def get_preferences(user: User, student: Student, request: Request) -> dict[str, str]:
    owner, institution, _ = await _scope(user, student)
    return await _store(request).active_preferences(owner, institution)


@router.get("/{thread_id}/messages")
async def get_messages(thread_id: UUID, user: User, student: Student, request: Request,
                       offset: int = 0) -> list[dict]:
    if offset < 0 or offset > 100000:
        raise HTTPException(status_code=422, detail="Invalid history offset")
    owner, institution, _ = await _scope(user, student)
    try:
        return await _store(request).list_messages(owner, institution, str(thread_id), offset=offset)
    except ConversationNotFound as error:
        raise _not_found(error) from error


@router.patch("/{thread_id}")
async def rename_thread(thread_id: UUID, body: RenameThread, user: User,
                        student: Student, request: Request) -> dict:
    owner, institution, _ = await _scope(user, student)
    try:
        return await _store(request).update_thread(
            owner, institution, str(thread_id), {"title": body.title.strip()})
    except ConversationNotFound as error:
        raise _not_found(error) from error


@router.post("/{thread_id}/archive")
async def archive_thread(thread_id: UUID, user: User, student: Student, request: Request) -> dict:
    owner, institution, _ = await _scope(user, student)
    try:
        return await _store(request).update_thread(
            owner, institution, str(thread_id), {"status": "ARCHIVED"})
    except ConversationNotFound as error:
        raise _not_found(error) from error


@router.post("/{thread_id}/messages", response_model=MessageReply)
async def continue_thread(thread_id: UUID, body: NewMessage, user: User, student: Student,
                          advisor: Advisor, request: Request) -> MessageReply:
    owner, institution, _ = await _scope(user, student)
    store = _store(request)
    try:
        thread = await store.get_thread(owner, institution, str(thread_id))
        if thread["status"] != "ACTIVE":
            raise ConversationNotFound("Conversation archived")
        preferences, history = await asyncio.gather(
            store.active_preferences(owner, institution),
            store.recent_user_history(owner, institution),
        )
        message = body.message.strip()
        if not message:
            raise HTTPException(status_code=422, detail="Message must not be blank")
        user_row = await store.append_message(
            owner, institution, str(thread_id), "USER", message, "USER_STATED")
        changed = extract_explicit_preferences(message)
        for key, value in changed.items():
            await store.save_preference(owner, institution, key, value, user_row["id"])
        preferences.update(changed)
        if changed:
            summary = "; ".join(f"{key}={preferences[key]}" for key in sorted(preferences))[:800]
            await store.update_thread(owner, institution, str(thread_id), {"summary_text": summary})
        result = await advisor.advise_with_explanation(
            owner, message, bounded_conversation_context(
                preferences, history, thread.get("summary_text")))
        response = AdvisorResponse.from_domain(
            result.structured_result, explanation=result.explanation,
            explanation_status=result.explanation_status,
            explanation_language=result.explanation_language,
        )
        display = response.explanation or "تمت معالجة استفسارك وفق القواعد الحتمية."
        assistant_row = await store.append_message(
            owner, institution, str(thread_id), "ASSISTANT", display,
            "GUARDED_PROVIDER" if response.explanation_status.value == "GENERATED"
            else "DETERMINISTIC_EXPLANATION")
        return MessageReply(thread_id=thread_id, user_message=user_row,
                            assistant_message=assistant_row, advisor=response)
    except ConversationNotFound as error:
        raise _not_found(error) from error
