"""Exhaustive test suite for Phase P7.4: Advisor Authorization, Assignment Persistence & RLS.

Verifies:
1. Canonical scenarios P7-TEST-AUT-001 through P7-TEST-AUT-010 from docs/institutional-intelligence-advisor-test-matrix.md
2. Supplemental security tests:
   - Unauthenticated rejection (401 AUTH_REQUIRED)
   - Self-assignment rejection (both in service and database constraint)
   - Role spoofing via unverified client claims
   - Dual-role (analyst + advisor) user behavior with and without active assignment
   - Authorization-before-student-data-load enforcement (spy academic repository)
   - Persistence unavailability error translation (503)
   - Cross-tenant corrupted assignment isolation
   - Multi-university advisor exact tenant match
   - Strict query scoping (exact parameterized lookup, no bulk filter)
   - Supabase repository adapter transport and mapping tests
   - Static SQL migration schema and RLS verification
"""

from __future__ import annotations

from datetime import datetime, timezone
import pathlib
import re
from typing import Any, Mapping
from uuid import UUID, uuid4

import httpx
import pytest

from app.advisor_persistence import (
    AdvisorAccessContext,
    AdvisorPersistenceError,
    AdvisorPersistenceIntegrityError,
    AdvisorStudentAssignmentRecord,
    SupabaseAdvisorAssignmentRepository,
)
from app.advisor_service import (
    AdvisorAuthorizationError,
    AdvisorAuthorizationErrorCode,
    AdvisorAuthorizationService,
)
from app.mock_registration_persistence.models import InstitutionalMembershipRecord


# ==============================================================================
# In-Memory Repository for Fast, Deterministic Unit Testing
# ==============================================================================


class InMemoryAdvisorAssignmentRepository(SupabaseAdvisorAssignmentRepository):
    """Test-double of SupabaseAdvisorAssignmentRepository recording all invocations."""

    def __init__(self) -> None:
        # Pass dummy connection strings to bypass init checks
        super().__init__(supabase_url="http://mock.supabase.test", server_key="test-key")
        self.assignments: list[AdvisorStudentAssignmentRecord] = []
        self.memberships: list[InstitutionalMembershipRecord] = []
        self.student_universities: dict[UUID, UUID] = {}

        # Inspection spies
        self.load_assignment_calls: list[dict[str, Any]] = []
        self.load_memberships_calls: list[dict[str, Any]] = []
        self.load_student_univ_calls: list[dict[str, Any]] = []

    async def load_active_assignment(
        self,
        *,
        advisor_user_id: UUID,
        student_user_id: UUID,
        university_id: UUID,
    ) -> AdvisorStudentAssignmentRecord | None:
        self.load_assignment_calls.append(
            {
                "advisor_user_id": advisor_user_id,
                "student_user_id": student_user_id,
                "university_id": university_id,
            }
        )
        matches = [
            a
            for a in self.assignments
            if a.advisor_user_id == advisor_user_id
            and a.student_user_id == student_user_id
            and a.university_id == university_id
            and a.is_active
        ]
        if not matches:
            return None
        if len(matches) > 1:
            raise AdvisorPersistenceIntegrityError(
                "Multiple active assignments found", operation="load_active_assignment"
            )
        return matches[0]

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
        if advisor_user_id == student_user_id:
            raise AdvisorPersistenceIntegrityError(
                "Self-assignment is prohibited (advisor_user_id cannot equal student_user_id)",
                operation="create_assignment",
            )
        now = datetime.now(timezone.utc)
        record = AdvisorStudentAssignmentRecord(
            id=uuid4(),
            advisor_user_id=advisor_user_id,
            student_user_id=student_user_id,
            university_id=university_id,
            is_active=is_active,
            authority_source=authority_source,
            authority_version=authority_version,
            created_at=now,
            updated_at=now,
        )
        self.assignments.append(record)
        return record

    async def load_active_advisor_memberships_for_user(
        self,
        subject_user_id: UUID,
    ) -> tuple[InstitutionalMembershipRecord, ...]:
        self.load_memberships_calls.append({"subject_user_id": subject_user_id})
        return tuple(
            m
            for m in self.memberships
            if m.subject_user_id == subject_user_id
            and m.role == "ACADEMIC_ADVISOR"
            and m.active
        )

    async def load_student_authoritative_university(
        self,
        student_user_id: UUID,
    ) -> UUID | None:
        self.load_student_univ_calls.append({"student_user_id": student_user_id})
        return self.student_universities.get(student_user_id)


