"""Immutable, reproducible modeled report from one owner-scoped roadmap snapshot."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json

from app.roadmap.engine import AcademicRoadmap, RoadmapState

REPORT_SCHEMA_VERSION = "P9_MODELED_REPORT_V1"
REPORT_MARKER = "MODELED_UNOFFICIAL"


@dataclass(frozen=True)
class ReportCourse:
    course_code: str
    name_ar: str
    name_en: str | None
    state: RoadmapState
    credit_hours: Decimal
    planned_semester: int | None
    planned_order: int | None
    critical_path: bool


@dataclass(frozen=True)
class ModeledAcademicReport:
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
    courses: tuple[ReportCourse, ...]
    limitations: tuple[str, ...]
    content_fingerprint: str


def build_report_snapshot(roadmap: AcademicRoadmap) -> ModeledAcademicReport:
    """No new reads: web and print serialize the same frozen academic content."""
    if not roadmap.snapshot_fingerprint:
        raise ValueError("Report requires an authoritative roadmap fingerprint")
    courses = tuple(ReportCourse(
        node.course_code, node.name_ar, node.name_en, node.state,
        node.credit_hours, node.planned_semester, node.planned_order, node.critical_path,
    ) for node in roadmap.courses)
    content = {
        "schema": REPORT_SCHEMA_VERSION, "marker": REPORT_MARKER,
        "study_plan_id": roadmap.study_plan_id, "plan_number": roadmap.plan_number,
        "effective_year": roadmap.effective_year, "plan_updated_at": roadmap.plan_updated_at,
        "source_type": roadmap.source_type, "source_retrieved_at": roadmap.source_retrieved_at,
        "source_content_hash": roadmap.source_content_hash, "source_snapshot_ref": roadmap.source_snapshot_ref,
        "source_status": roadmap.source_status,
        "snapshot_contract_version": roadmap.snapshot_contract_version,
        "snapshot_fingerprint": roadmap.snapshot_fingerprint,
        "critical_path_policy_version": roadmap.critical_path_policy_version,
        "modeled_plan_policy_version": roadmap.modeled_plan_policy_version,
        "modeling_status": roadmap.modeling_status,
        "credits": [str(roadmap.plan_total_required_credits), str(roadmap.completed_plan_credits),
                    str(roadmap.in_progress_plan_credits), str(roadmap.remaining_plan_credits)],
        "courses": [[c.course_code, c.name_ar, c.name_en, c.state.value, str(c.credit_hours),
                     c.planned_semester, c.planned_order, c.critical_path] for c in courses],
        "limitations": list(roadmap.limitations),
    }
    fingerprint = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False,
                                          separators=(",", ":")).encode("utf-8")).hexdigest()
    return ModeledAcademicReport(
        REPORT_SCHEMA_VERSION, REPORT_MARKER, roadmap.study_plan_id, roadmap.plan_number,
        roadmap.effective_year, roadmap.plan_updated_at, roadmap.source_type,
        roadmap.source_retrieved_at, roadmap.source_content_hash, roadmap.source_snapshot_ref,
        roadmap.source_status, roadmap.snapshot_contract_version, roadmap.snapshot_fingerprint,
        roadmap.critical_path_policy_version, roadmap.modeled_plan_policy_version,
        roadmap.modeling_status, roadmap.generated_at, roadmap.plan_total_required_credits,
        roadmap.completed_plan_credits, roadmap.in_progress_plan_credits,
        roadmap.remaining_plan_credits, courses, roadmap.limitations, fingerprint,
    )
