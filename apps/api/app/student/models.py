"""Thin persistence aggregate; eligibility facts remain Phase 5 models."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from app.rules.models import AttemptOutcome, StudentCourseAttempt


@dataclass(frozen=True)
class StudentAcademicState:
    profile_id: str
    owner_user_id: str
    study_plan_id: str
    reported_cumulative_gpa: Decimal | None
    reported_gpa_scale: Decimal | None
    reported_earned_credit_hours: Decimal | None
    attempts: tuple[StudentCourseAttempt, ...]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PerformanceProvenance(str, Enum):
    OFFICIAL_VERIFIED = "OFFICIAL_VERIFIED"
    STUDENT_RECORD = "STUDENT_RECORD"
    DERIVED_DETERMINISTIC = "DERIVED_DETERMINISTIC"
    MODEL_OUTPUT = "MODEL_OUTPUT"
    MANUAL_ACADEMIC_REVIEW = "MANUAL_ACADEMIC_REVIEW"
    UNVERIFIED = "UNVERIFIED"


class PerformanceVerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class StudentCourseAttemptRecord:
    attempt_id: str
    profile_id: str
    course_code: str
    outcome: AttemptOutcome
    attempt_sequence: int | None
    term_label: str | None
    attempted_on: date | None
    reported_grade_text: str | None
    record_source: str
    created_at: datetime
    updated_at: datetime
    raw_numeric_grade: Decimal | None = None
    raw_letter_grade: str | None = None
    raw_grade_points: Decimal | None = None
    raw_academic_year: str | None = None
    raw_term: str | None = None
    attempt_credit_hours: Decimal | None = None
    performance_provenance: PerformanceProvenance = PerformanceProvenance.UNVERIFIED
    performance_verification_state: PerformanceVerificationState = PerformanceVerificationState.UNVERIFIED
    performance_source_reference: str | None = None
    course_name_ar: str | None = None
    course_name_en: str | None = None
