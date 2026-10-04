"""P6.4 persistence-only boundary for Mock Registration records."""

from .models import (
    InstitutionalMembershipRecord,
    PersistRevisionCommand,
    PersistRevisionResult,
    PersistenceResultKind,
    PersistedIntentCourse,
    PersistedIntentRevision,
    PersistedTargetPeriod,
)
from .repository import SupabaseMockRegistrationRepository

__all__ = [
    "InstitutionalMembershipRecord",
    "PersistRevisionCommand",
    "PersistRevisionResult",
    "PersistenceResultKind",
    "PersistedIntentCourse",
    "PersistedIntentRevision",
    "PersistedTargetPeriod",
    "SupabaseMockRegistrationRepository",
]
