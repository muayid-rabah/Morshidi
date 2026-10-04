"""Read-only provider protocols and adapters for institutional offering and capacity facts."""

from __future__ import annotations

from typing import Protocol

from app.institutional_intelligence.models import CapacityFact, OfferingFact


class OfferingFactProvider(Protocol):
    """Narrow read-only contract for external institutional offering facts."""

    async def get_offering_fact(
        self,
        *,
        university_id: str,
        period_key: str,
        course_code: str,
        study_plan_id: str | None = None,
    ) -> OfferingFact | None:
        """Loads verified or synthetic offering fact for a course in a target period."""
        ...


class CapacityFactProvider(Protocol):
    """Narrow read-only contract for external institutional capacity facts."""

    async def get_capacity_fact(
        self,
        *,
        university_id: str,
        period_key: str,
        course_code: str,
        study_plan_id: str | None = None,
    ) -> CapacityFact | None:
        """Loads verified or synthetic capacity fact for a course in a target period."""
        ...


class NullOfferingFactProvider:
    """Default runtime provider returning None when live SIS offering integration is absent."""

    async def get_offering_fact(
        self,
        *,
        university_id: str,
        period_key: str,
        course_code: str,
        study_plan_id: str | None = None,
    ) -> OfferingFact | None:
        return None


class NullCapacityFactProvider:
    """Default runtime provider returning None when live SIS capacity integration is absent."""

    async def get_capacity_fact(
        self,
        *,
        university_id: str,
        period_key: str,
        course_code: str,
        study_plan_id: str | None = None,
    ) -> CapacityFact | None:
        return None


class InMemoryOfferingFactProvider:
    """Configurable in-memory provider for testing, sandbox, and simulation contexts."""

    def __init__(self, facts: tuple[OfferingFact, ...] = ()) -> None:
        self._facts = list(facts)

    def add_fact(self, fact: OfferingFact) -> None:
        self._facts.append(fact)

    async def get_offering_fact(
        self,
        *,
        university_id: str,
        period_key: str,
        course_code: str,
        study_plan_id: str | None = None,
    ) -> OfferingFact | None:
        for f in self._facts:
            if (
                f.university_id == university_id
                and f.period_key == period_key
                and f.course_code == course_code
            ):
                return f
        return None


class InMemoryCapacityFactProvider:
    """Configurable in-memory provider for testing, sandbox, and simulation contexts."""

    def __init__(self, facts: tuple[CapacityFact, ...] = ()) -> None:
        self._facts = list(facts)

    def add_fact(self, fact: CapacityFact) -> None:
        self._facts.append(fact)

    async def get_capacity_fact(
        self,
        *,
        university_id: str,
        period_key: str,
        course_code: str,
        study_plan_id: str | None = None,
    ) -> CapacityFact | None:
        for f in self._facts:
            if (
                f.university_id == university_id
                and f.period_key == period_key
                and f.course_code == course_code
            ):
                if f.study_plan_id is not None and study_plan_id is not None:
                    if f.study_plan_id != study_plan_id:
                        continue
                return f
        return None

