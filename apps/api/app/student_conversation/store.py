"""Supabase Data API adapter for private conversation history.

Every service-role operation includes exact owner and institution predicates.
No chat text, provider payload, or credentials are logged in this module.
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

import httpx


class ConversationUnavailable(RuntimeError):
    pass


class ConversationNotFound(RuntimeError):
    pass


PREFERENCE_KEYS = ("regular_load", "summer_enabled", "summer_load", "graduation_pace")


class SupabaseConversationStore:
    def __init__(self, url: str, server_key: str, client: httpx.AsyncClient) -> None:
        self._base = f"{url.rstrip('/')}/rest/v1"
        self._key = server_key
        self._client = client

    async def _rows(self, method: str, table: str, *, params: Mapping[str, str] | None = None,
                    payload: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            response = await self._client.request(
                method, f"{self._base}/{table}", params=params, json=payload,
                headers={"apikey": self._key, "Authorization": f"Bearer {self._key}",
                         "Prefer": "return=representation", "Accept": "application/json"},
            )
        except httpx.RequestError as error:
            raise ConversationUnavailable("Conversation storage unavailable") from error
        if not 200 <= response.status_code < 300:
            raise ConversationUnavailable("Conversation storage rejected request")
        try:
            rows = response.json()
        except ValueError as error:
            raise ConversationUnavailable("Conversation storage response malformed") from error
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ConversationUnavailable("Conversation storage response malformed")
        return rows

    @staticmethod
    def _scope(owner: str, institution: str) -> dict[str, str]:
        return {"owner_user_id": f"eq.{owner}", "institution_id": f"eq.{institution}"}

    @staticmethod
    def _verify_scope(rows: list[dict[str, Any]], owner: str, institution: str) -> None:
        if any(row.get("owner_user_id") != owner or row.get("institution_id") != institution
               for row in rows):
            raise ConversationUnavailable("Conversation response scope mismatch")

    async def list_threads(self, owner: str, institution: str, *, offset: int = 0) -> list[dict[str, Any]]:
        rows = await self._rows("GET", "student_conversation_threads", params={
            **self._scope(owner, institution),
            "select": "id,owner_user_id,institution_id,title,status,created_at,updated_at,last_message_at,summary_text",
            "order": "updated_at.desc,id.desc", "limit": "100", "offset": str(offset),
        })
        self._verify_scope(rows, owner, institution)
        return [{key: value for key, value in row.items()
                 if key not in {"owner_user_id", "institution_id"}} for row in rows]

    async def create_thread(self, owner: str, institution: str, profile_id: str,
                            title: str) -> dict[str, Any]:
        rows = await self._rows("POST", "student_conversation_threads", payload={
            "owner_user_id": owner, "institution_id": institution,
            "profile_id": profile_id, "title": title,
        })
        if len(rows) != 1:
            raise ConversationUnavailable("Conversation creation scope mismatch")
        self._verify_scope(rows, owner, institution)
        return rows[0]

    async def get_thread(self, owner: str, institution: str, thread_id: str) -> dict[str, Any]:
        rows = await self._rows("GET", "student_conversation_threads", params={
            **self._scope(owner, institution), "id": f"eq.{thread_id}", "select": "*", "limit": "2",
        })
        if len(rows) != 1:
            raise ConversationNotFound("Conversation not found")
        self._verify_scope(rows, owner, institution)
        return rows[0]

    async def update_thread(self, owner: str, institution: str, thread_id: str,
                            changes: Mapping[str, Any]) -> dict[str, Any]:
        await self.get_thread(owner, institution, thread_id)
        rows = await self._rows("PATCH", "student_conversation_threads", params={
            **self._scope(owner, institution), "id": f"eq.{thread_id}"}, payload=changes)
        if len(rows) != 1:
            raise ConversationNotFound("Conversation not found")
        self._verify_scope(rows, owner, institution)
        return rows[0]

    async def list_messages(self, owner: str, institution: str, thread_id: str,
                            *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        await self.get_thread(owner, institution, thread_id)
        rows = await self._rows("GET", "student_conversation_messages", params={
            **self._scope(owner, institution), "thread_id": f"eq.{thread_id}",
            "select": "id,thread_id,owner_user_id,institution_id,role,content,message_type,provenance,created_at",
            "order": "created_at.desc,id.desc", "limit": str(min(limit, 100)), "offset": str(offset),
        })
        self._verify_scope(rows, owner, institution)
        if any(row.get("thread_id") != thread_id for row in rows):
            raise ConversationUnavailable("Conversation message scope mismatch")
        return [{key: value for key, value in row.items()
                 if key not in {"owner_user_id", "institution_id"}}
                for row in reversed(rows)]

    async def append_message(self, owner: str, institution: str, thread_id: str,
                             role: str, content: str, provenance: str) -> dict[str, Any]:
        thread = await self.get_thread(owner, institution, thread_id)
        if thread["status"] != "ACTIVE":
            raise ConversationNotFound("Archived conversation cannot be continued")
        rows = await self._rows("POST", "student_conversation_messages", payload={
            "thread_id": thread_id, "owner_user_id": owner, "institution_id": institution,
            "role": role, "content": content, "provenance": provenance,
            "message_type": "ACADEMIC_EXPLANATION" if role == "ASSISTANT" else "TEXT",
        })
        if len(rows) != 1:
            raise ConversationUnavailable("Message persistence failed")
        self._verify_scope(rows, owner, institution)
        if rows[0].get("thread_id") != thread_id:
            raise ConversationUnavailable("Message persistence scope mismatch")
        await self.update_thread(owner, institution, thread_id, {
            "last_message_at": rows[0]["created_at"], "updated_at": rows[0]["created_at"],
        })
        return rows[0]

    async def save_preference(self, owner: str, institution: str, key: str,
                              value: str, message_id: str) -> None:
        if key not in PREFERENCE_KEYS:
            raise ConversationUnavailable("Unsupported planning preference")
        rows = await self._rows("POST", "student_conversation_preferences", payload={
            "owner_user_id": owner, "institution_id": institution,
            "preference_key": key, "preference_value": value,
            "provenance": "USER_STATED", "source_message_id": message_id,
        })
        if len(rows) != 1 or rows[0].get("source_message_id") != message_id:
            raise ConversationUnavailable("Preference persistence scope mismatch")
        self._verify_scope(rows, owner, institution)

    async def active_preferences(self, owner: str, institution: str) -> dict[str, str]:
        # Fixed four indexed reads preserve older still-active keys after arbitrarily
        # many updates to another preference. No transcript scan or per-course query.
        pages = await asyncio.gather(*(self._rows("GET", "student_conversation_preferences", params={
            **self._scope(owner, institution), "select": "owner_user_id,institution_id,preference_key,preference_value",
            "preference_key": f"eq.{key}", "order": "created_at.desc,id.desc", "limit": "1",
        }) for key in PREFERENCE_KEYS))
        active: dict[str, str] = {}
        for key, rows in zip(PREFERENCE_KEYS, pages):
            self._verify_scope(rows, owner, institution)
            if len(rows) > 1 or any(row.get("preference_key") != key for row in rows):
                raise ConversationUnavailable("Preference response scope mismatch")
            if rows:
                active[key] = rows[0]["preference_value"]
        return active

    async def recent_user_history(self, owner: str, institution: str) -> list[str]:
        rows = await self._rows("GET", "student_conversation_messages", params={
            **self._scope(owner, institution), "role": "eq.USER", "select": "owner_user_id,institution_id,content",
            "order": "created_at.desc,id.desc", "limit": "4",
        })
        self._verify_scope(rows, owner, institution)
        return [str(row["content"])[:180] for row in reversed(rows)]

    async def export_owned_chats(self, owner: str, institution: str) -> dict[str, Any]:
        """Bounded owner export; no provider internals, hidden reasoning, or N+1 reads."""
        threads: list[dict[str, Any]] = []
        for offset in range(0, 500, 100):
            page = await self.list_threads(owner, institution, offset=offset)
            threads.extend({key: row[key] for key in (
                "id", "title", "status", "created_at", "updated_at", "last_message_at", "summary_text")
                if key in row} for row in page)
            if len(page) < 100:
                break
        messages: list[dict[str, Any]] = []
        for offset in range(0, 1000, 100):
            page = await self._rows("GET", "student_conversation_messages", params={
                **self._scope(owner, institution),
                "select": "id,thread_id,owner_user_id,institution_id,role,content,message_type,provenance,created_at",
                "order": "created_at.desc,id.desc", "limit": "100", "offset": str(offset),
            })
            self._verify_scope(page, owner, institution)
            messages.extend({key: row[key] for key in (
                "id", "thread_id", "role", "content", "message_type", "provenance", "created_at")
                             if key in row}
                            for row in page)
            if len(page) < 100:
                break
        return {
            "threads": threads,
            "messages": list(reversed(messages)),
            "active_planning_preferences": await self.active_preferences(owner, institution),
            "retention_classification": "USER_OWNED_CONVERSATION_DATA",
            "retention_policy": "RETENTION_POLICY_NOT_VERIFIED",
            "truncated": len(threads) == 500 or len(messages) == 1000,
            "limits": {"threads": 500, "messages": 1000},
        }
