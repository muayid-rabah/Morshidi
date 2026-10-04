"""Authenticated modeled roadmap response; no owner selector is accepted."""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel

from app.roadmap.engine import RoadmapState
from app.rules.models import DependencyType


class RoadmapEdgeResponse(BaseModel):
    prerequisite_code: str
    target_code: str
    dependency_type: DependencyType
    group_number: int
    option_count: int


class RoadmapCourseResponse(BaseModel):
    course_code: str
    name_ar: str
    name_en: str | None
    credit_hours: Decimal
    requirement_group_code: str
    state: RoadmapState
    reasons: tuple[str, ...]
    missing_prerequisite_groups: tuple[tuple[str, ...], ...]
    prerequisite_logic_status: str
    structural_criticality: bool
    structural_impact_count: int
    planned_semester: int | None
    planned_order: int | None
    critical_path: bool
    critical_path_reason: str | None
    critical_path_length: int
    critical_path_downstream_codes: tuple[str, ...]
    critical_path_evidence_chain: tuple[str, ...]


class AcademicRoadmapResponse(BaseModel):
    study_plan_id: str
    plan_number: str | None
    effective_year: int | None
    plan_updated_at: str | None
    generated_at: datetime
    plan_total_required_credits: Decimal
    completed_plan_credits: Decimal
    in_progress_plan_credits: Decimal
    remaining_plan_credits: Decimal
    courses: tuple[RoadmapCourseResponse, ...]
    edges: tuple[RoadmapEdgeResponse, ...]
    limitations: tuple[str, ...]
    snapshot_fingerprint: str | None
    snapshot_contract_version: str
    critical_path_policy_version: str
    modeling_status: str
    modeled_plan_policy_version: str | None
    source_type: str | None
    source_retrieved_at: str | None
    source_content_hash: str | None
    source_snapshot_ref: str | None
    source_status: str | None