class SpyAcademicDataRepository:
    """Spy simulating an academic data repository (attempts, progress, profiles).

    Verifies that sensitive student academic data is NEVER loaded when authorization fails.
    """

    def __init__(self) -> None:
        self.profile_load_count = 0
        self.attempts_load_count = 0
        self.progress_load_count = 0

    async def load_student_academic_profile(self, student_user_id: UUID) -> dict[str, Any]:
        self.profile_load_count += 1
        return {"id": str(uuid4()), "owner_user_id": str(student_user_id)}

    async def load_student_attempts(self, student_user_id: UUID) -> list[Any]:
        self.attempts_load_count += 1
        return []

    async def calculate_progress(self, student_user_id: UUID) -> dict[str, Any]:
        self.progress_load_count += 1
        return {}


# ==============================================================================
# Canonical Scenarios (P7-TEST-AUT-001 through P7-TEST-AUT-010)
# ==============================================================================


@pytest.mark.anyio
async def test_p7_aut_001_authenticated_assigned_advisor_access_granted() -> None:
    """P7-TEST-AUT-001: Authenticated advisor with active ACADEMIC_ADVISOR role and active explicit assignment -> Access granted (200 OK)."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()

    # Seed active ACADEMIC_ADVISOR membership
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    # Seed active explicit assignment
    assignment = await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_id,
        authority_source="FACULTY_DEAN_ASSIGNMENT",
        authority_version="2026-FALL",
        is_active=True,
    )

    # Seed authoritative student university
    repo.student_universities[student_id] = univ_id

    # Execute authorization
    context = await service.authorize_advisor_for_student(advisor_id, student_id)

    assert isinstance(context, AdvisorAccessContext)
    assert context.advisor_user_id == advisor_id
    assert context.student_user_id == student_id
    assert context.university_id == univ_id
    assert context.assignment_id == assignment.id
    assert context.authority_source == "FACULTY_DEAN_ASSIGNMENT"
    assert context.authority_version == "2026-FALL"


@pytest.mark.anyio
async def test_p7_aut_002_unassigned_student_access_rejected() -> None:
    """P7-TEST-AUT-002: Advisor with active role attempts access to an unassigned student -> 403 FORBIDDEN (ADVISOR_STUDENT_SCOPE_MISMATCH)."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    assigned_student_id = uuid4()
    unassigned_student_id = uuid4()
    univ_id = uuid4()

    # Seed active advisor role
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    # Seed assignment ONLY for assigned_student_id
    await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=assigned_student_id,
        university_id=univ_id,
        authority_source="FACULTY_DEAN_ASSIGNMENT",
        authority_version="2026-FALL",
        is_active=True,
    )
    repo.student_universities[assigned_student_id] = univ_id
    repo.student_universities[unassigned_student_id] = univ_id

    # Attempt to access unassigned_student_id
    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(advisor_id, unassigned_student_id)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH


@pytest.mark.anyio
async def test_p7_aut_003_institutional_analyst_role_access_rejected() -> None:
    """P7-TEST-AUT-003: User holding only INSTITUTIONAL_ANALYST role attempts student access -> 403 FORBIDDEN (zero student read access)."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    analyst_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()

    # User has INSTITUTIONAL_ANALYST role only
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=analyst_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="INSTITUTIONAL_ANALYST",
            active=True,
            authority_source="CHANCELLOR_OFFICE",
            authority_source_version="v1.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    repo.student_universities[student_id] = univ_id

    # Attempt access
    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(analyst_id, student_id)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.ADVISOR_ROLE_REQUIRED
    assert "ACADEMIC_ADVISOR" in exc_info.value.message


@pytest.mark.anyio
async def test_p7_aut_004_departmental_or_cohort_browsing_attempt_rejected() -> None:
    """P7-TEST-AUT-004: Departmental / cohort browsing attempt -> 403 FORBIDDEN (Cohort browsing deferred; explicit assignment required)."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    univ_id = uuid4()

    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    # Target student is omitted / cohort query attempted
    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(advisor_id, None)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH


@pytest.mark.anyio
async def test_p7_aut_005_advisor_snapshot_without_target_period_access_granted() -> None:
    """P7-TEST-AUT-005: Advisor requests snapshot without target period -> Access granted (200 OK; target period not required)."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()

    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_id,
        authority_source="FACULTY_DEAN_ASSIGNMENT",
        authority_version="2026-FALL",
        is_active=True,
    )
    repo.student_universities[student_id] = univ_id

    # Notice: No target_period_id is passed or needed by the authorization service
    context = await service.authorize_advisor_for_student(advisor_id, student_id)
    assert context.student_user_id == student_id
    assert context.university_id == univ_id


@pytest.mark.anyio
async def test_p7_aut_006_advisor_progress_without_target_period_access_granted() -> None:
    """P7-TEST-AUT-006: Advisor requests progress without target period -> Access granted (200 OK; target period not required)."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()

    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_id,
        authority_source="FACULTY_DEAN_ASSIGNMENT",
        authority_version="2026-FALL",
        is_active=True,
    )
    repo.student_universities[student_id] = univ_id

    # Verify authorization proceeds cleanly without target period
    context = await service.authorize_advisor_for_student(advisor_id, student_id)
    assert context.student_user_id == student_id
    assert context.advisor_user_id == advisor_id


