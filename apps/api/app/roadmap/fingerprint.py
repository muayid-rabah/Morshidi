"""Canonical, privacy-minimized content identity for one academic input snapshot.

This follows the Digital Twin's sorted-JSON SHA-256 pattern, but includes the
roadmap-specific course names and source metadata. It does not expose raw inputs.
"""

from __future__ import annotations

import hashlib
import json

from app.advisor.models import ResolvedCourseReference
from app.catalog.roadmap_metadata import RoadmapPlanMetadata
from app.progress.models import AcademicProgressCatalog
from app.rules.models import CanTakeCatalog, StudentCourseAttempt

ROADMAP_SNAPSHOT_VERSION = "P13_ROADMAP_INPUT_V2"


def academic_input_fingerprint(
    progress: AcademicProgressCatalog,
    eligibility: CanTakeCatalog,
    names: tuple[ResolvedCourseReference, ...],
    attempts: tuple[StudentCourseAttempt, ...],
    metadata: RoadmapPlanMetadata | None,
    *,
    institution_id: str,
) -> str:
    """Same normalized plan/rules/names/attempts -> same digest, independent of read order."""
    if not institution_id or not institution_id.strip():
        raise ValueError("Roadmap fingerprint requires stable institution identity")
    payload = {
        "schema": ROADMAP_SNAPSHOT_VERSION,
        "institution_id": institution_id,
        "study_plan_id": progress.study_plan.study_plan_id,
        "plan_total_credits": str(progress.study_plan.total_credit_hours),
        "plan_metadata": None if metadata is None else {
            "plan_number": metadata.plan_number,
            "effective_year": metadata.effective_year,
            "updated_at": metadata.updated_at,
            "source_type": metadata.source_type,
            "source_retrieved_at": metadata.source_retrieved_at,
            "source_content_hash": metadata.source_content_hash,
            "source_snapshot_ref": metadata.source_snapshot_ref,
            "source_status": metadata.source_status,
        },
        "groups": sorted([
            group.group_id, group.group_code, group.name_ar, group.name_en,
            group.scope, group.requirement_type.value, str(group.required_credit_hours),
            group.display_order,
        ] for group in progress.requirement_groups),
        "courses": sorted([
            course.plan_course_id, course.requirement_group_id, course.course_code,
            course.catalog_status.value, str(course.credit_hours), course.display_order,
        ] for course in progress.plan_courses),
        "rules": sorted([
            rule.course_code, rule.prerequisite_logic_status.value,
            sorted([
                group.group_number, group.dependency_type.value,
                sorted(group.option_course_codes),
            ] for group in rule.dependency_groups),
        ] for rule in eligibility.plan_courses),
        "identities": sorted([course.course_code, course.catalog_status.value]
                             for course in eligibility.courses),
        "names": sorted([course.course_code, course.canonical_arabic_name,
                         course.canonical_english_name] for course in names),
        "attempts": sorted([attempt.course_code, attempt.outcome.value] for attempt in attempts),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
