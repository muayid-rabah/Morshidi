"""Batch provider interfaces. Production defaults disclose no synthetic facts."""

from __future__ import annotations

from typing import Protocol

from .models import CareerProfile, HistoricalRecord, HistoricalSnapshot, InternshipCriteria, SkillTaxonomy, WorkloadFact


class HistoricalOutcomeProvider(Protocol):
    async def load_snapshot(self, university_id: str, study_plan_id: str) -> HistoricalSnapshot | None: ...


class WorkloadProvider(Protocol):
    async def load_facts(self, university_id: str, study_plan_id: str) -> tuple[WorkloadFact, ...] | None: ...


class SkillTaxonomyProvider(Protocol):
    async def load_taxonomy(self, university_id: str, study_plan_id: str) -> SkillTaxonomy | None: ...


class CareerProfileProvider(Protocol):
    async def load_profiles(self, university_id: str, study_plan_id: str) -> tuple[CareerProfile, ...] | None: ...


class InternshipCriteriaProvider(Protocol):
    async def load_criteria(self, university_id: str, study_plan_id: str) -> tuple[InternshipCriteria, ...] | None: ...


class RiskModel(Protocol):
    def infer(self, record: HistoricalRecord | None, *, generated_at: str) -> dict: ...


class UnavailableP11Provider:
    async def load_snapshot(self, university_id: str, study_plan_id: str) -> None: return None
    async def load_facts(self, university_id: str, study_plan_id: str) -> None: return None
    async def load_taxonomy(self, university_id: str, study_plan_id: str) -> None: return None
    async def load_profiles(self, university_id: str, study_plan_id: str) -> None: return None
    async def load_criteria(self, university_id: str, study_plan_id: str) -> None: return None
