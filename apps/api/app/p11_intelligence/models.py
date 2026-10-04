"""Provider-neutral, immutable P11 evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

Outcome = Literal["PASSED", "FAILED", "WITHDRAWN", "IN_PROGRESS"]


@dataclass(frozen=True)
class HistoricalRecord:
    anonymous_id: str
    entry_period: str
    period: str
    academic_level: int
    completed_courses: tuple[str, ...]
    repeated_courses: tuple[str, ...]
    completion_ratio: float | None
    credit_load: int | None
    observed_structural_signal: bool | None
    outcome: Outcome | None


@dataclass(frozen=True)
class HistoricalSnapshot:
    university_id: str
    study_plan_id: str
    source_version: str
    recorded_at: datetime
    provenance: str
    synthetic: bool
    records: tuple[HistoricalRecord, ...]


@dataclass(frozen=True)
class CohortDefinition:
    university_id: str
    study_plan_id: str
    entry_period: str
    period: str
    minimum_level: int = 1
    maximum_level: int = 8


@dataclass(frozen=True)
class WorkloadFact:
    course_code: str
    credits: int
    observed_low_hours: int | None
    observed_high_hours: int | None
    assessment_count: int | None
    has_lab_or_project: bool


@dataclass(frozen=True)
class Skill:
    skill_id: str
    name_ar: str
    name_en: str
    category: str
    description: str
    provenance: str


@dataclass(frozen=True)
class CourseSkillMapping:
    course_code: str
    skill_id: str
    evidence_type: str
    exposure: str
    provenance: str
    version: str


@dataclass(frozen=True)
class SkillTaxonomy:
    university_id: str
    study_plan_id: str
    version: str
    source_at: date
    synthetic: bool
    skills: tuple[Skill, ...]
    mappings: tuple[CourseSkillMapping, ...]


@dataclass(frozen=True)
class CareerProfile:
    career_id: str
    title_ar: str
    title_en: str
    required_skill_ids: tuple[str, ...]
    taxonomy_version: str
    source_version: str
    source_at: date
    provenance: str
    synthetic: bool


@dataclass(frozen=True)
class InternshipCriterion:
    criterion_id: str
    skill_id: str
    requirement_ar: str
    requirement_en: str


@dataclass(frozen=True)
class InternshipCriteria:
    partner_id: str
    title_ar: str
    title_en: str
    taxonomy_version: str
    source_version: str
    expires_at: date
    provenance: str
    synthetic: bool
    criteria: tuple[InternshipCriterion, ...]
