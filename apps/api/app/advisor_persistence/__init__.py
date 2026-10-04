"""Phase P7.4 Advisor Persistence Package."""

from app.advisor_persistence.errors import (
    AdvisorPersistenceError,
    AdvisorPersistenceIntegrityError,
)
from app.advisor_persistence.models import (
    AdvisorAccessContext,
    AdvisorStudentAssignmentRecord,
)
from app.advisor_persistence.repository import (
    SupabaseAdvisorAssignmentRepository,
)

__all__ = [
    "AdvisorAccessContext",
    "AdvisorPersistenceError",
    "AdvisorPersistenceIntegrityError",
    "AdvisorStudentAssignmentRecord",
    "SupabaseAdvisorAssignmentRepository",
]
