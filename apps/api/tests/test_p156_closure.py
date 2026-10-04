"""Local closure: batch display boundaries, governed export, and strategy API."""

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes.student import get_student_service
from app.catalog.display import CourseDisplayIdentity
from app.catalog.errors import CatalogIntegrityError
from app.catalog.supabase_repository import SupabaseAcademicCatalogRepository
from app.change_impact.service import ChangeImpactService, ImpactServiceError
from app.core.auth import CurrentUser, get_current_user
from app.degree_path.credit_timeline import AcademicTerm, compare_credit_timelines
from app.main import app
from app.services.student import StudentService
from app.student_conversation.store import SupabaseConversationStore, ConversationUnavailable

OWNER = "11111111-1111-1111-1111-111111111111"
TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
FOREIGN = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_catalog_display_is_batch_paginated_and_rejects_foreign_rows():
    async def run():
        calls = []
        foreign = False

        def respond(request):
            calls.append(request)
            assert request.url.params["university_id"] == f"eq.{TENANT}"
            offset = int(request.url.params["offset"])
            return httpx.Response(200, json=[{
                "id": f"course-{index}", "course_code": f"CS{index}",
                "name_ar": "مادة معتمدة", "name_en": "Canonical course",
                "university_id": FOREIGN if foreign else TENANT,
            } for index in range(offset, min(offset + 500, 501))])

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            repo = SupabaseAcademicCatalogRepository("https://local.invalid", "test-only", client)
            rows = await repo.load_university_course_identities(TENANT)
            assert len(rows) == 501 and len(calls) == 2
            assert rows[0].course_code == "CS0" and rows[0].name_ar == "مادة معتمدة"
            foreign = True
            with pytest.raises(CatalogIntegrityError):
                await repo.load_university_course_identities(TENANT)
    asyncio.run(run())


def test_student_and_analyst_display_maps_use_existing_authorization_boundaries():
    async def run():
        identities = (CourseDisplayIdentity("course-1", "CS101", "مقدمة", "Introduction"),)
        catalog = SimpleNamespace(load_university_course_identities=AsyncMock(return_value=identities))
        repository = SimpleNamespace(resolve_student_university_id=AsyncMock(return_value=TENANT))
        student = StudentService(repository, None, catalog)
        assert await student.get_course_identities(OWNER) == identities
        repository.resolve_student_university_id.assert_awaited_once_with(OWNER)
        catalog.load_university_course_identities.assert_awaited_once_with(TENANT)
        memberships = SimpleNamespace(load_active_memberships_for_user=AsyncMock(
            return_value=[SimpleNamespace(university_id=UUID(TENANT))]))
        service = ChangeImpactService(memberships, None, None, catalog, None)
        assert await service.course_identities(OWNER, UUID(TENANT)) == identities
        with pytest.raises(ImpactServiceError):
            await service.course_identities(OWNER, UUID(FOREIGN))
        assert catalog.load_university_course_identities.await_count == 2
    asyncio.run(run())


def test_export_whitelists_owned_content_and_keeps_archives_without_destructive_requests():
    async def run():
        calls = []
        foreign = False

        def respond(request):
            calls.append(request)
            assert request.method == "GET"
            assert request.url.params["owner_user_id"] == f"eq.{OWNER}"
            assert request.url.params["institution_id"] == f"eq.{TENANT}"
            scope = {"owner_user_id": OWNER, "institution_id": FOREIGN if foreign else TENANT}
            if request.url.path.endswith("threads"):
                row = {**scope, "id": "thread", "title": "Owned", "status": "ARCHIVED",
                       "summary_text": "regular_load=15", "raw_provider": "excluded"}
            elif request.url.path.endswith("messages"):
                row = {**scope, "id": "message", "thread_id": "thread", "role": "USER",
                       "content": "My preference", "chain_of_thought": "excluded"}
            else:
                key = request.url.params["preference_key"].removeprefix("eq.")
                assert request.url.params["limit"] == "1"
                assert request.url.params["order"] == "created_at.desc,id.desc"
                row = {**scope, "preference_key": key, "preference_value": {
                    "regular_load": "15", "summer_enabled": "true", "summer_load": "6",
                    "graduation_pace": "BALANCED"}[key]}
            return httpx.Response(200, json=[row])

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            store = SupabaseConversationStore("https://local.invalid", "test-only", client)
            result = await store.export_owned_chats(OWNER, TENANT)
            assert result["threads"][0]["status"] == "ARCHIVED"
            assert result["messages"][0]["content"] == "My preference"
            assert result["active_planning_preferences"]["graduation_pace"] == "BALANCED"
            assert result["retention_policy"] == "RETENTION_POLICY_NOT_VERIFIED"
            assert "excluded" not in str(result) and "owner_user_id" not in str(result)
            assert len(calls) == 6  # two collection reads plus four latest-key reads
            foreign = True
            with pytest.raises(ConversationUnavailable):
                await store.export_owned_chats(OWNER, TENANT)
    asyncio.run(run())


