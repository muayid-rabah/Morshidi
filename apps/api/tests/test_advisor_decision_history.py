"""Advisor Decision History authorization, redaction, and API regressions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.advisor_service import AdvisorAuthorizationService
from app.api.routes.decision_history import get_decision_trace_service
from app.core.auth import CurrentUser, get_current_user
from app.decision_trace import RedactionProfile
from app.decision_trace_persistence import DecisionTraceService
from app.main import app
from app.mock_registration_persistence.models import InstitutionalMembershipRecord
from tests.test_advisor_authorization import InMemoryAdvisorAssignmentRepository
from tests.test_decision_history import Repository, Scope, entry


STUDENT = uuid4()
OTHER = uuid4()
ADVISOR = uuid4()
UNASSIGNED = uuid4()
ANALYST = uuid4()
UNIVERSITY = uuid4()


class AdvisorRepository(Repository):
    async def list_student_entries(self, *, redaction_profiles=("STUDENT_SAFE",), **kwargs):
        rows = await super().list_student_entries(**kwargs)
        if redaction_profiles == ("STUDENT_SAFE",):
            return rows
        result = [item for item in self.entries if item.student_user_id == kwargs["student_user_id"]
                  and item.university_id == kwargs["university_id"]
                  and item.redaction_profile.value in redaction_profiles]
        result.sort(key=lambda item: (item.created_at, item.ledger_entry_id), reverse=True)
        if kwargs.get("before_created_at") is not None:
            result = [item for item in result if (item.created_at, item.ledger_entry_id)
                      < (kwargs["before_created_at"], kwargs["before_entry_id"])]
        return tuple(result[:kwargs["limit"]])

    async def load_student_entry(self, *, redaction_profiles=None, **kwargs):
        if redaction_profiles is None:
            return await super().load_student_entry(**kwargs)
        return next((item for item in self.entries if item.ledger_entry_id == kwargs["ledger_entry_id"]
                     and item.student_user_id == kwargs["student_user_id"]
                     and item.university_id == kwargs["university_id"]
                     and item.redaction_profile.value in redaction_profiles), None)

    async def load_student_successor(self, *, redaction_profiles=("STUDENT_SAFE",), **kwargs):
        return next((item for item in self.entries if item.supersedes_entry_id == kwargs["ledger_entry_id"]
                     and item.student_user_id == kwargs["student_user_id"]
                     and item.university_id == kwargs["university_id"]
                     and item.redaction_profile.value in redaction_profiles), None)


def _membership(user, university, role="ACADEMIC_ADVISOR"):
    now = datetime.now(timezone.utc)
    return InstitutionalMembershipRecord(
        membership_id=uuid4(), subject_user_id=user, university_id=university,
        provider_namespace="test", role=role, active=True,
        authority_source="test", authority_source_version="v1", created_at=now, updated_at=now,
    )


async def _setup(rows):
    assignments = InMemoryAdvisorAssignmentRepository()
    assignments.student_universities[STUDENT] = UNIVERSITY
    assignments.memberships.extend((
        _membership(ADVISOR, UNIVERSITY), _membership(UNASSIGNED, UNIVERSITY),
        _membership(ANALYST, UNIVERSITY, "INSTITUTIONAL_ANALYST"),
    ))
    await assignments.create_assignment(
        advisor_user_id=ADVISOR, student_user_id=STUDENT, university_id=UNIVERSITY,
        authority_source="test", authority_version="v1",
    )
    repository = AdvisorRepository(rows)
    service = DecisionTraceService(repository, Scope(UNIVERSITY), AdvisorAuthorizationService(assignments))
    return service, assignments, repository


@pytest.mark.anyio
async def test_assigned_advisor_sees_both_safe_profiles_and_student_remains_restricted():
    public = entry(student=STUDENT, university=UNIVERSITY)
    advisor = entry(student=STUDENT, university=UNIVERSITY, profile=RedactionProfile.ADVISOR_SAFE)
    full = entry(student=STUDENT, university=UNIVERSITY, profile=RedactionProfile.FULL_AUDIT)
    service, _, _ = await _setup((public, advisor, full, entry(student=OTHER, university=UNIVERSITY)))
    page = await service.list_advisor_history(CurrentUser(str(ADVISOR)), STUDENT)
    assert {item.ledger_entry_id for item in page} == {public.ledger_entry_id, advisor.ledger_entry_id}
    assert all(item.integrity_status == "VERIFIED" for item in page)
    detail = await service.get_advisor_history_detail(CurrentUser(str(ADVISOR)), STUDENT, advisor.ledger_entry_id)
    assert detail.integrity_status == "VERIFIED" and len(detail.evidence) == 2
    assert detail.evidence[1].uri is None
    assert not hasattr(detail, "integrity_hash") and not hasattr(detail, "actor_id")
    from app.decision_trace_persistence import DecisionTracePersistenceError
    with pytest.raises(DecisionTracePersistenceError):
        await service.get_student_history_detail(CurrentUser(str(STUDENT)), advisor.ledger_entry_id)
    with pytest.raises(DecisionTracePersistenceError):
        await service.get_advisor_history_detail(CurrentUser(str(ADVISOR)), STUDENT, full.ledger_entry_id)


@pytest.mark.anyio
async def test_denied_roles_assignment_tenant_unknown_and_tamper_fail_closed():
    good = entry(student=STUDENT, university=UNIVERSITY)
    service, assignments, repository = await _setup((good,))
    from app.decision_trace_persistence import DecisionTracePersistenceError
    for principal, target in ((UNASSIGNED, STUDENT), (ANALYST, STUDENT), (STUDENT, STUDENT),
                              (ADVISOR, OTHER)):
        with pytest.raises(DecisionTracePersistenceError):
            await service.list_advisor_history(CurrentUser(str(principal)), target)
    assignments.assignments[0] = replace(assignments.assignments[0], is_active=False)
    with pytest.raises(DecisionTracePersistenceError):
        await service.list_advisor_history(CurrentUser(str(ADVISOR)), STUDENT)
    assignments.assignments[0] = replace(assignments.assignments[0], is_active=True)
    assignments.student_universities[STUDENT] = uuid4()
    with pytest.raises(DecisionTracePersistenceError):
        await service.list_advisor_history(CurrentUser(str(ADVISOR)), STUDENT)
    assignments.student_universities[STUDENT] = UNIVERSITY
    repository.entries = (replace(good, policy_version="tampered"),)
    with pytest.raises(DecisionTracePersistenceError):
        await service.list_advisor_history(CurrentUser(str(ADVISOR)), STUDENT)


@pytest.mark.anyio
async def test_pagination_stable_and_bounded():
    rows = tuple(entry(student=STUDENT, university=UNIVERSITY) for _ in range(3))
    service, _, _ = await _setup(rows)
    first = await service.list_advisor_history(CurrentUser(str(ADVISOR)), STUDENT, limit=2)
    second = await service.list_advisor_history(
        CurrentUser(str(ADVISOR)), STUDENT, limit=2,
        before_created_at=first[-1].created_at, before_entry_id=first[-1].ledger_entry_id,
    )
    assert len({item.ledger_entry_id for item in first + second}) == 3


def test_advisor_api_read_only_and_denial():
    import anyio
    own = entry(student=STUDENT, university=UNIVERSITY, profile=RedactionProfile.ADVISOR_SAFE)
    service, _, _ = anyio.run(_setup, (own,))
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ADVISOR))
    app.dependency_overrides[get_decision_trace_service] = lambda: service
    try:
        with TestClient(app) as client:
            path = f"/api/v1/advisor/students/{STUDENT}/decision-history"
            listed = client.get(path)
            assert listed.status_code == 200 and len(listed.json()) == 1
            assert listed.json()[0]["ledger_entry_id"] == own.ledger_entry_id
            detail = client.get(f"{path}/{own.ledger_entry_id}")
            assert detail.status_code == 200 and detail.json()["integrity_status"] == "VERIFIED"
            assert "actor_id" not in detail.json() and "integrity_hash" not in detail.json()
            assert client.get(f"{path}/{uuid4()}").status_code == 404
            for query in ("?limit=0", "?limit=51", "?before_entry_id=x"):
                assert client.get(path + query).status_code == 422
            for method in (client.post, client.patch, client.delete):
                assert method(path).status_code == 405
            app.dependency_overrides[get_current_user] = lambda: CurrentUser(str(ANALYST))
            assert client.get(path).status_code == 404
    finally:
        app.dependency_overrides.clear()