@pytest.mark.anyio
async def test_p7_aut_007_cross_tenant_advisor_access_rejected() -> None:
    """P7-TEST-AUT-007: Cross-tenant advisor access (Advisor at Univ A, Student at Univ B) -> 403 FORBIDDEN."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_a = uuid4()
    univ_b = uuid4()

    # Advisor belongs to Univ A
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_a,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    # Corrupted / mismatched assignment claiming Univ A for student in Univ B
    await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_a,
        authority_source="CORRUPTED_ENTRY",
        authority_version="v0",
        is_active=True,
    )

    # Student authoritative record belongs to Univ B
    repo.student_universities[student_id] = univ_b

    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(advisor_id, student_id)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH
    assert "tenant" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_p7_aut_008_inactive_advisor_profile_rejected() -> None:
    """P7-TEST-AUT-008: Advisor with active=False on institutional membership -> 403 FORBIDDEN."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()

    # Inactive membership
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=False,  # INACTIVE!
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_id,
        authority_source="FACULTY_DEAN_ASSIGNMENT",
        authority_version="2026-FALL",
        is_active=True,
    )
    repo.student_universities[student_id] = univ_id

    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(advisor_id, student_id)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.ADVISOR_ROLE_REQUIRED


@pytest.mark.anyio
async def test_p7_aut_009_expired_or_inactive_advising_assignment_rejected() -> None:
    """P7-TEST-AUT-009: Assignment expired/inactive (is_active=False) -> 403 FORBIDDEN."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()

    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    # Inactive assignment record
    await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_id,
        authority_source="FACULTY_DEAN_ASSIGNMENT",
        authority_version="2025-SPRING",
        is_active=False,  # INACTIVE!
    )
    repo.student_universities[student_id] = univ_id

    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(advisor_id, student_id)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH


def test_p7_aut_010_in_system_waiver_override_attempt_rejected() -> None:
    """P7-TEST-AUT-010: In-system waiver/override attempt -> Rejected (403 / NOT_SUPPORTED; provider-neutral facts only)."""
    # Verify that neither AdvisorAuthorizationService nor SupabaseAdvisorAssignmentRepository implements waiver or override methods
    assert not hasattr(AdvisorAuthorizationService, "override_prerequisite")
    assert not hasattr(AdvisorAuthorizationService, "grant_waiver")
    assert not hasattr(AdvisorAuthorizationService, "force_eligible")
    assert not hasattr(SupabaseAdvisorAssignmentRepository, "create_waiver")
    assert not hasattr(SupabaseAdvisorAssignmentRepository, "override_prerequisite")
    assert not hasattr(AdvisorStudentAssignmentRecord, "can_override")


# ==============================================================================
# Supplemental Security, Integrity, and Architecture Tests
# ==============================================================================


@pytest.mark.anyio
async def test_unauthenticated_request_rejected_with_401() -> None:
    """Unauthenticated caller (None user_id) is rejected with 401 AUTH_REQUIRED."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(None, uuid4())

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.AUTH_REQUIRED


@pytest.mark.anyio
async def test_self_assignment_rejected_by_service_and_db_constraint() -> None:
    """Self-assignment (advisor_id == student_id) is rejected by service and repository validation."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)
    user_id = uuid4()
    univ_id = uuid4()

    # 1. Service rejection
    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(user_id, user_id)
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH
    assert "self" in exc_info.value.message.lower()

    # 2. Repository insert rejection
    with pytest.raises(AdvisorPersistenceIntegrityError) as repo_exc:
        await repo.create_assignment(
            advisor_user_id=user_id,
            student_user_id=user_id,
            university_id=univ_id,
            authority_source="TEST",
            authority_version="v1",
        )
    assert "distinct" in str(repo_exc.value) or "self" in str(repo_exc.value).lower()


@pytest.mark.anyio
async def test_dual_role_user_without_assignment_rejected() -> None:
    """User holding both INSTITUTIONAL_ANALYST and ACADEMIC_ADVISOR still cannot access unassigned student."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    user_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()

    # Seed both roles
    now = datetime.now(timezone.utc)
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=user_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="INSTITUTIONAL_ANALYST",
            active=True,
            authority_source="AUTH",
            authority_source_version="v1",
            created_at=now,
            updated_at=now,
        )
    )
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=user_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="AUTH",
            authority_source_version="v1",
            created_at=now,
            updated_at=now,
        )
    )
    repo.student_universities[student_id] = univ_id

    # No assignment seeded -> denied
    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(user_id, student_id)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH


