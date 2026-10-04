"""Strict request, interpretation and response contracts without student fields."""

from __future__ import annotations

from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryStatus(str, Enum):
    ANSWERED = "ANSWERED"
    ABSTAINED = "ABSTAINED"


class AbstentionReason(str, Enum):
    UNSUPPORTED_QUERY = "UNSUPPORTED_QUERY"
    AMBIGUOUS_METRIC = "AMBIGUOUS_METRIC"
    NO_APPROVED_METRIC = "NO_APPROVED_METRIC"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INVALID_PROVIDER_OUTPUT = "INVALID_PROVIDER_OUTPUT"
    SCOPE_UNAVAILABLE = "SCOPE_UNAVAILABLE"
    METRIC_UNAVAILABLE = "METRIC_UNAVAILABLE"


class InstitutionalAIQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    question: str = Field(min_length=8, max_length=300)
    target_period_id: UUID
    study_plan_id: UUID
    course_code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")
    university_id: UUID | None = None

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 8 or len(normalized) > 300:
            raise ValueError("question length is outside the approved bound")
        return normalized

    @field_validator("course_code")
    @classmethod
    def normalize_course(cls, value: str) -> str:
        return " ".join(value.upper().split())


class ProviderInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    status: Literal["INTERPRETED", "ABSTAINED"]
    metric_id: str | None
    language: Literal["ar", "en"]
    abstention_reason: str | None


class QueryInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metric_id: str
    metric_label: str
    metric_catalog_version: str
    question_language: Literal["ar", "en"]
    target_period_id: UUID
    target_period_key: str
    study_plan_id: UUID
    course_code: str


class QueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["AVAILABLE", "SUPPRESSED", "INSUFFICIENT_DATA", "REVIEW_REQUIRED", "NOT_APPLICABLE"]
    value: int | float | str | None
    unit: str
    quality_flags: tuple[str, ...]
    answer_text: str


class QueryProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    catalog_version: str
    prerequisite_version: str
    demand_source_version: str
    policy_version: str
    computed_at: str | None


class InstitutionalAIQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: QueryStatus
    interpretation: QueryInterpretation | None = None
    result: QueryResult | None = None
    provenance: QueryProvenance | None = None
    query_fingerprint: str | None = None
    limitations: tuple[str, ...] = ()
    abstention_reason: AbstentionReason | None = None
