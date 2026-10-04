"""Allowlisted student-only Decision History response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.decision_trace.registries import DecisionStatus, DecisionType, ProvenanceClass, ReplayStatus


class StudentDecisionHistoryItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ledger_entry_id: str
    decision_type: DecisionType
    decision_status: DecisionStatus
    created_at: datetime
    source_engine: str
    source_engine_version: str
    policy_version: str
    replay_status: ReplayStatus
    supersedes_entry_id: str | None
    is_superseded: bool
    limitations: tuple[str, ...]
    integrity_status: Literal["VERIFIED"]


class StudentDecisionEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    identifier: str
    version: str
    locator: str | None
    uri: str | None


class StudentDecisionHistoryDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ledger_entry_id: str
    decision_type: DecisionType
    decision_status: DecisionStatus
    created_at: datetime
    source_engine: str
    source_engine_version: str
    policy_version: str
    source_versions: tuple[str, ...]
    replay_status: ReplayStatus
    provenance_class: ProvenanceClass
    limitations: tuple[str, ...]
    integrity_status: Literal["VERIFIED"]
    supersedes_entry_id: str | None
    is_superseded: bool
    evidence: tuple[StudentDecisionEvidenceResponse, ...]
