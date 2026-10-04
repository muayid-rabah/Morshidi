"""Strict self-service student profile transport contracts."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, Strict, field_validator, model_validator

from app.rules.models import AttemptOutcome

CourseCode = Annotated[str, Strict(), Field(min_length=1)]
RecordSource = Literal["manual_entry", "transcript_import", "university_integration", "admin_correction"]


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileCreateRequest(_StrictRequest):
    study_plan_id: UUID
    reported_cumulative_gpa: Decimal | None = Field(default=None, ge=0)
    reported_gpa_scale: Decimal | None = Field(default=None, gt=0)
    reported_earned_credit_hours: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_gpa_pair(self):
        if (self.reported_cumulative_gpa is None) != (self.reported_gpa_scale is None):
            raise ValueError("reported GPA and scale must be supplied together")
        return self


class ProfileUpdateRequest(_StrictRequest):
    reported_cumulative_gpa: Decimal | None = Field(default=None, ge=0)
    reported_gpa_scale: Decimal | None = Field(default=None, gt=0)
    reported_earned_credit_hours: Decimal | None = Field(default=None, ge=0)


class AcademicProfileResponse(BaseModel):
    id: UUID
    study_plan_id: UUID
    reported_cumulative_gpa: Decimal | None
    reported_gpa_scale: Decimal | None
    reported_earned_credit_hours: Decimal | None
    created_at: datetime | None
    updated_at: datetime | None


class AttemptCreateRequest(_StrictRequest):
    course_code: CourseCode
    status: AttemptOutcome
    attempt_sequence: int | None = Field(default=None, gt=0)
    term_label: str | None = None
    attempted_on: date | None = None
    raw_grade_text: str | None = None
    record_source: RecordSource = "manual_entry"

    @field_validator("course_code")
    @classmethod
    def nonblank_code(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("course_code must not be blank")
        return value

    @field_validator("term_label", "raw_grade_text")
    @classmethod
    def nonblank_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("optional attempt text must not be blank")
        return value


class AttemptUpdateRequest(_StrictRequest):
    status: AttemptOutcome | None = None
    attempt_sequence: int | None = Field(default=None, gt=0)
    term_label: str | None = None
    attempted_on: date | None = None
    raw_grade_text: str | None = None
    record_source: RecordSource | None = None

    @field_validator("term_label", "raw_grade_text")
    @classmethod
    def nonblank_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("optional attempt text must not be blank")
        return value

    @model_validator(mode="after")
    def reject_null_required_values(self):
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        if "record_source" in self.model_fields_set and self.record_source is None:
            raise ValueError("record_source cannot be null")
        return self


class CourseAttemptResponse(BaseModel):
    id: UUID
    course_code: str
    course_name_ar: str | None = None
    course_name_en: str | None = None
    status: AttemptOutcome
    attempt_sequence: int | None
    term_label: str | None
    attempted_on: date | None
    raw_grade_text: str | None
    record_source: RecordSource
    created_at: datetime
    updated_at: datetime
