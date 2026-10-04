"""Allowlisted response DTOs and models for Institutional Intelligence API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SignalResponseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    status: str
    value: int | float | str | None
    unit: str
    quality_flags: list[str] = Field(default_factory=list)
    trace_id: str | None = None


class AlertResponseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: str
    emitted: bool
    category: str
    message: str
    side_effects: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class DecisionTraceResponseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str | None
    signal_id: str
    rule_id: str
    result_status: str
    result_value: int | float | str | None = None
    limitations: list[str] = Field(default_factory=list)


class ProvenanceResponseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    university_id: str
    target_period_key: str
    scope_type: str
    scope_id: str
    catalog_version: str
    prerequisite_version: str
    demand_source_version: str
    policy_version: str
    computed_at: str | None = None


class InstitutionalIntelligenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["institutional_intelligence"] = "institutional_intelligence"
    contract_version: str
    university_id: UUID
    target_period_id: UUID
    target_period_key: str
    study_plan_id: UUID | None
    course_code: str
    provenance: ProvenanceResponseDTO
    signals: dict[str, SignalResponseDTO]
    alerts: list[AlertResponseDTO]
    traces: list[DecisionTraceResponseDTO]
    quality_flags: list[str]
    coverage_notes: list[str]
    generated_at: datetime
