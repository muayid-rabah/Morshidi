"""Phase P7.4 Supabase adapter for Advisor Authorization and Assignment Persistence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx

from app.advisor_persistence.errors import (
    AdvisorPersistenceError,
    AdvisorPersistenceIntegrityError,
)
from app.advisor_persistence.models import (
    AdvisorStudentAssignmentRecord,
)
from app.mock_registration_persistence.models import (
    InstitutionalMembershipRecord,
)


class SupabaseAdvisorAssignmentRepository:
    """Server-side, trusted service-role repository for advisor assignments."""

    def __init__(
        self,
        supabase_url: str,
        server_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not supabase_url.strip() or not server_key.strip():
            raise ValueError("supabase_url and server_key must not be empty")
        self._rest_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._server_key = server_key
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def load_active_assignment(
        self,
        *,
        advisor_user_id: UUID,
        student_user_id: UUID,
        university_id: UUID,
    ) -> AdvisorStudentAssignmentRecord | None:
        """Load the active explicit assignment matching the exact advisor, student, and university."""
        rows = await self._get_rows(
            "advisor_student_assignments",
            {
                "select": "*",
                "advisor_user_id": f"eq.{advisor_user_id}",
                "student_user_id": f"eq.{student_user_id}",
                "university_id": f"eq.{university_id}",
                "is_active": "eq.true",
            },
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise AdvisorPersistenceIntegrityError(
                "Multiple active assignments found for the same advisor, student, and university",
                operation="load_active_assignment",
            )
        return _assignment_record(rows[0])

    async def create_assignment(
        self,
        *,
        advisor_user_id: UUID,
        student_user_id: UUID,
        university_id: UUID,
        authority_source: str,
        authority_version: str,
        is_active: bool = True,
    ) -> AdvisorStudentAssignmentRecord:
        """Insert a trusted advisor-student assignment (service-role provisioning / testing)."""
        if advisor_user_id == student_user_id:
            raise AdvisorPersistenceIntegrityError(
                "Self-assignment is prohibited (advisor_user_id cannot equal student_user_id)",
                operation="create_assignment",
            )
        payload = {
            "advisor_user_id": str(advisor_user_id),
            "student_user_id": str(student_user_id),
            "university_id": str(university_id),
            "authority_source": authority_source.strip(),
            "authority_version": authority_version.strip(),
            "is_active": is_active,
        }
        response = await self._request("POST", "advisor_student_assignments", json=payload)
        self._require_success(response, "create_assignment")
        rows = _response_rows(response)
        if not rows:
            raise AdvisorPersistenceIntegrityError(
                "Empty representation returned on assignment insert",
                operation="create_assignment",
            )
        return _assignment_record(rows[0])

    async def load_active_advisor_memberships_for_user(
        self,
        subject_user_id: UUID,
    ) -> tuple[InstitutionalMembershipRecord, ...]:
        """Load active institutional memberships with role 'ACADEMIC_ADVISOR'."""
        rows = await self._get_rows(
            "institutional_memberships",
            {
                "select": "*",
                "subject_user_id": f"eq.{subject_user_id}",
                "role": "eq.ACADEMIC_ADVISOR",
                "active": "eq.true",
            },
        )
        return tuple(_membership_record(row) for row in rows)

    async def load_student_authoritative_university(
        self,
        student_user_id: UUID,
    ) -> UUID | None:
        """Load the authoritative university for a student profile without reading attempts or progress."""
        rows = await self._get_rows(
            "student_academic_profiles",
            {
                "select": "id,owner_user_id,study_plans(majors(faculties(university_id)))",
                "owner_user_id": f"eq.{student_user_id}",
            },
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise AdvisorPersistenceIntegrityError(
                "Multiple student academic profiles matched one owner",
                operation="load_student_authoritative_university",
            )
        profile = rows[0]
        plan = profile.get("study_plans")
        major = plan.get("majors") if isinstance(plan, Mapping) else None
        faculty = major.get("faculties") if isinstance(major, Mapping) else None
        if not isinstance(faculty, Mapping) or not faculty.get("university_id"):
            raise AdvisorPersistenceIntegrityError(
                "Student profile is missing its study plan university relationship",
                operation="load_student_authoritative_university",
            )
        try:
            return UUID(str(faculty["university_id"]))
        except (ValueError, TypeError) as error:
            raise AdvisorPersistenceIntegrityError(
                "Invalid university UUID on student profile",
                operation="load_student_authoritative_university",
            ) from error

    async def _get_rows(
        self,
        resource: str,
        params: Mapping[str, str],
    ) -> list[Mapping[str, Any]]:
        response = await self._request("GET", resource, params=params)
        self._require_success(response, f"get {resource}")
        return _response_rows(response)

    async def _request(
        self,
        method: str,
        resource: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            return await self._client.request(
                method,
                f"{self._rest_url}/{resource}",
                params=params,
                json=json,
                headers={
                    "apikey": self._server_key,
                    "Authorization": f"Bearer {self._server_key}",
                    "Accept": "application/json",
                    "Prefer": "return=representation",
                },
            )
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise AdvisorPersistenceError(
                f"Transport failure during {method} {resource}",
                operation=resource,
                status_code=503,
            ) from error

    @staticmethod
    def _require_success(response: httpx.Response, operation: str) -> None:
        if 200 <= response.status_code < 300:
            return
        code = _postgrest_code(response)
        raise AdvisorPersistenceError(
            f"Persistence error ({response.status_code}, code {code}) during {operation}",
            operation=operation,
            status_code=response.status_code,
        )


def _postgrest_code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        return ""
    if isinstance(body, Mapping) and isinstance(body.get("code"), str):
        return body["code"]
    return ""


def _response_rows(response: httpx.Response) -> list[Mapping[str, Any]]:
    try:
        data = response.json()
    except Exception as error:
        raise AdvisorPersistenceIntegrityError("Non-JSON response from persistence service") from error
    if isinstance(data, list):
        return [row for row in data if isinstance(row, Mapping)]
    if isinstance(data, Mapping):
        return [data]
    return []


def _assignment_record(row: Mapping[str, Any]) -> AdvisorStudentAssignmentRecord:
    try:
        return AdvisorStudentAssignmentRecord(
            id=UUID(str(row["id"])),
            advisor_user_id=UUID(str(row["advisor_user_id"])),
            student_user_id=UUID(str(row["student_user_id"])),
            university_id=UUID(str(row["university_id"])),
            is_active=bool(row["is_active"]),
            authority_source=str(row["authority_source"]),
            authority_version=str(row["authority_version"]),
            created_at=_parse_datetime(row.get("created_at")),
            updated_at=_parse_datetime(row.get("updated_at")),
        )
    except (KeyError, ValueError, TypeError) as error:
        raise AdvisorPersistenceIntegrityError("Failed to map assignment record row") from error


def _membership_record(row: Mapping[str, Any]) -> InstitutionalMembershipRecord:
    try:
        return InstitutionalMembershipRecord(
            membership_id=UUID(str(row["id"])),
            subject_user_id=UUID(str(row["subject_user_id"])),
            university_id=UUID(str(row["university_id"])),
            provider_namespace=str(row["provider_namespace"]),
            role=str(row["role"]),
            active=bool(row["active"]),
            authority_source=str(row["authority_source"]),
            authority_source_version=str(row["authority_source_version"]),
            created_at=_parse_datetime(row.get("created_at")),
            updated_at=_parse_datetime(row.get("updated_at")),
        )
    except (KeyError, ValueError, TypeError) as error:
        raise AdvisorPersistenceIntegrityError("Failed to map institutional membership row") from error


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError(f"Invalid datetime format: {value}")