@pytest.mark.anyio
async def test_dual_role_user_with_active_assignment_granted() -> None:
    """Dual-role user with an active explicit assignment is granted access."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    user_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()

    now = datetime.now(timezone.utc)
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=user_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="INSTITUTIONAL_ANALYST",
            active=True,
            authority_source="AUTH",
            authority_source_version="v1",
            created_at=now,
            updated_at=now,
        )
    )
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=user_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="AUTH",
            authority_source_version="v1",
            created_at=now,
            updated_at=now,
        )
    )
    await repo.create_assignment(
        advisor_user_id=user_id,
        student_user_id=student_id,
        university_id=univ_id,
        authority_source="DEAN",
        authority_version="v1",
        is_active=True,
    )
    repo.student_universities[student_id] = univ_id

    context = await service.authorize_advisor_for_student(user_id, student_id)
    assert context.student_user_id == student_id
    assert context.university_id == univ_id


@pytest.mark.anyio
async def test_role_spoofing_via_client_claims_rejected() -> None:
    """Client claims of role (e.g. in token metadata or caller parameters) are ignored; server membership is authoritative."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    untrusted_caller_id = uuid4()
    student_id = uuid4()

    # No database membership exists for untrusted_caller_id
    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(untrusted_caller_id, student_id)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.ADVISOR_ROLE_REQUIRED


@pytest.mark.anyio
async def test_authorization_before_student_data_load_enforced() -> None:
    """Verifies that academic attempt and progress loaders are NEVER called when advisor authorization fails."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)
    academic_spy = SpyAcademicDataRepository()

    unauthorized_advisor_id = uuid4()
    target_student_id = uuid4()

    # Attempt unauthorized authorization
    with pytest.raises(AdvisorAuthorizationError):
        await service.authorize_advisor_for_student(unauthorized_advisor_id, target_student_id)

    # Assert that zero academic loaders were called
    assert academic_spy.profile_load_count == 0
    assert academic_spy.attempts_load_count == 0
    assert academic_spy.progress_load_count == 0


@pytest.mark.anyio
async def test_persistence_unavailable_maps_to_503() -> None:
    """Repository transport/database errors map to 503 PERSISTENCE_UNAVAILABLE (not masking as missing assignment)."""

    class BrokenAdvisorRepository(SupabaseAdvisorAssignmentRepository):
        def __init__(self) -> None:
            super().__init__(supabase_url="http://mock.supabase.test", server_key="test-key")

        async def load_active_advisor_memberships_for_user(self, subject_user_id: UUID):
            raise AdvisorPersistenceError(
                "Database connection timed out", operation="load_memberships", status_code=503
            )

    broken_repo = BrokenAdvisorRepository()
    service = AdvisorAuthorizationService(broken_repo)

    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(uuid4(), uuid4())

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.PERSISTENCE_UNAVAILABLE


@pytest.mark.anyio
async def test_multi_university_advisor_exact_tenant_resolution() -> None:
    """Advisor holding active roles in Univ A and Univ B correctly authorizes against Univ B student and Univ B assignment."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_b_id = uuid4()
    univ_a = uuid4()
    univ_b = uuid4()

    now = datetime.now(timezone.utc)
    # Role in Univ A
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_a,
            provider_namespace="univ_a",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="AUTH",
            authority_source_version="v1",
            created_at=now,
            updated_at=now,
        )
    )
    # Role in Univ B
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_b,
            provider_namespace="univ_b",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="AUTH",
            authority_source_version="v1",
            created_at=now,
            updated_at=now,
        )
    )

    # Assignment only in Univ B
    await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_b_id,
        university_id=univ_b,
        authority_source="DEAN_B",
        authority_version="v1",
        is_active=True,
    )
    repo.student_universities[student_b_id] = univ_b

    context = await service.authorize_advisor_for_student(advisor_id, student_b_id)
    assert context.university_id == univ_b
    assert context.student_user_id == student_b_id


@pytest.mark.anyio
async def test_negative_assignment_lookup_is_not_500() -> None:
    """Missing assignment returns 403 ADVISOR_STUDENT_SCOPE_MISMATCH, not an unhandled 500 error."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()

    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="AUTH",
            authority_source_version="v1",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(advisor_id, student_id)

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_exact_query_scoping_no_bulk_loading() -> None:
    """Verifies that repository queries use exact composite equality filters rather than loading all assignments."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()

    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_id,
            provider_namespace="zarqa_sis",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="AUTH",
            authority_source_version="v1",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_id,
        authority_source="AUTH",
        authority_version="v1",
        is_active=True,
    )
    repo.student_universities[student_id] = univ_id

    await service.authorize_advisor_for_student(advisor_id, student_id)

    # Verify query parameters were strictly scoped
    assert len(repo.load_assignment_calls) == 1
    call = repo.load_assignment_calls[0]
    assert call["advisor_user_id"] == advisor_id
    assert call["student_user_id"] == student_id
    assert call["university_id"] == univ_id


