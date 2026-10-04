"""Provider-neutral exact-key lookup for modeled curriculum versions."""

from __future__ import annotations

from typing import Mapping, Protocol

from .ingestion import IngestionState, LocalPublication
from .models import EquivalencyRule, PlanIdentity, PlanVersion

PlanKey = tuple[str, str, str, str, str]


class PlanVersionProvider(Protocol):
    async def load_version(self, key: PlanKey) -> PlanVersion | None: ...


class StudentModelingProvider(PlanVersionProvider, Protocol):
    async def source_for(self, institution_id: str, study_plan_id: str) -> PlanVersion | None: ...
    async def allowed_targets(self, source: PlanIdentity) -> tuple[PlanVersion, ...]: ...
    async def rules_for(self, source: PlanIdentity, target: PlanIdentity) -> tuple[EquivalencyRule, ...]: ...


class IsolatedInMemoryPlanProvider:
    """Only explicit test/local plans; no tenant creation or production database state."""

    def __init__(self, plans: tuple[PlanVersion, ...]):
        keys = [plan.identity.key for plan in plans]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate plan/version identity")
        self._plans = dict(zip(keys, plans, strict=True))

    async def load_version(self, key: PlanKey) -> PlanVersion | None:
        plan = self._plans.get(key)
        if plan is not None and plan.identity.key != key:
            raise ValueError("Provider returned cross-scope plan")
        return plan

    async def rules_for(self, source: PlanIdentity, target: PlanIdentity) -> tuple[EquivalencyRule, ...]:
        old = self._plans.get(source.key)
        new = self._plans.get(target.key)
        if old is None or new is None:
            return ()
        source_courses = {c.identity.course_id: c.identity for c in old.courses}
        target_courses = {c.identity.course_id: c.identity for c in new.courses}
        result: list[EquivalencyRule] = []
        for row in new.staged_rules:
            if row.source_plan_key != source.key or row.target_plan_key != target.key:
                continue
            src = source_courses.get(row.source_course_id)
            dst = target_courses.get(row.target_course_id)
            if src is None or dst is None:
                raise ValueError("Staged rule references missing exact source/target course")
            result.append(EquivalencyRule(row.rule_id, src, dst, source.key,
                                          target.key, row.effective_from, row.effective_to,
                                          row.authority, row.version, row.status, row.provenance))
        return tuple(result)


class ApprovedLocalModelingProvider(IsolatedInMemoryPlanProvider):
    """Explicit local allowlist; no production default or client-supplied curriculum."""

    def __init__(self, publications: tuple[LocalPublication, ...],
                 source_bindings: Mapping[tuple[str, str], PlanKey],
                 target_allowlist: Mapping[PlanKey, tuple[PlanKey, ...]]):
        if any(p.state is not IngestionState.PUBLISHED or not p.plan.synthetic for p in publications):
            raise ValueError("Only published synthetic local artifacts may be modeled")
        super().__init__(tuple(p.plan for p in publications))
        self._bindings = dict(source_bindings)
        self._allowed = {key: tuple(values) for key, values in target_allowlist.items()}
        for (institution, _), key in self._bindings.items():
            plan = self._plans.get(key)
            if plan is None or plan.identity.institution_id != institution:
                raise ValueError("Invalid owner plan binding")
        for source_key, target_keys in self._allowed.items():
            source = self._plans.get(source_key)
            if source is None:
                raise ValueError("Unknown source allowlist plan")
            for target_key in target_keys:
                target = self._plans.get(target_key)
                if target is None or target.identity.institution_id != source.identity.institution_id or target_key == source_key:
                    raise ValueError("Invalid modeled target scope")

    async def source_for(self, institution_id: str, study_plan_id: str) -> PlanVersion | None:
        key = self._bindings.get((institution_id, study_plan_id))
        return self._plans.get(key) if key is not None else None

    async def allowed_targets(self, source: PlanIdentity) -> tuple[PlanVersion, ...]:
        return tuple(self._plans[key] for key in self._allowed.get(source.key, ()))
