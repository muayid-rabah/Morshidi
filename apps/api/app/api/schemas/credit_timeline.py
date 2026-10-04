"""Request/response contracts for owner-derived credit-only projections."""

from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.degree_path.credit_timeline import AcademicTerm, ComparisonMode


class CreditTimelineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    regular_load: Decimal = Field(ge=3, le=30)
    summer_enabled: bool = False
    summer_load: Decimal = Field(default=Decimal(0), ge=0, le=9)
    start_year: int = Field(ge=2000, le=2200)
    start_term: AcademicTerm


class CreditTermResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    academic_year: int
    term: AcademicTerm
    planned_credits: Decimal
    remaining_after: Decimal


class CreditTimelineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    policy_version: str
    total_required_credits: Decimal
    earned_credits: Decimal
    initial_remaining_credits: Decimal
    regular_load: Decimal
    summer_enabled: bool
    summer_load: Decimal
    terms: list[CreditTermResponse]
    regular_semester_count: int
    summer_count: int
    completion_year: int | None
    completion_term: AcademicTerm | None
    assumptions: list[str]
    warnings: list[str]


class CreditComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_year: int = Field(ge=2000, le=2200)
    start_term: AcademicTerm
    preferred_regular_load: Decimal | None = Field(default=None, ge=3, le=30)
    preferred_summer_enabled: bool | None = None
    preferred_summer_load: Decimal | None = Field(default=None, ge=3, le=9)
    graduation_pace: ComparisonMode | None = None


class CreditComparisonScenarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    scenario_id: str
    mode: ComparisonMode
    timeline: CreditTimelineResponse
    total_modeled_terms: int
    workload_indicator: str
    preference_match: bool
    provenance: str
    difficulty_evidence: str
    confidence: str
    current_workload_risk: int | None


class CreditComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    policy_version: str
    scenarios: list[CreditComparisonScenarioResponse]
    evaluated_scenarios: int
    limitations: list[str]
