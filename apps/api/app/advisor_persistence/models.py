"""Phase P7.4 Advisor Authorization and Assignment Persistence Models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class AdvisorStudentAssignmentRecord:
    """Immutable representation of a persisted advisor-student assignment relation."""

    id: UUID
    advisor_user_id: UUID
    student_user_id: UUID
    university_id: UUID
    is_active: bool
    authority_source: str
    authority_version: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.advisor_user_id == self.student_user_id:
            raise ValueError("advisor_user_id and student_user_id must be distinct")
        if not self.authority_source.strip():
            raise ValueError("authority_source must not be empty")
        if not self.authority_version.strip():
            raise ValueError("authority_version must not be empty")


@dataclass(frozen=True)
class AdvisorAccessContext:
    """Minimal typed authorization context granting advisor access to a specific student."""

    advisor_user_id: UUID
    student_user_id: UUID
    university_id: UUID
    assignment_id: UUID
    authority_source: str
    authority_version: str

    def __post_init__(self) -> None:
        if self.advisor_user_id == self.student_user_id:
            raise ValueError("advisor_user_id and student_user_id must be distinct")
        if not self.authority_source.strip():
            raise ValueError("authority_source must not be empty")
        if not self.authority_version.strip():
            raise ValueError("authority_version must not be empty")
