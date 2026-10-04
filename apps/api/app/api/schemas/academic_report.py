"""Uncacheable, owner-scoped modeled report contract."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.roadmap.engine import RoadmapState


class ReportCourseResponse(BaseModel):
    course_code: str
    name_ar: str
    name_en: str | None
    state: RoadmapState
    credit_hours: Decimal
    planned_semester: int | None
    planned_order: int | None
    critical_path: bool


class ModeledAcademicReportResponse(BaseModel):
    report_schema_version: str
    modeled_state_marker: str
    study_plan_id: str
    plan_number: str | None
    effective_year: int | None
    plan_updated_at: str | None
    source_type: str | None
    source_retrieved_at: str | None
    source_content_hash: str | None
    source_snapshot_ref: str | None
    source_status: str | None
    snapshot_contract_version: str
    snapshot_fingerprint: str
    critical_path_policy_version: str
    modeled_plan_policy_version: str | None
    modeling_status: str
    generated_at: datetime
    plan_total_required_credits: Decimal
    completed_plan_credits: Decimal
    in_progress_plan_credits: Decimal
    remaining_plan_credits: Decimal
    courses: tuple[ReportCourseResponse, ...]
    limitations: tuple[str, ...]
    content_fingerprint: str