def test_comparison_service_uses_owner_progress_and_p155_workload_evidence():
    async def run():
        service = StudentService(None, None, None)
        service.get_academic_progress = AsyncMock(return_value=SimpleNamespace(
            plan_total_required_credits=Decimal(132), completed_plan_credits=Decimal(60)))
        service.get_adaptive_course_intelligence = AsyncMock(return_value=SimpleNamespace(
            recommendations=[SimpleNamespace(workload_risk=80), SimpleNamespace(workload_risk=60)],
            model_version="PERSONAL_DIFFICULTY_MODEL_V1"))
        result = await service.compare_credit_timelines(OWNER, start_year=2026,
            start_term=AcademicTerm.FIRST_SEMESTER)
        service.get_academic_progress.assert_awaited_once_with(OWNER)
        service.get_adaptive_course_intelligence.assert_awaited_once_with(OWNER)
        assert all(row.current_workload_risk == 70 for row in result.scenarios)
        assert all(row.difficulty_evidence.startswith("CURRENT_ELIGIBLE_COURSES_ONLY") for row in result.scenarios)
        assert all(row.confidence == "MODELED_CREDIT_ONLY" for row in result.scenarios)
    asyncio.run(run())


def test_strategy_and_display_api_derive_owner_and_reject_authoritative_input():
    class Student:
        async def get_course_identities(self, owner):
            assert owner == OWNER
            return [CourseDisplayIdentity("course-1", "CS101", "مقدمة", "Introduction")]

        async def compare_credit_timelines(self, owner, **values):
            assert owner == OWNER
            return compare_credit_timelines(required=Decimal(132), earned=Decimal(60), **values)

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
    app.dependency_overrides[get_student_service] = lambda: Student()
    try:
        with TestClient(app) as client:
            display = client.get("/api/v1/me/course-identities?university_id=" + FOREIGN)
            assert display.status_code == 200 and display.json()[0]["name_ar"] == "مقدمة"
            assert display.headers["cache-control"] == "private, no-store"
            body = {"start_year": 2026, "start_term": "FIRST_SEMESTER",
                    "preferred_regular_load": 15, "preferred_summer_enabled": True,
                    "preferred_summer_load": 6, "graduation_pace": "BALANCED"}
            response = client.post("/api/v1/me/degree-paths/credit-comparison", json=body)
            assert response.status_code == 200
            assert response.json()["scenarios"][1]["preference_match"] is True
            assert client.post("/api/v1/me/degree-paths/credit-comparison", json={
                **body, "earned_credits": 132}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_unapplied_chat_migration_static_owner_and_tenant_constraints():
    migration = Path(__file__).resolve().parents[3] / "supabase/migrations/20261001200504_add_student_conversation_history.sql"
    sql = migration.read_text(encoding="utf-8").lower()
    assert sql.count("enable row level security") == 3
    assert sql.count("for select to authenticated") == 3
    assert "using (true)" not in sql and "for all to authenticated" not in sql
    assert "foreign key (thread_id, owner_user_id, institution_id)" in sql
    assert "references public.student_academic_profiles(id) on delete restrict" in sql
    assert "t.institution_id = student_conversation_messages.institution_id" in sql
    assert "validate_student_conversation_scope" in sql
    assert "validate_student_conversation_preference_scope" in sql
    assert "grant select, insert, update, delete" in sql and "to service_role" in sql
    assert "graduation_pace" in sql
