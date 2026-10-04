"""Typed application-service contracts, separate from HTTP and P6.2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from app.mock_registration.models import (
    AcademicProgress,
    AcademicProgressCatalog,
    CanTakeCatalog,
    DemandAggregationResult,
    IntentLifecycle,
    PlanCourseFact,
    TargetPeriodClass,
    ValidatedIntent,
    ValidationStatus,
)
from app.mock_registration.registries import ReasonCode
from app.rules.models import StudentCourseAttempt


class CurrentValidity(str, Enum):
    CURRENT_VALID = "CURRENT_VALID"
    CURRENT_INVALID = "CURRENT_INVALID"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    STALE_REQUIRES_REVALIDATION = "STALE_REQUIRES_REVALIDATION"
    EXPIRED = "EXPIRED"


class RevalidationStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class AcademicContextSnapshot:
    owner_user_id: UUID
    university_id: UUID
    major_id: UUID
    study_plan_id: UUID
    study_plan_version: str
    eligibility_catalog: CanTakeCatalog
    progress_catalog: AcademicProgressCatalog
    current_progress: AcademicProgress
    student_attempts: tuple[StudentCourseAttempt, ...]
    course_ids: tuple[tuple[str, UUID], ...]
    plan_course_facts: tuple[PlanCourseFact, ...]
    source_versions: tuple[str, ...]
    progress_state_version: str
    progress_state_reference: str | None
    snapshot_token: str

    def course_id(self, course_code: str) -> UUID | None:
        return dict(self.course_ids).get(course_code)


@dataclass(frozen=True)
class RevalidationResult:
    current_validity: CurrentValidity
    status: RevalidationStatus
    validated_intent: ValidatedIntent | None
    reason_codes: tuple[ReasonCode, ...]


@dataclass(frozen=True)
class StudentIntentResult:
    intent_id: UUID
    target_period_id: UUID
    target_period_class: TargetPeriodClass
    revision: int
    lifecycle_status: IntentLifecycle
    course_codes: tuple[str, ...]
    submission_validation_status: ValidationStatus
    submission_reason_codes: tuple[ReasonCode, ...]
    current_validity: CurrentValidity | None
    revalidation_status: RevalidationStatus
    current_reason_codes: tuple[ReasonCode, ...]
    idempotent_replay: bool
    created_at: datetime
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class InstitutionalDemandResult:
    demand: DemandAggregationResult
    revalidation_status: RevalidationStatus
    stale_records_excluded: bool
    generated_at: datetime
    university_id: UUID
    target_period_id: UUID
    study_plan_id: UUID | None
    course_code: str | None