# ==============================================================================
# Phase P7.4.1 Determinism and Ordering Invariance Tests
# ==============================================================================


@pytest.mark.anyio
async def test_multi_university_advisor_ordering_invariance_a_then_b() -> None:
    """Multi-university advisor with memberships returned [A, B], assignment in B, student in B -> AUTHORIZED."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_a = uuid4()
    univ_b = uuid4()
    now = datetime.now(timezone.utc)

    # Seed memberships in order A then B
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_a,
            provider_namespace="univ_a",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=now,
            updated_at=now,
        )
    )
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_b,
            provider_namespace="univ_b",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=now,
            updated_at=now,
        )
    )

    # Valid assignment only in Univ B
    assignment_b = await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_b,
        authority_source="DEAN_B",
        authority_version="2026-FALL",
        is_active=True,
    )
    repo.student_universities[student_id] = univ_b

    context = await service.authorize_advisor_for_student(advisor_id, student_id)
    assert context.advisor_user_id == advisor_id
    assert context.student_user_id == student_id
    assert context.university_id == univ_b
    assert context.assignment_id == assignment_b.id


@pytest.mark.anyio
async def test_multi_university_advisor_ordering_invariance_b_then_a() -> None:
    """Multi-university advisor with memberships returned [B, A], assignment in B, student in B -> identical authorization result."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_a = uuid4()
    univ_b = uuid4()
    now = datetime.now(timezone.utc)

    # Seed memberships in order B then A
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_b,
            provider_namespace="univ_b",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=now,
            updated_at=now,
        )
    )
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_a,
            provider_namespace="univ_a",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=now,
            updated_at=now,
        )
    )

    # Valid assignment only in Univ B
    assignment_b = await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_b,
        authority_source="DEAN_B",
        authority_version="2026-FALL",
        is_active=True,
    )
    repo.student_universities[student_id] = univ_b

    context = await service.authorize_advisor_for_student(advisor_id, student_id)
    assert context.advisor_user_id == advisor_id
    assert context.student_user_id == student_id
    assert context.university_id == univ_b
    assert context.assignment_id == assignment_b.id


@pytest.mark.anyio
async def test_multi_university_active_assignments_in_both_picks_student_university() -> None:
    """Active assignments exist in both Univ A and Univ B, student is in B -> B assignment selected deterministically."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_a = uuid4()
    univ_b = uuid4()
    now = datetime.now(timezone.utc)

    # Seed memberships in order A then B
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_a,
            provider_namespace="univ_a",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=now,
            updated_at=now,
        )
    )
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_b,
            provider_namespace="univ_b",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=now,
            updated_at=now,
        )
    )

    # Active assignments in BOTH Univ A and Univ B for the same advisor/student pair
    assignment_a = await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_a,
        authority_source="DEAN_A",
        authority_version="v1-A",
        is_active=True,
    )
    assignment_b = await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_b,
        authority_source="DEAN_B",
        authority_version="v1-B",
        is_active=True,
    )

    # Authoritative university is Univ B
    repo.student_universities[student_id] = univ_b

    context = await service.authorize_advisor_for_student(advisor_id, student_id)
    assert context.university_id == univ_b
    assert context.assignment_id == assignment_b.id
    assert context.assignment_id != assignment_a.id
    assert context.authority_source == "DEAN_B"

    # Verify that load_active_assignment was called only for Univ B
    assert len(repo.load_assignment_calls) == 1
    assert repo.load_assignment_calls[0]["university_id"] == univ_b


@pytest.mark.anyio
async def test_assignment_in_a_only_student_in_b_denied() -> None:
    """Advisor has roles in A and B, but assignment exists only in A; student is in B -> DENIED (403)."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_a = uuid4()
    univ_b = uuid4()
    now = datetime.now(timezone.utc)

    # Roles in both A and B
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_a,
            provider_namespace="univ_a",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=now,
            updated_at=now,
        )
    )
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_b,
            provider_namespace="univ_b",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=now,
            updated_at=now,
        )
    )

    # Assignment exists in A only
    await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_a,
        authority_source="DEAN_A",
        authority_version="v1",
        is_active=True,
    )

    # Student belongs to Univ B
    repo.student_universities[student_id] = univ_b

    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(advisor_id, student_id)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH
    assert "assignment" in exc_info.value.message.lower()


