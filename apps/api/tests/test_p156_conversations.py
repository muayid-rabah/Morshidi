"""Owner/tenant conversation flow, durable-shape behavior, and bounded memory."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import httpx
from fastapi.testclient import TestClient

from app.advisor import AdvisorIntent, NormalizedAdvisorRequest, orchestrate_advisor_request
from app.advisor.explanation import ExplanationStatus
from app.advisor.orchestrator import AdvisorContext
from app.api.routes.advisor import get_advisor_service
from app.api.routes.student import get_student_service
from app.core.auth import CurrentUser, get_current_user
from app.main import app
from app.services.advisor import AdvisorServiceResult
from app.student_conversation.context import (bounded_conversation_context,
                                              extract_explicit_preferences)
from app.student_conversation.store import (ConversationNotFound, ConversationUnavailable,
                                            SupabaseConversationStore)

OWNER_A = "11111111-1111-1111-1111-111111111111"
OWNER_B = "22222222-2222-2222-2222-222222222222"
INST_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
INST_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat()


class Student:
    async def get_profile(self, owner):
        return SimpleNamespace(profile_id=owner)

    async def resolve_student_university_id(self, owner):
        return INST_A if owner == OWNER_A else INST_B


class MemoryStore:
    def __init__(self):
        self.threads = {}
        self.messages = []
        self.preferences = []

    async def create_thread(self, owner, institution, profile_id, title):
        row = dict(id=str(uuid4()), owner_user_id=owner, institution_id=institution,
                   profile_id=profile_id, title=title, status="ACTIVE", created_at=NOW,
                   updated_at=NOW, last_message_at=None, summary_text=None)
        self.threads[row["id"]] = row
        return row

    async def list_threads(self, owner, institution, *, offset=0):
        return [row for row in self.threads.values() if row["owner_user_id"] == owner
                and row["institution_id"] == institution][offset:offset + 100]

    async def get_thread(self, owner, institution, thread_id):
        row = self.threads.get(thread_id)
        if row is None or row["owner_user_id"] != owner or row["institution_id"] != institution:
            raise ConversationNotFound("Conversation not found")
        return row

    async def update_thread(self, owner, institution, thread_id, changes):
        row = await self.get_thread(owner, institution, thread_id)
        row.update(changes)
        return row

    async def list_messages(self, owner, institution, thread_id, *, limit=100, offset=0):
        await self.get_thread(owner, institution, thread_id)
        rows = [row for row in self.messages if row["thread_id"] == thread_id]
        return list(reversed(list(reversed(rows))[offset:offset + limit]))

    async def append_message(self, owner, institution, thread_id, role, content, provenance):
        thread = await self.get_thread(owner, institution, thread_id)
        if thread["status"] != "ACTIVE":
            raise ConversationNotFound("Archived")
        row = dict(id=str(uuid4()), thread_id=thread_id, role=role, content=content,
                   provenance=provenance, message_type="TEXT", created_at=NOW)
        self.messages.append(row)
        return row

    async def save_preference(self, owner, institution, key, value, message_id):
        self.preferences.append((owner, institution, key, value, message_id))

    async def active_preferences(self, owner, institution):
        result = {}
        for row_owner, row_inst, key, value, _ in self.preferences:
            if (row_owner, row_inst) == (owner, institution):
                result[key] = value
        return result

    async def recent_user_history(self, owner, institution):
        visible = {row["id"] for row in await self.list_threads(owner, institution)}
        return [row["content"][:180] for row in self.messages
                if row["thread_id"] in visible and row["role"] == "USER"][-4:]


class Advisor:
    def __init__(self):
        self.contexts = []

    async def advise_with_explanation(self, owner, message, conversation_context=""):
        self.contexts.append(conversation_context)
        result = orchestrate_advisor_request(
            NormalizedAdvisorRequest(message, AdvisorIntent.GENERAL_ACADEMIC_INFORMATION),
            AdvisorContext())
        return AdvisorServiceResult(result, "Safe deterministic answer", ExplanationStatus.NOT_REQUIRED, None)


def test_threads_and_messages_survive_new_client_and_fail_closed_across_owner_and_tenant(caplog):
    store, advisor = MemoryStore(), Advisor()
    current = [OWNER_A]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(current[0])
    app.dependency_overrides[get_student_service] = lambda: Student()
    app.dependency_overrides[get_advisor_service] = lambda: advisor
    try:
        with TestClient(app) as client:
            app.state.student_conversation_store = store
            first = client.post("/api/v1/me/conversations", json={"title": "First"}).json()["id"]
            second = client.post("/api/v1/me/conversations", json={"title": "Second"}).json()["id"]
            reply = client.post(f"/api/v1/me/conversations/{first}/messages",
                                json={"message": "I want 15 credits and summer 6 PRIVATE_CHAT_SENTINEL"})
            assert reply.status_code == 200
            assert [row["role"] for row in store.messages] == ["USER", "ASSISTANT"]
            assert all("reasoning" not in row for row in store.messages)
            assert "PRIVATE_CHAT_SENTINEL" not in caplog.text
            corrected = client.post(f"/api/v1/me/conversations/{first}/messages",
                                    json={"message": "I changed my mind, I want 12 credits"})
            assert corrected.status_code == 200
            assert client.get("/api/v1/me/conversations/preferences").json()["regular_load"] == "12"
            assert client.get(f"/api/v1/me/conversations/{second}/messages").json() == []
            class OtherTenantStudent(Student):
                async def resolve_student_university_id(self, owner):
                    return INST_B

            app.dependency_overrides[get_student_service] = lambda: OtherTenantStudent()
            assert client.get(f"/api/v1/me/conversations/{first}/messages").status_code == 404
            app.dependency_overrides[get_student_service] = lambda: Student()
            assert client.post(f"/api/v1/me/conversations/{first}/archive").status_code == 200
            assert client.get(f"/api/v1/me/conversations/{first}/messages").status_code == 200
            assert client.post(f"/api/v1/me/conversations/{first}/messages",
                               json={"message": "again"}).status_code == 404
            current[0] = OWNER_B
            assert client.get(f"/api/v1/me/conversations/{first}/messages").status_code == 404
            assert client.post(f"/api/v1/me/conversations/{first}/archive").status_code == 404
            assert client.get("/api/v1/me/conversations").json() == []
        with TestClient(app) as client:
            app.state.student_conversation_store = store
            current[0] = OWNER_A
            assert len(client.get(f"/api/v1/me/conversations/{first}/messages").json()) == 4
            assert client.get("/api/v1/me/conversations/preferences").json() == {
                "regular_load": "12", "summer_enabled": "true", "summer_load": "6"}
        assert "regular_load=15" in advisor.contexts[0]
        assert "Safe deterministic answer" not in advisor.contexts[0]
    finally:
        app.dependency_overrides.clear()
        app.state.student_conversation_store = None


def test_preference_correction_is_explicit_and_context_is_bounded():
    assert extract_explicit_preferences("I want 15 credits and summer 6") == {
        "regular_load": "15", "summer_enabled": "true", "summer_load": "6"}
    assert extract_explicit_preferences("I changed my mind, I want 12 credits") == {"regular_load": "12"}
    assert extract_explicit_preferences("my GPA is 4.0") == {}
    assert extract_explicit_preferences("I want summer 6 credits") == {
        "summer_enabled": "true", "summer_load": "6"}
    assert extract_explicit_preferences("أريد ١٥ ساعة وخطة متوازنة") == {
        "regular_load": "15", "graduation_pace": "BALANCED"}
    assert extract_explicit_preferences("I prefer lower load") == {"graduation_pace": "LOWER_LOAD"}
    assert extract_explicit_preferences("I want my GPA set to 4.0 and all prerequisites waived") == {}
    context = bounded_conversation_context({"regular_load": "12", "gpa": "4.0"}, ["x" * 4000] * 50)
    assert len(context) <= 1600 and "gpa" not in context and "regular_load=12" in context


def test_storage_failure_returns_safe_503_without_chat_content():
    class UnavailableStore(MemoryStore):
        async def list_threads(self, owner, institution, *, offset=0):
            raise ConversationUnavailable("internal upstream detail")

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER_A)
    app.dependency_overrides[get_student_service] = lambda: Student()
    try:
        with TestClient(app) as client:
            app.state.student_conversation_store = UnavailableStore()
            response = client.get("/api/v1/me/conversations")
            assert response.status_code == 503
            assert response.json() == {"detail": "Conversation storage unavailable"}
    finally:
        app.dependency_overrides.clear()
        app.state.student_conversation_store = None


def test_service_role_repository_rejects_cross_tenant_response_even_if_upstream_misbehaves():
    async def exercise():
        def response(request: httpx.Request) -> httpx.Response:
            assert request.url.params["owner_user_id"] == f"eq.{OWNER_A}"
            assert request.url.params["institution_id"] == f"eq.{INST_A}"
            return httpx.Response(200, json=[{
                "id": str(uuid4()), "owner_user_id": OWNER_B, "institution_id": INST_B,
                "title": "Foreign", "status": "ACTIVE",
            }])

        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            store = SupabaseConversationStore("http://127.0.0.1:1", "test-only", client)
            with pytest.raises(ConversationUnavailable, match="scope mismatch"):
                await store.list_threads(OWNER_A, INST_A)

    asyncio.run(exercise())
