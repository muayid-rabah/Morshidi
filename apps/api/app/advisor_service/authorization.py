"""Phase P7.4 Advisor Authorization Service.

Enforces the accepted Phase P7.1 advisor access predicate:
Authenticated user
AND active ACADEMIC_ADVISOR institutional role
AND active explicit advisor-student assignment
AND matching university
AND exact target student
-> advisor access may proceed. Any missing condition -> denied.
"""

from __future__ import annotations

from uuid import UUID

from app.advisor_persistence.errors import AdvisorPersistenceError
from app.advisor_persistence.models import (
    AdvisorAccessContext,
    AdvisorStudentAssignmentRecord,
)
from app.advisor_persistence.repository import (
    SupabaseAdvisorAssignmentRepository,
)
from app.advisor_service.errors import (
    AdvisorAuthorizationError,
    AdvisorAuthorizationErrorCode,
)


class AdvisorAuthorizationService:
    """Server-side authorization gate for academic advisors."""

    def __init__(self, assignment_repo: SupabaseAdvisorAssignmentRepository) -> None:
        self._repo = assignment_repo

    async def authorize_advisor_for_student(
        self,
        authenticated_user_id: UUID | str | None,
        target_student_user_id: UUID | str | None,
    ) -> AdvisorAccessContext:
        """Evaluate the full authorization predicate before any student academic data is loaded.

        Returns an authorized AdvisorAccessContext on success, or raises
        AdvisorAuthorizationError with an appropriate finite code and HTTP status.
        """
        # 1. Authenticated user required
        if authenticated_user_id is None:
            raise AdvisorAuthorizationError(
                code=AdvisorAuthorizationErrorCode.AUTH_REQUIRED,
                message="Authentication required for advisor access",
                status_code=401,
            )
        try:
            auth_uuid = (
                authenticated_user_id
                if isinstance(authenticated_user_id, UUID)
                else UUID(str(authenticated_user_id))
            )
        except (ValueError, TypeError):
            raise AdvisorAuthorizationError(
                code=AdvisorAuthorizationErrorCode.AUTH_REQUIRED,
                message="Invalid authentication subject identifier",
                status_code=401,
            )

        # 2. Target student required
        if target_student_user_id is None:
            raise AdvisorAuthorizationError(
                code=AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH,
                message="Target student identifier required",
                status_code=403,
            )
        try:
            target_student_uuid = (
                target_student_user_id
                if isinstance(target_student_user_id, UUID)
                else UUID(str(target_student_user_id))
            )
        except (ValueError, TypeError):
            raise AdvisorAuthorizationError(
                code=AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH,
                message="Invalid target student identifier",
                status_code=403,
            )

        # 3. Self-assignment rejection
        if auth_uuid == target_student_uuid:
            raise AdvisorAuthorizationError(
                code=AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH,
                message="Self-advising is prohibited",
                status_code=403,
            )

        try:
            # 4. Active ACADEMIC_ADVISOR institutional role check
            memberships = await self._repo.load_active_advisor_memberships_for_user(auth_uuid)
            if not memberships:
                raise AdvisorAuthorizationError(
                    code=AdvisorAuthorizationErrorCode.ADVISOR_ROLE_REQUIRED,
                    message="Authenticated user does not hold an active ACADEMIC_ADVISOR institutional role",
                    status_code=403,
                )

            # 6. Load target student's authoritative university
            student_univ_id = await self._repo.load_student_authoritative_university(target_student_uuid)
            # 7. If authoritative student university is unavailable -> privacy-safe scope denial
            if student_univ_id is None:
                raise AdvisorAuthorizationError(
                    code=AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH,
                    message="Target student tenant scope is unavailable",
                    status_code=403,
                )

            # 8. Verify advisor has an ACTIVE ACADEMIC_ADVISOR membership in that exact student university
            advisor_universities = {m.university_id for m in memberships}
            # 9. If not -> privacy-safe advisor scope denial
            if student_univ_id not in advisor_universities:
                raise AdvisorAuthorizationError(
                    code=AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH,
                    message="Advisor does not hold an active role in student tenant university",
                    status_code=403,
                )

            # 10. Perform exactly ONE active assignment lookup using authoritative student university
            assignment = await self._repo.load_active_assignment(
                advisor_user_id=auth_uuid,
                student_user_id=target_student_uuid,
                university_id=student_univ_id,
            )

            # 11. If no assignment -> privacy-safe advisor scope denial
            if assignment is None:
                raise AdvisorAuthorizationError(
                    code=AdvisorAuthorizationErrorCode.ADVISOR_STUDENT_SCOPE_MISMATCH,
                    message="No active explicit assignment found for target student in tenant university",
                    status_code=403,
                )

        except AdvisorPersistenceError as error:
            raise AdvisorAuthorizationError(
                code=AdvisorAuthorizationErrorCode.PERSISTENCE_UNAVAILABLE,
                message="Advisor authorization storage unavailable",
                status_code=503,
            ) from error

        # 12. Access granted; construct minimal safe context
        return AdvisorAccessContext(
            advisor_user_id=auth_uuid,
            student_user_id=target_student_uuid,
            university_id=assignment.university_id,
            assignment_id=assignment.id,
            authority_source=assignment.authority_source,
            authority_version=assignment.authority_version,
        )