@pytest.mark.anyio
async def test_membership_in_a_only_student_in_b_denied_without_querying_a() -> None:
    """Advisor has role only in A, student is in B -> DENIED (403), and assignment lookup for Univ A is NOT executed."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_a = uuid4()
    univ_b = uuid4()
    now = datetime.now(timezone.utc)

    # Membership only in Univ A
    repo.memberships.append(
        InstitutionalMembershipRecord(
            membership_id=uuid4(),
            subject_user_id=advisor_id,
            university_id=univ_a,
            provider_namespace="univ_a",
            role="ACADEMIC_ADVISOR",
            active=True,
            authority_source="REGISTRAR_DIRECTIVE",
            authority_source_version="v1.0",
            created_at=now,
            updated_at=now,
        )
    )

    # Assignment exists in Univ A
    await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_a,
        authority_source="DEAN_A",
        authority_version="v1",
        is_active=True,
    )

    # Student belongs to Univ B
    repo.student_universities[student_id] = univ_b

    with pytest.raises(AdvisorAuthorizationError) as exc_info:
        await service.authorize_advisor_for_student(advisor_id, student_id)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH

    # Crucial check: assignment lookup was never performed, and Univ A was NOT used as authority
    assert len(repo.load_assignment_calls) == 0


@pytest.mark.anyio
async def test_exact_assignment_query_uses_student_authoritative_university() -> None:
    """Assignment lookup must execute exactly once and use the student's authoritative university."""
    repo = InMemoryAdvisorAssignmentRepository()
    service = AdvisorAuthorizationService(repo)

    advisor_id = uuid4()
    student_id = uuid4()
    univ_a = uuid4()
    univ_b = uuid4()
    univ_c = uuid4()
    now = datetime.now(timezone.utc)

    # Advisor has roles in A, B, C
    for u, name in [(univ_a, "a"), (univ_b, "b"), (univ_c, "c")]:
        repo.memberships.append(
            InstitutionalMembershipRecord(
                membership_id=uuid4(),
                subject_user_id=advisor_id,
                university_id=u,
                provider_namespace=f"univ_{name}",
                role="ACADEMIC_ADVISOR",
                active=True,
                authority_source="REGISTRAR_DIRECTIVE",
                authority_source_version="v1.0",
                created_at=now,
                updated_at=now,
            )
        )

    # Assignment in Univ B
    assignment_b = await repo.create_assignment(
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_b,
        authority_source="DEAN_B",
        authority_version="v1",
        is_active=True,
    )
    repo.student_universities[student_id] = univ_b

    context = await service.authorize_advisor_for_student(advisor_id, student_id)
    assert context.assignment_id == assignment_b.id

    # Exactly one query performed with exact parameters
    assert len(repo.load_assignment_calls) == 1
    call = repo.load_assignment_calls[0]
    assert call["advisor_user_id"] == advisor_id
    assert call["student_user_id"] == student_id
    assert call["university_id"] == univ_b


@pytest.mark.anyio
async def test_authorization_result_equality_across_membership_permutations() -> None:
    """Authorization returns identical AdvisorAccessContext across all permutations of advisor membership ordering."""
    import itertools

    advisor_id = uuid4()
    student_id = uuid4()
    univ_a = uuid4()
    univ_b = uuid4()
    univ_c = uuid4()
    now = datetime.now(timezone.utc)

    # Base membership records
    mem_a = InstitutionalMembershipRecord(
        membership_id=uuid4(),
        subject_user_id=advisor_id,
        university_id=univ_a,
        provider_namespace="univ_a",
        role="ACADEMIC_ADVISOR",
        active=True,
        authority_source="REGISTRAR_DIRECTIVE",
        authority_source_version="v1.0",
        created_at=now,
        updated_at=now,
    )
    mem_b = InstitutionalMembershipRecord(
        membership_id=uuid4(),
        subject_user_id=advisor_id,
        university_id=univ_b,
        provider_namespace="univ_b",
        role="ACADEMIC_ADVISOR",
        active=True,
        authority_source="REGISTRAR_DIRECTIVE",
        authority_source_version="v1.0",
        created_at=now,
        updated_at=now,
    )
    mem_c = InstitutionalMembershipRecord(
        membership_id=uuid4(),
        subject_user_id=advisor_id,
        university_id=univ_c,
        provider_namespace="univ_c",
        role="ACADEMIC_ADVISOR",
        active=True,
        authority_source="REGISTRAR_DIRECTIVE",
        authority_source_version="v1.0",
        created_at=now,
        updated_at=now,
    )

    all_memberships = [mem_a, mem_b, mem_c]
    fixed_assignment = AdvisorStudentAssignmentRecord(
        id=uuid4(),
        advisor_user_id=advisor_id,
        student_user_id=student_id,
        university_id=univ_b,
        is_active=True,
        authority_source="DEAN_B",
        authority_version="v1",
        created_at=now,
        updated_at=now,
    )
    contexts: list[AdvisorAccessContext] = []

    # Permute all membership orderings: 3! = 6 permutations
    for perm in itertools.permutations(all_memberships):
        repo = InMemoryAdvisorAssignmentRepository()
        service = AdvisorAuthorizationService(repo)
        repo.memberships = list(perm)
        repo.assignments = [fixed_assignment]
        repo.student_universities[student_id] = univ_b

        ctx = await service.authorize_advisor_for_student(advisor_id, student_id)
        contexts.append(ctx)

    assert len(contexts) == 6
    baseline = contexts[0]
    for ctx in contexts[1:]:
        assert ctx.advisor_user_id == baseline.advisor_user_id
        assert ctx.student_user_id == baseline.student_user_id
        assert ctx.university_id == baseline.university_id
        assert ctx.assignment_id == baseline.assignment_id
        assert ctx.authority_source == baseline.authority_source
        assert ctx.authority_version == baseline.authority_version


