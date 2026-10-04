"""Fixed, fictional P11 snapshots. Never reads real student outcomes."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.offerings.fake_provider import FAKE_UNIVERSITY_ID

from .models import (
    CareerProfile, CourseSkillMapping, HistoricalRecord, HistoricalSnapshot,
    InternshipCriteria, InternshipCriterion, Skill, SkillTaxonomy, WorkloadFact,
)

FAKE_PLAN_ID = "f1000000-0000-0000-0000-000000000023"
SOURCE_AT = date(2026, 9, 1)


class FakeP11Provider:
    @staticmethod
    def _matches(university_id: str, study_plan_id: str) -> bool:
        return university_id == FAKE_UNIVERSITY_ID and study_plan_id == FAKE_PLAN_ID

    async def load_snapshot(self, university_id: str, study_plan_id: str) -> HistoricalSnapshot | None:
        if not self._matches(university_id, study_plan_id):
            return None
        records = tuple(HistoricalRecord(
            f"anonymous-{index:02d}", "SYN-2025-FALL",
            "SYN-2025-FALL" if index < 6 else "SYN-2026-FALL", 2,
            ("CS101", "MATH101") if index % 3 else ("CS101",),
            ("MATH101",) if index % 4 == 0 else (),
            (0.75 if index % 3 else 0.5), 12 if index % 2 else 9,
            index % 4 == 0, "FAILED" if index % 4 == 0 else "PASSED",
        ) for index in range(12))
        return HistoricalSnapshot(university_id, study_plan_id, "p11-synthetic-history-v1",
                                  datetime(2026, 9, 1, tzinfo=timezone.utc),
                                  "FICTIONAL_SANDBOX_OUTCOMES", True, records)

    async def load_facts(self, university_id: str, study_plan_id: str) -> tuple[WorkloadFact, ...] | None:
        if not self._matches(university_id, study_plan_id):
            return None
        return (WorkloadFact("CS101", 3, 5, 8, 3, True),
                WorkloadFact("MATH101", 3, 4, 7, 2, False),
                WorkloadFact("PHYS101", 3, None, None, None, True))

    async def load_taxonomy(self, university_id: str, study_plan_id: str) -> SkillTaxonomy | None:
        if not self._matches(university_id, study_plan_id):
            return None
        skills = (
            Skill("SYN-CODE", "البرمجة", "Programming", "technical", "Fictional programming exposure", "SYNTHETIC_CURATED"),
            Skill("SYN-QUANT", "الاستدلال الكمي", "Quantitative reasoning", "reasoning", "Fictional quantitative exposure", "SYNTHETIC_CURATED"),
            Skill("SYN-COMMS", "التواصل", "Communication", "transferable", "Fictional communication exposure", "SYNTHETIC_CURATED"),
        )
        mappings = (
            CourseSkillMapping("CS101", "SYN-CODE", "COURSE_COMPLETION", "INTRODUCTORY", "SYNTHETIC_MAPPING", "p11-taxonomy-v1"),
            CourseSkillMapping("MATH101", "SYN-QUANT", "COURSE_COMPLETION", "INTRODUCTORY", "SYNTHETIC_MAPPING", "p11-taxonomy-v1"),
            CourseSkillMapping("HIST101", "SYN-COMMS", "COURSE_COMPLETION", "INTRODUCTORY", "SYNTHETIC_MAPPING", "p11-taxonomy-v1"),
        )
        return SkillTaxonomy(university_id, study_plan_id, "p11-taxonomy-v1", SOURCE_AT, True, skills, mappings)

    async def load_profiles(self, university_id: str, study_plan_id: str) -> tuple[CareerProfile, ...] | None:
        if not self._matches(university_id, study_plan_id):
            return None
        return (CareerProfile("SYN-SOFTWARE", "مطوّر برمجيات تجريبي", "Fictional software developer",
                              ("SYN-CODE", "SYN-QUANT"), "p11-taxonomy-v1", "p11-career-v1",
                              SOURCE_AT, "FICTIONAL_CAREER_PROFILE", True),)

    async def load_criteria(self, university_id: str, study_plan_id: str) -> tuple[InternshipCriteria, ...] | None:
        if not self._matches(university_id, study_plan_id):
            return None
        return (InternshipCriteria("SYN-PARTNER", "تدريب تجريبي", "Fictional internship",
                                   "p11-taxonomy-v1", "p11-criteria-v1", date(2027, 9, 1),
                                   "FICTIONAL_PARTNER_CRITERIA", True,
                                   (InternshipCriterion("SYN-C1", "SYN-CODE", "دليل برمجة", "Programming evidence"),
                                    InternshipCriterion("SYN-C2", "SYN-QUANT", "دليل كمي", "Quantitative evidence"))),)
