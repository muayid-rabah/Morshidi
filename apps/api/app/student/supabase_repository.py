"""GET-only Supabase adapter for persisted student academic state."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import logging
from time import perf_counter
from typing import Any
from uuid import UUID

import httpx

from app.core.request_timing import request_id_context
from app.rules.models import AttemptOutcome, StudentCourseAttempt
from app.student.errors import (
    StudentProfileIntegrityError,
    StudentProfileNotFound,
    StudentProfileTransportError,
    StudentAttemptNotFound,
    StudentCourseNotFound,
    StudentCourseUniversityMismatch,
    StudentProfileAlreadyExists,
    StudentStudyPlanNotFound,
)
from app.student.models import (
    PerformanceProvenance,
    PerformanceVerificationState,
    StudentAcademicState,
    StudentCourseAttemptRecord,
)


_ATTEMPT_RECORD_SELECT = (
    "id,profile_id,outcome,attempt_sequence,term_label,attempted_on,"
    "reported_grade_text,record_source,raw_numeric_grade,raw_letter_grade,"
    "raw_grade_points,raw_academic_year,raw_term,attempt_credit_hours,"
    "performance_provenance,performance_verification_state,"
    "performance_source_reference,created_at,updated_at,courses(course_code,name_ar,name_en)"
)


class SupabaseStudentAcademicRepository:
    """Server-side, owner-scoped student academic-state adapter.

    Attempts are ordered by persisted ``created_at`` then ``id``. The server
    key is only sent as an API-key header and is never retained in errors.
    """

    def __init__(self, supabase_url: str, server_key: str, client: httpx.AsyncClient | None = None) -> None:
        if not supabase_url.strip() or not server_key.strip():
            raise ValueError("supabase_url and server_key must not be empty")
        self._rest_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._server_key = server_key
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def load_student_academic_state(self, owner_user_id: UUID | str) -> StudentAcademicState:
        owner_id = str(owner_user_id)
        phase_started = perf_counter()
        profiles = await self._get_rows(
            "student_academic_profiles",
            {
                "select": "id,owner_user_id,study_plan_id,reported_cumulative_gpa,reported_gpa_scale,reported_earned_credit_hours,created_at,updated_at",
                "owner_user_id": f"eq.{owner_id}",
            },
        )
        logging.getLogger("uvicorn.error").info(
            "degree_path_phase request_id=%s phase=academic_profile_load_ms value=%.1f",
            request_id_context.get(), (perf_counter() - phase_started) * 1000,
        )
        if not profiles:
            raise StudentProfileNotFound("Student academic profile was not found")
        if len(profiles) != 1:
            raise StudentProfileIntegrityError("Multiple student profiles matched one owner")
        profile = profiles[0]
        profile_id = _uuid_text(profile, "id", "profile")
        if _uuid_text(profile, "owner_user_id", "profile") != owner_id:
            raise StudentProfileIntegrityError("Profile response did not match requested owner")
        phase_started = perf_counter()
        attempts = await self._get_rows(
            "student_course_attempts",
            {
                "select": "id,profile_id,outcome,created_at,courses(course_code)",
                "profile_id": f"eq.{profile_id}",
                "order": "created_at.asc,id.asc",
            },
        )
        logging.getLogger("uvicorn.error").info(
            "degree_path_phase request_id=%s phase=attempts_load_ms value=%.1f",
            request_id_context.get(), (perf_counter() - phase_started) * 1000,
        )
        mapped: list[StudentCourseAttempt] = []
        for row in attempts:
            if _uuid_text(row, "profile_id", "attempt") != profile_id:
                raise StudentProfileIntegrityError("Attempt response belongs to another profile")
            course = row.get("courses")
            if not isinstance(course, Mapping):
                raise StudentProfileIntegrityError("Attempt is missing its referenced course")
            try:
                outcome = AttemptOutcome(_required_text(row, "outcome", "attempt"))
            except ValueError as error:
                raise StudentProfileIntegrityError("Attempt has unsupported outcome") from error
            mapped.append(StudentCourseAttempt(_required_text(course, "course_code", "course"), outcome))
        return StudentAcademicState(
            profile_id=profile_id,
            owner_user_id=owner_id,
            study_plan_id=_uuid_text(profile, "study_plan_id", "profile"),
            reported_cumulative_gpa=_decimal(profile.get("reported_cumulative_gpa"), "reported_cumulative_gpa"),
            reported_gpa_scale=_decimal(profile.get("reported_gpa_scale"), "reported_gpa_scale"),
            reported_earned_credit_hours=_decimal(profile.get("reported_earned_credit_hours"), "reported_earned_credit_hours"),
            attempts=tuple(mapped),
            created_at=_optional_datetime(profile.get("created_at"), "profile created_at"),
            updated_at=_optional_datetime(profile.get("updated_at"), "profile updated_at"),
        )

    async def create_profile(
        self,
        owner_user_id: UUID | str,
        study_plan_id: UUID | str,
        *,
        reported_cumulative_gpa: Decimal | None = None,
        reported_gpa_scale: Decimal | None = None,
        reported_earned_credit_hours: Decimal | None = None,
    ) -> StudentAcademicState:
        payload = {
            "owner_user_id": str(owner_user_id),
            "study_plan_id": str(study_plan_id),
            "reported_cumulative_gpa": _json_decimal(reported_cumulative_gpa),
            "reported_gpa_scale": _json_decimal(reported_gpa_scale),
            "reported_earned_credit_hours": _json_decimal(reported_earned_credit_hours),
        }
        response = await self._request("POST", "student_academic_profiles", json=payload)
        if response.status_code == 409 and _postgrest_code(response) == "23505":
            raise StudentProfileAlreadyExists("Student academic profile already exists")
        if response.status_code in (400, 409) and _postgrest_code(response) == "23503":
            raise StudentStudyPlanNotFound("Study plan was not found")
        self._require_success(response, "POST", "student_academic_profiles")
        return await self.load_student_academic_state(owner_user_id)

    async def update_profile(
        self,
        owner_user_id: UUID | str,
        *,
        reported_cumulative_gpa: Decimal | None,
        reported_gpa_scale: Decimal | None,
        reported_earned_credit_hours: Decimal | None,
    ) -> StudentAcademicState:
        payload = {
            "reported_cumulative_gpa": _json_decimal(reported_cumulative_gpa),
            "reported_gpa_scale": _json_decimal(reported_gpa_scale),
            "reported_earned_credit_hours": _json_decimal(reported_earned_credit_hours),
        }
        response = await self._request("PATCH", "student_academic_profiles", params={"owner_user_id": f"eq.{owner_user_id}"}, json=payload)
        self._require_success(response, "PATCH", "student_academic_profiles")
        if not _response_rows(response):
            raise StudentProfileNotFound("Student academic profile was not found")
        return await self.load_student_academic_state(owner_user_id)

    async def delete_profile(self, owner_user_id: UUID | str) -> None:
        response = await self._request("DELETE", "student_academic_profiles", params={"owner_user_id": f"eq.{owner_user_id}"})
        self._require_success(response, "DELETE", "student_academic_profiles")
        if not _response_rows(response):
            raise StudentProfileNotFound("Student academic profile was not found")

    async def load_attempt_records(self, owner_user_id: UUID | str) -> tuple[StudentCourseAttemptRecord, ...]:
        state = await self.load_student_academic_state(owner_user_id)
        rows = await self._get_rows("student_course_attempts", {
            "select": _ATTEMPT_RECORD_SELECT,
            "profile_id": f"eq.{state.profile_id}", "order": "created_at.asc,id.asc",
        })
        return tuple(_attempt_record(row, state.profile_id) for row in rows)

    async def create_attempt(
        self, owner_user_id: UUID | str, course_code: str, outcome: AttemptOutcome, *,
        attempt_sequence: int | None = None, term_label: str | None = None,
        attempted_on: date | None = None, reported_grade_text: str | None = None,
        record_source: str = "manual_entry",
        raw_numeric_grade: Decimal | None = None, raw_letter_grade: str | None = None,
        raw_grade_points: Decimal | None = None, raw_academic_year: str | None = None,
        raw_term: str | None = None, attempt_credit_hours: Decimal | None = None,
        performance_provenance: PerformanceProvenance = PerformanceProvenance.STUDENT_RECORD,
        performance_verification_state: PerformanceVerificationState = PerformanceVerificationState.UNVERIFIED,
        performance_source_reference: str | None = None,
    ) -> StudentCourseAttemptRecord:
        profile_id, course_id = await self._resolve_course_for_owner(owner_user_id, course_code)
        payload = {"profile_id": profile_id, "course_id": course_id, "outcome": outcome.value,
            "attempt_sequence": attempt_sequence, "term_label": term_label,
            "attempted_on": attempted_on.isoformat() if attempted_on else None,
            "reported_grade_text": reported_grade_text, "record_source": record_source,
            "raw_numeric_grade": _json_decimal(raw_numeric_grade),
            "raw_letter_grade": raw_letter_grade,
            "raw_grade_points": _json_decimal(raw_grade_points),
            "raw_academic_year": raw_academic_year, "raw_term": raw_term,
            "attempt_credit_hours": _json_decimal(attempt_credit_hours),
            "performance_provenance": performance_provenance.value,
            "performance_verification_state": performance_verification_state.value,
            "performance_source_reference": performance_source_reference}
        response = await self._request("POST", "student_course_attempts", params={"select": _ATTEMPT_RECORD_SELECT}, json=payload)
        self._require_success(response, "POST", "student_course_attempts")
        rows = _response_rows(response)
        if len(rows) != 1: raise StudentProfileIntegrityError("Attempt creation did not return one row")
        return _attempt_record(rows[0], profile_id)

    async def update_attempt(
        self, owner_user_id: UUID | str, attempt_id: UUID | str, *, outcome: AttemptOutcome,
        attempt_sequence: int | None = None, term_label: str | None = None,
        attempted_on: date | None = None, reported_grade_text: str | None = None,
        record_source: str = "manual_entry",
    ) -> StudentCourseAttemptRecord:
        profile_id = (await self.load_student_academic_state(owner_user_id)).profile_id
        payload = {"outcome": outcome.value, "attempt_sequence": attempt_sequence,
            "term_label": term_label, "attempted_on": attempted_on.isoformat() if attempted_on else None,
            "reported_grade_text": reported_grade_text, "record_source": record_source}
        response = await self._request("PATCH", "student_course_attempts", params={"id": f"eq.{attempt_id}", "profile_id": f"eq.{profile_id}", "select": _ATTEMPT_RECORD_SELECT}, json=payload)
        self._require_success(response, "PATCH", "student_course_attempts")
        rows = _response_rows(response)
        if not rows: raise StudentAttemptNotFound("Student course attempt was not found")
        if len(rows) != 1: raise StudentProfileIntegrityError("Attempt update returned multiple rows")
        return _attempt_record(rows[0], profile_id)

    async def delete_attempt(self, owner_user_id: UUID | str, attempt_id: UUID | str) -> None:
        profile_id = (await self.load_student_academic_state(owner_user_id)).profile_id
        response = await self._request("DELETE", "student_course_attempts", params={"id": f"eq.{attempt_id}", "profile_id": f"eq.{profile_id}"})
        self._require_success(response, "DELETE", "student_course_attempts")
        if not _response_rows(response): raise StudentAttemptNotFound("Student course attempt was not found")

    async def resolve_student_university_id(self, owner_user_id: UUID | str) -> str:
        profiles = await self._get_rows("student_academic_profiles", {
            "select": "id,study_plans(majors(faculties(university_id)))", "owner_user_id": f"eq.{owner_user_id}"})
        if not profiles: raise StudentProfileNotFound("Student academic profile was not found")
        if len(profiles) != 1: raise StudentProfileIntegrityError("Multiple student profiles matched one owner")
        return _profile_university_id(profiles[0])

    async def _resolve_course_for_owner(self, owner_user_id: UUID | str, course_code: str) -> tuple[str, str]:
        profiles = await self._get_rows("student_academic_profiles", {
            "select": "id,study_plans(majors(faculties(university_id)))", "owner_user_id": f"eq.{owner_user_id}"})
        if not profiles: raise StudentProfileNotFound("Student academic profile was not found")
        if len(profiles) != 1: raise StudentProfileIntegrityError("Multiple student profiles matched one owner")
        profile_id = _uuid_text(profiles[0], "id", "profile")
        university_id = _profile_university_id(profiles[0])
        courses = await self._get_rows("courses", {"select": "id,course_code,university_id,catalog_status", "course_code": f"eq.{course_code}"})
        if not courses: raise StudentCourseNotFound("Course code was not found")
        matching = [row for row in courses if row.get("university_id") == university_id]
        if not matching: raise StudentCourseUniversityMismatch("Course code does not belong to the profile university")
        if len(matching) != 1: raise StudentProfileIntegrityError("Multiple university courses matched one code")
        if _required_text(matching[0], "course_code", "course") != course_code: raise StudentProfileIntegrityError("Course response did not preserve exact code")
        return profile_id, _uuid_text(matching[0], "id", "course")

    async def _request(self, method: str, resource: str, *, params: Mapping[str, str] | None = None, json: Mapping[str, Any] | None = None) -> httpx.Response:
        try:
            return await self._client.request(method, f"{self._rest_url}/{resource}", params=params, json=json,
                headers={"apikey": self._server_key, "Authorization": f"Bearer {self._server_key}", "Accept": "application/json", "Prefer": "return=representation"})
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise StudentProfileTransportError(method, resource) from error

    @staticmethod
    def _require_success(response: httpx.Response, method: str, resource: str) -> None:
        if not 200 <= response.status_code < 300:
            raise StudentProfileTransportError(method, resource, status_code=response.status_code)

    async def _get_rows(self, resource: str, params: Mapping[str, str]) -> list[Mapping[str, Any]]:
        try:
            response = await self._client.get(f"{self._rest_url}/{resource}", params=params, headers={"apikey": self._server_key, "Authorization": f"Bearer {self._server_key}", "Accept": "application/json"})
        except (httpx.TimeoutException, httpx.RequestError) as error:
            raise StudentProfileTransportError("GET", resource) from error
        if not 200 <= response.status_code < 300:
            raise StudentProfileTransportError("GET", resource, status_code=response.status_code)
        try:
            body = response.json()
        except ValueError as error:
            raise StudentProfileTransportError("decode response", resource) from error
        if not isinstance(body, list) or not all(isinstance(row, Mapping) for row in body):
            raise StudentProfileIntegrityError(f"{resource} response is not a row array")
        return list(body)


def _required_text(row: Mapping[str, Any], field: str, resource: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise StudentProfileIntegrityError(f"{resource} is missing required {field}")
    return value


def _uuid_text(row: Mapping[str, Any], field: str, resource: str) -> str:
    value = _required_text(row, field, resource)
    try:
        return str(UUID(value))
    except ValueError as error:
        raise StudentProfileIntegrityError(f"{resource} has invalid {field}") from error


def _decimal(value: Any, field: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise StudentProfileIntegrityError(f"profile has invalid {field}")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise StudentProfileIntegrityError(f"profile has invalid {field}") from error


def _json_decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _postgrest_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("code") if isinstance(body, Mapping) else None


def _response_rows(response: httpx.Response) -> list[Mapping[str, Any]]:
    try:
        body = response.json()
    except ValueError as error:
        raise StudentProfileTransportError("decode response", "student data") from error
    if not isinstance(body, list) or not all(isinstance(row, Mapping) for row in body):
        raise StudentProfileIntegrityError("Student write response is not a row array")
    return list(body)


def _optional_datetime(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StudentProfileIntegrityError(f"{field} is invalid")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise StudentProfileIntegrityError(f"{field} is invalid") from error


def _required_datetime(row: Mapping[str, Any], field: str, resource: str) -> datetime:
    value = _optional_datetime(row.get(field), f"{resource} {field}")
    if value is None:
        raise StudentProfileIntegrityError(f"{resource} is missing required {field}")
    return value


def _optional_date(value: Any, field: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StudentProfileIntegrityError(f"{field} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise StudentProfileIntegrityError(f"{field} is invalid") from error


def _attempt_record(row: Mapping[str, Any], profile_id: str) -> StudentCourseAttemptRecord:
    if _uuid_text(row, "profile_id", "attempt") != profile_id:
        raise StudentProfileIntegrityError("Attempt response belongs to another profile")
    course = row.get("courses")
    if not isinstance(course, Mapping):
        raise StudentProfileIntegrityError("Attempt is missing its referenced course")
    try:
        outcome = AttemptOutcome(_required_text(row, "outcome", "attempt"))
    except ValueError as error:
        raise StudentProfileIntegrityError("Attempt has unsupported outcome") from error
    sequence = row.get("attempt_sequence")
    if sequence is not None and (isinstance(sequence, bool) or not isinstance(sequence, int)):
        raise StudentProfileIntegrityError("Attempt has invalid attempt_sequence")
    for field in (
        "term_label", "reported_grade_text", "raw_letter_grade", "raw_academic_year",
        "raw_term", "performance_source_reference",
    ):
        if row.get(field) is not None and not isinstance(row[field], str):
            raise StudentProfileIntegrityError(f"Attempt has invalid {field}")
    return StudentCourseAttemptRecord(
        attempt_id=_uuid_text(row, "id", "attempt"), profile_id=profile_id,
        course_code=_required_text(course, "course_code", "course"), outcome=outcome,
        course_name_ar=course.get("name_ar"), course_name_en=course.get("name_en"),
        attempt_sequence=sequence, term_label=row.get("term_label"),
        attempted_on=_optional_date(row.get("attempted_on"), "attempt attempted_on"),
        reported_grade_text=row.get("reported_grade_text"),
        record_source=_required_text(row, "record_source", "attempt"),
        raw_numeric_grade=_decimal(row.get("raw_numeric_grade"), "raw_numeric_grade"),
        raw_letter_grade=row.get("raw_letter_grade"),
        raw_grade_points=_decimal(row.get("raw_grade_points"), "raw_grade_points"),
        raw_academic_year=row.get("raw_academic_year"), raw_term=row.get("raw_term"),
        attempt_credit_hours=_decimal(row.get("attempt_credit_hours"), "attempt_credit_hours"),
        performance_provenance=_performance_provenance(row.get("performance_provenance")),
        performance_verification_state=_performance_verification_state(row.get("performance_verification_state")),
        performance_source_reference=row.get("performance_source_reference"),
        created_at=_required_datetime(row, "created_at", "attempt"),
        updated_at=_required_datetime(row, "updated_at", "attempt"),
    )


def _performance_provenance(value: Any) -> PerformanceProvenance:
    if value is None:
        return PerformanceProvenance.UNVERIFIED
    try:
        return PerformanceProvenance(value)
    except (TypeError, ValueError) as error:
        raise StudentProfileIntegrityError("Attempt has invalid performance_provenance") from error


def _performance_verification_state(value: Any) -> PerformanceVerificationState:
    if value is None:
        return PerformanceVerificationState.UNVERIFIED
    try:
        return PerformanceVerificationState(value)
    except (TypeError, ValueError) as error:
        raise StudentProfileIntegrityError("Attempt has invalid performance_verification_state") from error


def _profile_university_id(profile: Mapping[str, Any]) -> str:
    plan = profile.get("study_plans")
    major = plan.get("majors") if isinstance(plan, Mapping) else None
    faculty = major.get("faculties") if isinstance(major, Mapping) else None
    if not isinstance(faculty, Mapping):
        raise StudentProfileIntegrityError("Profile is missing its study-plan university")
    return _uuid_text(faculty, "university_id", "faculty")
