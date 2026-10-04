"""WC-046 authorization order, required audit, and retry contracts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from functools import wraps
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.advisor_service.errors import AdvisorAuthorizationError, AdvisorAuthorizationErrorCode
from app.change_impact.service import ChangeImpactService, ImpactServiceCode, ImpactServiceError
from app.decision_trace import (
    ActorClass, DecisionType, IntegrityStatus, MaterialityClass, ReplayStatus,
    SubjectScopeType, verify_integrity_hash,
)
from app.decision_trace_persistence.errors import DecisionTraceErrorCode, DecisionTracePersistenceError
from app.mock_registration_persistence.errors import MockRegistrationPersistenceError, PersistenceFailureCode
from tests.test_change_impact_engine import (
    PLAN, TENANT, _credit, _policy, _pre, _prerequisite_catalog, _progress_catalog,
)


ACTOR = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
STUDENT = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class Memberships:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    async def load_active_memberships_for_user(self, **kwargs):
        self.calls.append(kwargs)
        return (SimpleNamespace(university_id=TENANT),) if self.allowed else ()

    async def load_active_membership(self, **kwargs):
        self.calls.append(kwargs)
        if not self.allowed or kwargs["university_id"] != TENANT:
            raise MockRegistrationPersistenceError(PersistenceFailureCode.RESOURCE_NOT_FOUND,
                                                   "denied")
        return SimpleNamespace(university_id=TENANT)


class Advisor:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    async def authorize_advisor_for_student(self, actor, student):
        self.calls.append((actor, student))
        if not self.allowed:
            raise AdvisorAuthorizationError(AdvisorAuthorizationErrorCode.ADVISOR_ACCESS_DENIED,
                                            "denied")
        return SimpleNamespace(university_id=TENANT)


class Contexts:
    def __init__(self):
        self.calls = []

    async def validate_plan_scope(self, plan, university):
        self.calls.append((plan, university))
        if university != TENANT:
            raise ValueError("wrong tenant")
        return ()

    async def load_owner_context(self, student):
        self.calls.append(student)
        return SimpleNamespace(
            university_id=TENANT, study_plan_id=PLAN,
            eligibility_catalog=_prerequisite_catalog(), progress_catalog=None,
            student_attempts=(), study_plan_version="plan-v1", plan_course_facts=(),
            current_progress=SimpleNamespace(reported_cumulative_gpa=None,
                reported_gpa_scale=None, reported_earned_credit_hours=None),
        )


class Catalog:
    def __init__(self):
        self.calls = []

    async def load_plan_eligibility_catalog(self, plan):
        self.calls.append(plan)
        return _prerequisite_catalog()

    async def load_progress_catalog(self, plan):
        self.calls.append(plan)
        return _progress_catalog()


class Ledger:
    def __init__(self):
        self.entries = {}
        self.append_calls = 0
        self.fail = False

    async def load_exact_internal_entry(self, *, ledger_entry_id, university_id):
        assert university_id == str(TENANT)
        return self.entries.get(ledger_entry_id)

    async def append(self, entry):
        self.append_calls += 1
        if self.fail:
            raise DecisionTracePersistenceError(DecisionTraceErrorCode.PERSISTENCE_UNAVAILABLE,
                                                "failure")
        self.entries[entry.ledger_entry_id] = entry
        return entry.ledger_entry_id


def service(*, allowed=True, advisor_allowed=True):
    members, advisor = Memberships(allowed), Advisor(advisor_allowed)
    contexts, catalog, ledger = Contexts(), Catalog(), Ledger()
    return ChangeImpactService(members, advisor, contexts, catalog, ledger), members, advisor, contexts, catalog, ledger


def run_async(fn):
    @wraps(fn)
    def wrapper():
        return asyncio.run(fn())
    return wrapper


@run_async
async def test_analyst_policy_report_and_required_append_are_tenant_scoped():
    subject, members, _, contexts, catalog, ledger = service()
    report = await subject.evaluate_institutional(str(ACTOR), _policy(), university_id=TENANT)
    assert report.audit_status == "LEDGER_PERSISTED"
    assert not contexts.calls and not catalog.calls
    assert ledger.append_calls == 1
    entry = next(iter(ledger.entries.values()))
    assert entry.decision_type is DecisionType.CHANGE_IMPACT_EVALUATION
    assert entry.materiality_class is MaterialityClass.LEDGER_REQUIRED
    assert entry.actor_class is ActorClass.INSTITUTIONAL_ANALYST
    assert entry.actor_id == str(ACTOR) and entry.university_id == str(TENANT)
    assert entry.subject_scope_type is SubjectScopeType.POLICY_DOCUMENT
    assert entry.student_user_id is None
    assert entry.replay_status is ReplayStatus.NOT_REPLAYABLE
    assert verify_integrity_hash(entry) is IntegrityStatus.VERIFIED
    assert "CHANGE_IMPACT_V1_EPHEMERAL_REPORT" in entry.limitations
    assert members.calls[0]["role"] == "INSTITUTIONAL_ANALYST"


@run_async
async def test_retry_reconciles_exact_existing_trace_without_duplicate_append():
    subject, _, _, _, _, ledger = service()
    first = await subject.evaluate_institutional(str(ACTOR), _policy())
    second = await subject.evaluate_institutional(str(ACTOR), _policy())
    assert first.change_id == second.change_id
    assert ledger.append_calls == 1 and len(ledger.entries) == 1
    entry = next(iter(ledger.entries.values()))
    ledger.entries[entry.ledger_entry_id] = replace(entry, outcome_reference="wrong")
    with pytest.raises(ImpactServiceError) as caught:
        await subject.evaluate_institutional(str(ACTOR), _policy())
    assert caught.value.code is ImpactServiceCode.AUDIT_PERSISTENCE_UNAVAILABLE


@run_async
async def test_audit_failure_fails_closed():
    subject, _, _, _, _, ledger = service()
    ledger.fail = True
    with pytest.raises(ImpactServiceError) as caught:
        await subject.evaluate_institutional(str(ACTOR), _policy())
    assert caught.value.code is ImpactServiceCode.AUDIT_PERSISTENCE_UNAVAILABLE


@run_async
async def test_analyst_denial_precedes_catalog_and_audit():
    subject, _, _, contexts, catalog, ledger = service(allowed=False)
    with pytest.raises(ImpactServiceError) as caught:
        await subject.evaluate_institutional(str(ACTOR), _pre())
    assert caught.value.code is ImpactServiceCode.ACCESS_DENIED
    assert not contexts.calls and not catalog.calls and not ledger.entries


@run_async
async def test_assigned_advisor_only_and_no_student_identity_in_report():
    subject, _, advisor, contexts, _, ledger = service()
    report = await subject.evaluate_advisor(str(ACTOR), STUDENT, _pre())
    assert advisor.calls == [(ACTOR, STUDENT)]
    assert contexts.calls == [STUDENT]
    assert str(STUDENT) not in report.model_dump_json()
    entry = next(iter(ledger.entries.values()))
    assert entry.subject_scope_type is SubjectScopeType.STUDENT_INDIVIDUAL
    assert entry.student_user_id == str(STUDENT)
    assert entry.actor_class is ActorClass.ACADEMIC_ADVISOR


@run_async
async def test_unassigned_advisor_denied_before_student_load():
    subject, _, _, contexts, _, ledger = service(advisor_allowed=False)
    with pytest.raises(ImpactServiceError) as caught:
        await subject.evaluate_advisor(str(ACTOR), STUDENT, _pre())
    assert caught.value.code is ImpactServiceCode.ACCESS_DENIED
    assert not contexts.calls and not ledger.entries


@run_async
async def test_unknown_plan_course_or_group_fails_without_audit():
    subject, _, _, _, _, ledger = service()
    for delta in (_pre(target_course_code="MISSING"), _credit(course_code="MISSING")):
        with pytest.raises(ImpactServiceError) as caught:
            await subject.evaluate_institutional(str(ACTOR), delta, university_id=TENANT)
        assert caught.value.code is ImpactServiceCode.SCOPE_UNAVAILABLE
    assert ledger.append_calls == 0
