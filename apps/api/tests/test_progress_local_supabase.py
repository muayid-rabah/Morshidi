"""Opt-in progress validation against the canonical local Plan 12 catalog."""

from __future__ import annotations

import asyncio
import os
import uuid
from decimal import Decimal

import httpx
import pytest

from app.catalog.supabase_repository import SupabaseAcademicCatalogRepository
from app.progress.engine import calculate_academic_progress
from app.progress.models import CourseProgressState, RequirementType
from app.rules.models import AttemptOutcome, StudentCourseAttempt
from app.services.eligibility import EligibilityService
from app.services.student import StudentService
from app.student.supabase_repository import SupabaseStudentAcademicRepository

URL = os.getenv("MORSHIDI_LOCAL_SUPABASE_URL")
KEY = os.getenv("MORSHIDI_LOCAL_SUPABASE_SERVER_KEY")
PLAN = os.getenv("MORSHIDI_LOCAL_STUDY_PLAN_ID")
pytestmark = pytest.mark.skipif(
    not all((URL, KEY, PLAN)), reason="set local MORSHIDI_LOCAL_SUPABASE_* values"
)


def test_real_plan12_structure_and_progress_scenarios() -> None:
    async def run() -> None:
        repository = SupabaseAcademicCatalogRepository(URL or "", KEY or "")
        try:
            catalog = await repository.load_progress_catalog(PLAN or "")
        finally:
            await repository.close()

        assert catalog.study_plan.total_credit_hours == 132
        assert len(catalog.requirement_groups) == 6
        assert len(catalog.plan_courses) == 68
        groups = {group.group_code: group for group in catalog.requirement_groups}
        groups_by_id = {group.group_id: group for group in catalog.requirement_groups}
        assert groups["UNIVERSITY_ELECTIVE"].required_credit_hours == 9
        assert groups["MAJOR_ELECTIVE"].required_credit_hours == 9

        by_code = {course.course_code: course for course in catalog.plan_courses}
        assert by_code["0200115"].credit_hours == 0
        assert by_code["1509999"].credit_hours == 0
        assert all(
            groups_by_id[by_code[code].requirement_group_id].requirement_type is RequirementType.REQUIRED
            for code in ("0200115", "1509999")
        )

        empty = calculate_academic_progress(catalog, ())
        assert empty.completed_plan_credits == 0
        assert empty.remaining_plan_credits == 132
        assert not any(group.is_satisfied for group in empty.requirement_groups)

        passed_once = calculate_academic_progress(
            catalog, (StudentCourseAttempt("1501110", AttemptOutcome.PASSED),)
        )
        repeated = calculate_academic_progress(
            catalog,
            (
                StudentCourseAttempt("1501110", AttemptOutcome.FAILED),
                StudentCourseAttempt("1501110", AttemptOutcome.PASSED),
                StudentCourseAttempt("1501110", AttemptOutcome.PASSED),
            ),
        )
        assert passed_once.completed_plan_credits == 3
        assert repeated.completed_plan_credits == passed_once.completed_plan_credits
        assert next(row for row in repeated.courses if row.course_code == "1501110").state is CourseProgressState.COMPLETED

        referenced = calculate_academic_progress(
            catalog, (StudentCourseAttempt("0300103", AttemptOutcome.PASSED),)
        )
        assert referenced.completed_plan_credits == 0
        assert "0300103" not in {row.course_code for row in referenced.courses}

        university_electives = [
            course.course_code
            for course in catalog.plan_courses
            if groups_by_id[course.requirement_group_id].group_code == "UNIVERSITY_ELECTIVE"
        ][:4]
        excess = calculate_academic_progress(
            catalog,
            tuple(StudentCourseAttempt(code, AttemptOutcome.PASSED) for code in university_electives),
        )
        elective_result = next(
            group for group in excess.requirement_groups
            if group.group_code == "UNIVERSITY_ELECTIVE"
        )
        assert elective_result.completed_listed_credits == 12
        assert elective_result.credited_toward_requirement == 9

        university_required_positive = tuple(
            StudentCourseAttempt(course.course_code, AttemptOutcome.PASSED)
            for course in catalog.plan_courses
            if groups_by_id[course.requirement_group_id].group_code == "UNIVERSITY_REQUIRED"
            and course.credit_hours > 0
        )
        zero_incomplete = calculate_academic_progress(catalog, university_required_positive)
        required_result = next(
            group for group in zero_incomplete.requirement_groups
            if group.group_code == "UNIVERSITY_REQUIRED"
        )
        assert required_result.credited_toward_requirement == 18
        assert not required_result.is_satisfied

    asyncio.run(run())


def test_real_student_repository_catalog_service_and_engine() -> None:
    async def run() -> None:
        owner = str(uuid.uuid4())
        headers = {"apikey": KEY or "", "Authorization": f"Bearer {KEY or ''}"}
        async with httpx.AsyncClient(timeout=10) as client:
            student = SupabaseStudentAcademicRepository(URL or "", KEY or "", client)
            catalog = SupabaseAcademicCatalogRepository(URL or "", KEY or "", client)
            service = StudentService(student, EligibilityService(catalog), catalog)
            try:
                created = await client.post(
                    f"{URL}/auth/v1/admin/users",
                    headers=headers,
                    json={"id": owner, "email": f"phase65-{owner}@local.test", "email_confirm": True},
                )
                created.raise_for_status()
                profile_response = await client.post(
                    f"{URL}/rest/v1/student_academic_profiles",
                    headers={**headers, "Prefer": "return=representation"},
                    json={
                        "owner_user_id": owner,
                        "study_plan_id": PLAN,
                        "reported_cumulative_gpa": 3.25,
                        "reported_gpa_scale": 4,
                        "reported_earned_credit_hours": 15,
                    },
                )
                profile_response.raise_for_status()
                profile_id = profile_response.json()[0]["id"]
                courses_response = await client.get(
                    f"{URL}/rest/v1/courses",
                    headers=headers,
                    params={"select": "id,course_code", "course_code": "in.(1501110,0300103)"},
                )
                courses_response.raise_for_status()
                course_ids = {row["course_code"]: row["id"] for row in courses_response.json()}
                attempt_response = await client.post(
                    f"{URL}/rest/v1/student_course_attempts",
                    headers=headers,
                    json=[
                        {"profile_id": profile_id, "course_id": course_ids["1501110"], "outcome": "FAILED"},
                        {"profile_id": profile_id, "course_id": course_ids["1501110"], "outcome": "PASSED"},
                        {"profile_id": profile_id, "course_id": course_ids["0300103"], "outcome": "PASSED"},
                    ],
                )
                attempt_response.raise_for_status()

                progress = await service.get_academic_progress(owner)
                assert progress.study_plan_id == PLAN
                assert progress.plan_total_required_credits == 132
                assert progress.completed_plan_credits == 3
                assert "0300103" not in {row.course_code for row in progress.courses}
                assert progress.reported_cumulative_gpa == Decimal("3.25")
                assert progress.reported_gpa_scale == Decimal("4")
                assert progress.reported_earned_credit_hours == Decimal("15")
            finally:
                await client.delete(f"{URL}/auth/v1/admin/users/{owner}", headers=headers)

    asyncio.run(run())
