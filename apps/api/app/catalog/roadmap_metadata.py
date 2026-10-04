"""Presentation-only plan provenance, separate from hash-pinned progress contracts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RoadmapPlanMetadata:
    study_plan_id: str
    plan_number: str
    effective_year: int | None
    updated_at: str
    source_type: str | None = None
    source_retrieved_at: str | None = None
    source_content_hash: str | None = None
    source_snapshot_ref: str | None = None
    source_status: str | None = None
