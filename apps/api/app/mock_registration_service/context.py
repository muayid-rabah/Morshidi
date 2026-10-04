"""Authoritative academic-context loader for P6.5."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

import httpx

from app.catalog.repository import AcademicCatalogRepository
from app.catalog.errors import CatalogIntegrityError, CatalogTransportError, StudyPlanNotFound
from app.mock_registration.models import MockRegistrationContext, PlanCourseFact, TargetPeriod
from app.progress.engine import calculate_academic_progress
from app.student.repository import StudentAcademicRepository

from .models import AcademicContextSnapshot


class AcademicContextLoader(Protocol):
    async def load_owner_context(self, owner_user_id: UUID) -> AcademicContextSnapshot: ...
    async def validate_plan_scope(self, study_plan_id: UUID, university_id: UUID) -> tuple[PlanCourseFact, ...]: ...


class SupabaseAcademicContextLoader:
    def __init__(self, supabase_url: str, server_key: str, client: httpx.AsyncClient,
                 student_repository: StudentAcademicRepository,
                 catalog_repository: AcademicCatalogRepository) -> None:
        self._rest_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._key = server_key
        self._client = client
        self._students = student_repository
        self._catalog = catalog_repository

    async def load_owner_context(self, owner_user_id: UUID) -> AcademicContextSnapshot:
        state = await self._students.load_student_academic_state(owner_user_id)
        plan_id = UUID(state.study_plan_id)
        progress_catalog = await self._catalog.load_progress_catalog(plan_id)
        eligibility_catalog = await self._catalog.load_plan_eligibility_catalog(plan_id)
        progress = calculate_academic_progress(
            progress_catalog, state.attempts,
            reported_cumulative_gpa=state.reported_cumulative_gpa,
            reported_gpa_scale=state.reported_gpa_scale,
            reported_earned_credit_hours=state.reported_earned_credit_hours,
        )
        plan, rows = await self._load_plan_rows(plan_id)
        university_id, major_id, plan_version, facts, course_ids, source_versions = _map_plan(plan, rows)
        progress_version = _digest(
            state.profile_id,
            *((item.course_code, item.outcome.value) for item in state.attempts),
            state.reported_cumulative_gpa,
            state.reported_gpa_scale,
            state.reported_earned_credit_hours,
        )
        token = _digest(plan_version, progress_version, *source_versions)
        return AcademicContextSnapshot(
            owner_user_id=owner_user_id, university_id=university_id, major_id=major_id,
            study_plan_id=plan_id, study_plan_version=plan_version,
            eligibility_catalog=eligibility_catalog, progress_catalog=progress_catalog,
            current_progress=progress, student_attempts=state.attempts,
            course_ids=course_ids, plan_course_facts=facts,
            source_versions=source_versions, progress_state_version=progress_version,
            progress_state_reference=state.profile_id, snapshot_token=token,
        )

    async def validate_plan_scope(self, study_plan_id: UUID, university_id: UUID) -> tuple[PlanCourseFact, ...]:
        plan, rows = await self._load_plan_rows(study_plan_id)
        mapped_university, _, _, facts, _, _ = _map_plan(plan, rows)
        if mapped_university != university_id:
            raise StudyPlanNotFound("Study plan was not found")
        return facts

    async def _load_plan_rows(self, study_plan_id: UUID):
        plans = await self._get("study_plans", {
            "select": "id,major_id,plan_number,effective_year,source_id,status,updated_at,majors(faculties(university_id))",
            "id": f"eq.{study_plan_id}",
        })
        if len(plans) != 1:
            raise StudyPlanNotFound("Study plan was not found")
        rows = await self._get("study_plan_courses", {
            "select": "course_id,requirement_group_id,credit_hours,source_id,prerequisite_logic_status,updated_at,courses(course_code,university_id)",
            "study_plan_id": f"eq.{study_plan_id}", "order": "course_id.asc",
        })
        return plans[0], rows

    async def _get(self, resource: str, params: Mapping[str, str]) -> list[Mapping[str, Any]]:
        try:
            response = await self._client.get(f"{self._rest_url}/{resource}", params=params,
                headers={"apikey": self._key, "Authorization": f"Bearer {self._key}", "Accept": "application/json"})
        except (httpx.RequestError, httpx.TimeoutException) as error:
            raise CatalogTransportError("GET", resource) from error
        if not 200 <= response.status_code < 300:
            raise CatalogTransportError("GET", resource, status_code=response.status_code)
        try:
            body = response.json()
        except ValueError as error:
            raise CatalogTransportError("decode", resource) from error
        if not isinstance(body, list) or not all(isinstance(item, Mapping) for item in body):
            raise CatalogIntegrityError(f"{resource} response is invalid")
        return list(body)


def domain_context(snapshot: AcademicContextSnapshot, period: TargetPeriod) -> MockRegistrationContext:
    return MockRegistrationContext(
        owner_scope_id=str(snapshot.owner_user_id), university_id=str(snapshot.university_id),
        major_id=str(snapshot.major_id), study_plan_id=str(snapshot.study_plan_id),
        study_plan_version=snapshot.study_plan_version,
        eligibility_catalog=snapshot.eligibility_catalog, progress_catalog=snapshot.progress_catalog,
        current_progress=snapshot.current_progress, student_attempts=snapshot.student_attempts,
        source_versions=snapshot.source_versions,
        engine_policy_versions=("phase5:v1", "phase6:v1", "p6:v1"),
        allowed_target_period=period,
    )


def _map_plan(plan: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]):
    try:
        major_id = UUID(str(plan["major_id"]))
        university_id = UUID(str(plan["majors"]["faculties"]["university_id"]))
        plan_id = str(UUID(str(plan["id"])))
    except (KeyError, TypeError, ValueError) as error:
        raise CatalogIntegrityError("Study plan scope is invalid") from error
    plan_version = _digest(plan_id, plan.get("plan_number"), plan.get("effective_year"), plan.get("source_id"))
    facts: list[PlanCourseFact] = []
    course_ids: list[tuple[str, UUID]] = []
    versions: list[str] = [plan_version]
    for row in rows:
        try:
            course = row["courses"]
            code = str(course["course_code"])
            if UUID(str(course["university_id"])) != university_id:
                raise ValueError
            course_id = UUID(str(row["course_id"]))
            group_id = str(UUID(str(row["requirement_group_id"])))
            credit = Decimal(str(row["credit_hours"]))
        except (KeyError, TypeError, ValueError) as error:
            raise CatalogIntegrityError("Study plan course scope is invalid") from error
        source_version = _digest(row.get("source_id"), row.get("prerequisite_logic_status"), row.get("updated_at"))
        facts.append(PlanCourseFact(str(university_id), str(major_id), plan_id, plan_version, code, group_id, credit, source_version))
        course_ids.append((code, course_id))
        versions.append(source_version)
    return university_id, major_id, plan_version, tuple(facts), tuple(sorted(course_ids)), tuple(sorted(set(versions)))


def _digest(*values: object) -> str:
    payload = "\x1f".join(repr(value) for value in values).encode()
    return hashlib.sha256(payload).hexdigest()

