"""P10-only fictional tenant bootstrap for Local Supabase integration tests.

Fixed catalog/period identities make repeated runs idempotent. Ephemeral Auth
principals and their access rows are removed after each test. A local db reset
removes the fixed fictional catalog; this module refuses non-loopback targets.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from urllib.parse import urlparse

import httpx

from app.offerings.fake_provider import FAKE_PERIOD, FAKE_UNIVERSITY_ID
from app.mock_registration.aggregation import aggregate_institutional_demand
from app.mock_registration.models import (
    AggregationLimits, AggregationScope, CoverageInput, DemandAggregationInput,
    IntentLifecycle, IntentProvenance, PlanCourseFact, PrivacyConfiguration,
    RegistrationIntent, ResolvedIntent, ResolutionDisposition, TargetPeriod,
    TargetPeriodClass, ValidatedIntent, ValidationStatus,
)
from tests.test_decision_trace_persistence_service_local_supabase import (
    URL, _create_user, _server_headers,
)

FACULTY_ID = "f1000000-0000-0000-0000-000000000021"
MAJOR_ID = "f1000000-0000-0000-0000-000000000022"
PLAN_ID = "f1000000-0000-0000-0000-000000000023"
GROUP_ID = "f1000000-0000-0000-0000-000000000024"
PERIOD_ID = "f1000000-0000-0000-0000-000000000025"
NAMESPACE = "p10-fictional-only"
FOREIGN_UNIVERSITY_ID = "f1000000-0000-0000-0000-000000000050"
FOREIGN_FACULTY_ID = "f1000000-0000-0000-0000-000000000051"
FOREIGN_MAJOR_ID = "f1000000-0000-0000-0000-000000000052"
FOREIGN_PLAN_ID = "f1000000-0000-0000-0000-000000000053"
FOREIGN_GROUP_ID = "f1000000-0000-0000-0000-000000000054"
FOREIGN_COURSE_ID = "f1000000-0000-0000-0000-000000000055"
COURSES = {code: f"f1000000-0000-0000-0000-{30 + index:012d}"
           for index, code in enumerate(("CS101", "MATH101", "HIST101", "PHYS101"))}


def _local_only() -> None:
    parsed = urlparse(URL or "")
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port not in {54321, 55321}:
        raise RuntimeError("P10 synthetic fixture requires local loopback Supabase")


def _ensure(client: httpx.Client, table: str, row: dict) -> None:
    existing = client.get(f"{URL}/rest/v1/{table}", headers=_server_headers(),
                          params={"select": "*", "id": f"eq.{row['id']}"})
    existing.raise_for_status()
    if existing.json():
        assert all(existing.json()[0].get(key) == value for key, value in row.items()), (
            "P10 fixed synthetic identity contains unexpected data", table)
        return
    created = client.post(f"{URL}/rest/v1/{table}", headers=_server_headers(), json=row)
    assert created.status_code == 201, (table, created.status_code, created.text)


def seed_catalog(client: httpx.Client) -> None:
    """Insert only the minimal synthetic tenant/plan facts; safe to call twice."""
    _local_only()
    _ensure(client, "universities", {"id": FAKE_UNIVERSITY_ID,
             "name_ar": "جامعة مرشدي التجريبية الخيالية", "name_en": "Morshidi Fictional Sandbox University",
             "country": "SYNTHETIC", "active": True})
    _ensure(client, "faculties", {"id": FACULTY_ID, "university_id": FAKE_UNIVERSITY_ID,
             "code": "SYN-ENG", "name_ar": "كلية تجريبية", "name_en": "Fictional Faculty"})
    _ensure(client, "majors", {"id": MAJOR_ID, "faculty_id": FACULTY_ID,
             "code": "SYN-CS", "name_ar": "تخصص تجريبي", "name_en": "Fictional Major"})
    _ensure(client, "study_plans", {"id": PLAN_ID, "major_id": MAJOR_ID,
             "plan_number": "P10-SYNTHETIC", "total_credit_hours": 12,
             "effective_year": 2026, "status": "active"})
    _ensure(client, "requirement_groups", {"id": GROUP_ID, "study_plan_id": PLAN_ID,
             "group_code": "SYN-CORE", "name_ar": "مجموعة تجريبية",
             "scope": "major", "requirement_type": "required", "required_credit_hours": 12})
    for index, (code, identifier) in enumerate(COURSES.items()):
        _ensure(client, "courses", {"id": identifier, "university_id": FAKE_UNIVERSITY_ID,
                 "course_code": code, "name_en": f"Fictional {code}", "catalog_status": "known"})
        _ensure(client, "study_plan_courses", {
            "id": f"f1000000-0000-0000-0000-{40 + index:012d}",
            "study_plan_id": PLAN_ID, "course_id": identifier,
            "requirement_group_id": GROUP_ID, "credit_hours": 3,
            "prerequisite_logic_status": "not_applicable", "verification_status": "verified",
            "display_order": index,
        })
    _ensure(client, "mock_registration_target_periods", {
        "id": PERIOD_ID, "university_id": FAKE_UNIVERSITY_ID,
        "provider_namespace": NAMESPACE, "period_key": FAKE_PERIOD,
        "period_class": "SYNTHETIC_SANDBOX_PERIOD",
        "verified_provider_source": False, "source_version": "p10-synthetic-v1",
    })
    # A minimal second fictional identity is only an isolation sentinel. It has
    # no P10 period, offering provider, analyst, or institutional demand.
    _ensure(client, "universities", {"id": FOREIGN_UNIVERSITY_ID,
             "name_ar": "جامعة حدود تجريبية خيالية", "name_en": "Fictional Isolation Sentinel University",
             "country": "SYNTHETIC", "active": True})
    _ensure(client, "faculties", {"id": FOREIGN_FACULTY_ID,
             "university_id": FOREIGN_UNIVERSITY_ID, "name_ar": "كلية حدود خيالية"})
    _ensure(client, "majors", {"id": FOREIGN_MAJOR_ID, "faculty_id": FOREIGN_FACULTY_ID,
             "name_ar": "تخصص حدود خيالي"})
    _ensure(client, "study_plans", {"id": FOREIGN_PLAN_ID, "major_id": FOREIGN_MAJOR_ID,
             "plan_number": "P10-ISOLATION-ONLY", "total_credit_hours": 3, "status": "active"})
    _ensure(client, "requirement_groups", {"id": FOREIGN_GROUP_ID, "study_plan_id": FOREIGN_PLAN_ID,
             "group_code": "SYN-FOREIGN", "name_ar": "مجموعة حدود خيالية",
             "scope": "major", "requirement_type": "required", "required_credit_hours": 3})
    _ensure(client, "courses", {"id": FOREIGN_COURSE_ID,
             "university_id": FOREIGN_UNIVERSITY_ID, "course_code": "CS101",
             "name_en": "Fictional Foreign CS101", "catalog_status": "known"})
    _ensure(client, "study_plan_courses", {
        "id": "f1000000-0000-0000-0000-000000000056",
        "study_plan_id": FOREIGN_PLAN_ID, "course_id": FOREIGN_COURSE_ID,
        "requirement_group_id": FOREIGN_GROUP_ID, "credit_hours": 3,
        "prerequisite_logic_status": "not_applicable", "verification_status": "verified",
    })


def synthetic_p6_demand(owner_count: int):
    """Run the real P6 privacy aggregator on ephemeral synthetic facts, no DB write."""
    if owner_count not in {1, 2}:
        raise ValueError("P10 synthetic demand supports only one or two owners")
    period = TargetPeriod(FAKE_UNIVERSITY_ID, FAKE_PERIOD,
                          TargetPeriodClass.SYNTHETIC_SANDBOX_PERIOD, "p10-synthetic-v1")
    records = []
    for number in range(owner_count):
        intent = RegistrationIntent(
            f"p10-ephemeral-intent-{number}", f"p10-ephemeral-owner-{number}",
            FAKE_UNIVERSITY_ID, MAJOR_ID, PLAN_ID, "p10-synthetic-v1", period, 1,
            IntentLifecycle.SUBMITTED, ("CS101",),
            IntentProvenance.SYNTHETIC_SANDBOX_INTENT, "p10-ephemeral:v1",
        )
        validated = ValidatedIntent(intent, ("CS101",), "0" * 64,
                                    ValidationStatus.VALID, (), (), Decimal("3"), (), ())
        records.append(ResolvedIntent(validated, ResolutionDisposition.CURRENT))
    return aggregate_institutional_demand(DemandAggregationInput(
        AggregationScope(FAKE_UNIVERSITY_ID), period, tuple(records),
        (PlanCourseFact(FAKE_UNIVERSITY_ID, MAJOR_ID, PLAN_ID, "p10-synthetic-v1",
                        "CS101", GROUP_ID, Decimal("3"), "p10-synthetic-v1"),),
        PrivacyConfiguration(2, "p10-synthetic-privacy:v1"),
        AggregationLimits(2, 4), CoverageInput(owner_count, True),
        source_versions=("p10-ephemeral:v1",),
    ))


@contextmanager
def synthetic_principals(client: httpx.Client):
    """Create authenticated student/analyst; remove access before Auth teardown."""
    _local_only()
    users: list[str] = []
    try:
        student, student_token = _create_user(client, "p10-fictional-student")
        users.append(student)
        analyst, analyst_token = _create_user(client, "p10-fictional-analyst")
        users.append(analyst)
        outsider, outsider_token = _create_user(client, "p10-fictional-outsider")
        users.append(outsider)
        profile = client.post(f"{URL}/rest/v1/student_academic_profiles",
                              headers=_server_headers(),
                              json={"owner_user_id": student, "study_plan_id": PLAN_ID})
        assert profile.status_code == 201, profile.status_code
        foreign_profile = client.post(f"{URL}/rest/v1/student_academic_profiles",
                                      headers=_server_headers(),
                                      json={"owner_user_id": outsider, "study_plan_id": FOREIGN_PLAN_ID})
        assert foreign_profile.status_code == 201, foreign_profile.status_code
        membership = client.post(f"{URL}/rest/v1/institutional_memberships",
                                 headers=_server_headers(), json={
                                     "subject_user_id": analyst, "university_id": FAKE_UNIVERSITY_ID,
                                     "provider_namespace": NAMESPACE, "role": "INSTITUTIONAL_ANALYST",
                                     "active": True, "authority_source": "P10_SYNTHETIC_TEST",
                                     "authority_source_version": "v1",
                                 })
        assert membership.status_code == 201, membership.status_code
        yield {"student": student_token, "analyst": analyst_token, "outsider": outsider_token,
               "student_id": student, "analyst_id": analyst, "outsider_id": outsider}
    finally:
        for table, column, identifier in (
            ("institutional_memberships", "subject_user_id", users[1] if len(users) > 1 else None),
            ("student_academic_profiles", "owner_user_id", users[0] if users else None),
            ("student_academic_profiles", "owner_user_id", users[2] if len(users) > 2 else None),
        ):
            if identifier:
                deleted = client.delete(f"{URL}/rest/v1/{table}", headers=_server_headers(),
                                        params={column: f"eq.{identifier}"})
                deleted.raise_for_status()
        for identifier in reversed(users):
            deleted = client.delete(f"{URL}/auth/v1/admin/users/{identifier}",
                                    headers=_server_headers())
            deleted.raise_for_status()