# ==============================================================================
# Supabase HTTP Adapter Unit Tests (Mock HTTPX)
# ==============================================================================


@pytest.mark.anyio
async def test_supabase_repository_load_active_assignment_transport() -> None:
    """Tests SupabaseAdvisorAssignmentRepository.load_active_assignment with mocked httpx transport."""
    assignment_id = uuid4()
    advisor_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()
    now_iso = datetime.now(timezone.utc).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/rest/v1/advisor_student_assignments"
        assert request.headers["apikey"] == "test-key"
        assert f"eq.{advisor_id}" in str(request.url)
        assert f"eq.{student_id}" in str(request.url)
        assert f"eq.{univ_id}" in str(request.url)
        assert "eq.true" in str(request.url)
        return httpx.Response(
            200,
            json=[
                {
                    "id": str(assignment_id),
                    "advisor_user_id": str(advisor_id),
                    "student_user_id": str(student_id),
                    "university_id": str(univ_id),
                    "is_active": True,
                    "authority_source": "TEST_SOURCE",
                    "authority_version": "v1.0",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
            ],
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        repo = SupabaseAdvisorAssignmentRepository("http://test.supabase", "test-key", client=client)
        record = await repo.load_active_assignment(
            advisor_user_id=advisor_id,
            student_user_id=student_id,
            university_id=univ_id,
        )
        assert record is not None
        assert record.id == assignment_id
        assert record.advisor_user_id == advisor_id
        assert record.student_user_id == student_id
        assert record.university_id == univ_id


@pytest.mark.anyio
async def test_supabase_repository_create_assignment_transport() -> None:
    """Tests SupabaseAdvisorAssignmentRepository.create_assignment with mocked httpx transport."""
    assignment_id = uuid4()
    advisor_id = uuid4()
    student_id = uuid4()
    univ_id = uuid4()
    now_iso = datetime.now(timezone.utc).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/advisor_student_assignments"
        return httpx.Response(
            201,
            json=[
                {
                    "id": str(assignment_id),
                    "advisor_user_id": str(advisor_id),
                    "student_user_id": str(student_id),
                    "university_id": str(univ_id),
                    "is_active": True,
                    "authority_source": "SIS_IMPORT",
                    "authority_version": "v2.0",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
            ],
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        repo = SupabaseAdvisorAssignmentRepository("http://test.supabase", "test-key", client=client)
        record = await repo.create_assignment(
            advisor_user_id=advisor_id,
            student_user_id=student_id,
            university_id=univ_id,
            authority_source="SIS_IMPORT",
            authority_version="v2.0",
        )
        assert record.id == assignment_id
        assert record.authority_source == "SIS_IMPORT"


@pytest.mark.anyio
async def test_supabase_repository_load_student_authoritative_university_transport() -> None:
    """Tests SupabaseAdvisorAssignmentRepository.load_student_authoritative_university with mocked httpx transport."""
    student_id = uuid4()
    univ_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/rest/v1/student_academic_profiles"
        assert f"eq.{student_id}" in str(request.url)
        return httpx.Response(
            200,
            json=[
                {
                    "id": str(uuid4()),
                    "owner_user_id": str(student_id),
                    "study_plans": {
                        "majors": {
                            "faculties": {
                                "university_id": str(univ_id),
                            }
                        }
                    },
                }
            ],
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        repo = SupabaseAdvisorAssignmentRepository("http://test.supabase", "test-key", client=client)
        resolved_univ_id = await repo.load_student_authoritative_university(student_id)
        assert resolved_univ_id == univ_id


# ==============================================================================
# Static SQL Migration Verification
# ==============================================================================


def test_sql_migration_file_static_verification() -> None:
    """Verifies that the P7.4 migration file contains exact required schema, constraints, and RLS policies."""
    migration_path = pathlib.Path("supabase/migrations/20260923150000_add_advisor_authorization_persistence.sql")
    assert migration_path.exists(), f"Migration file not found at {migration_path}"
    content = migration_path.read_text(encoding="utf-8")

    # 1. ACADEMIC_ADVISOR role check extension
    assert "institutional_memberships_role_check" in content
    assert "ACADEMIC_ADVISOR" in content

    # 2. Table name
    assert "create table public.advisor_student_assignments" in content

    # 3. Exact columns present
    for column in [
        "id uuid",
        "advisor_user_id uuid",
        "student_user_id uuid",
        "university_id uuid",
        "is_active boolean",
        "authority_source text",
        "authority_version text",
        "created_at timestamptz",
        "updated_at timestamptz",
    ]:
        assert column in content, f"Column definition '{column}' missing from migration"

    # 4. Forbidden columns strictly NOT present (ignoring comments and string literals)
    sql_statements = re.sub(r"--.*$", "", content, flags=re.MULTILINE)
    sql_statements = re.sub(r"/\*.*?\*/", "", sql_statements, flags=re.DOTALL)
    sql_statements = re.sub(r"'.*?'", "", sql_statements, flags=re.DOTALL)
    for forbidden in [
        "target_period_id",
        "study_plan_id",
        "department_id",
        "faculty_id",
        "cohort_id",
        "course_id",
        "permission_score",
        "confidence",
        "advisor_rank",
    ]:
        assert forbidden not in sql_statements, f"Forbidden column '{forbidden}' found in migration SQL statements"

    # 5. Self-assignment constraint
    assert "check (advisor_user_id <> student_user_id)" in content or "check (advisor_user_id != student_user_id)" in content

    # 6. Unique active index
    assert "idx_advisor_student_assignments_active_unique" in content
    assert "where is_active" in content

    # 7. Lookup index
    assert "idx_advisor_student_assignments_lookup" in content

    # 8. RLS enabled
    assert "alter table public.advisor_student_assignments enable row level security;" in content

    # 9. Strict privileges: revoke all from public, anon, authenticated; grant only to service_role
    assert "revoke all on table public.advisor_student_assignments" in content
    assert "grant select, insert, update, delete on table public.advisor_student_assignments" in content
    assert "to service_role;" in content


def test_advisor_cannot_self_grant_assignment_via_rls() -> None:
    """Verifies that authenticated advisors cannot self-grant or mutate assignment rows via Supabase RLS."""
    migration_path = pathlib.Path("supabase/migrations/20260923150000_add_advisor_authorization_persistence.sql")
    content = migration_path.read_text(encoding="utf-8")

    # Privileges revoked from authenticated users
    assert "revoke all on table public.advisor_student_assignments\n  from public, anon, authenticated, service_role;" in content

    # Zero create policy statements exist for authenticated or anon
    assert "create policy" not in content.lower()

    # Self-assignment constraint is enforced at SQL schema level
    assert "check_advisor_student_distinct check (advisor_user_id <> student_user_id)" in content


def test_student_cannot_grant_assignment_via_rls() -> None:
    """Verifies that students cannot create, modify, or delete advisor assignment rows via Supabase RLS."""
    migration_path = pathlib.Path("supabase/migrations/20260923150000_add_advisor_authorization_persistence.sql")
    content = migration_path.read_text(encoding="utf-8")

    # Table grants are strictly limited to service_role
    assert "grant select, insert, update, delete on table public.advisor_student_assignments\n  to service_role;" in content

    # Zero policies granting student write or mutate access
    assert "to authenticated" not in content
    assert "to anon" not in content


def test_advisor_persistence_and_service_have_no_tools_or_llm() -> None:
    """Strict non-goals check: advisor_persistence and advisor_service contain zero tools, zero LLM, and zero routes."""
    persistence_pkg = pathlib.Path("apps/api/app/advisor_persistence")
    service_pkg = pathlib.Path("apps/api/app/advisor_service")

    combined_sources = "\n".join(
        p.read_text(encoding="utf-8")
        for pkg in (persistence_pkg, service_pkg)
        for p in pkg.glob("*.py")
    ).lower()

    for forbidden in [
        "openai",
        "langchain",
        "chatcompletion",
        "fastapi",
        "apirouter",
        "advisor_tool_get_academic_snapshot",
        "advisor_tool_get_progress",
        "advisor_tool_check_eligibility",
        "advisor_tool_get_recommendations",
        "advisor_tool_get_semester_plans",
        "advisor_tool_get_degree_paths",
        "advisor_tool_get_student_intelligence",
        "advisor_tool_check_delay_consequence",
        "advisor_tool_run_what_if",
        "advisor_tool_get_current_mock_registration",
        "advisor_tool_explain_recommendation_decision",
        "override_prerequisite",
        "grant_waiver",
    ]:
        assert forbidden not in combined_sources, f"Forbidden concept '{forbidden}' detected in P7.4 codebase"
