"""Real Local Supabase advisor assignment, tenant, and redaction matrix."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.core.auth import CurrentUser
from app.decision_trace import RedactionProfile
from app.decision_trace_persistence import DecisionTracePersistenceError
from tests.test_decision_trace_persistence_service_local_supabase import (
    URL, ANON_KEY, SERVER_KEY, _advisor_entry, _assignment, _create_profile,
    _create_user, _membership, _plan_scope, _service,
    _student_entry,
)
from tests.test_decision_trace_persistence_local_supabase import _foreign_university_id


pytestmark = pytest.mark.skipif(
    not all((URL, ANON_KEY, SERVER_KEY)),
    reason="set local-only MORSHIDI_LOCAL_SUPABASE_* values",
)


@pytest.mark.anyio
async def test_local_advisor_history_exact_assignment_tenant_profile_and_analyst_denial():
    with httpx.Client(timeout=30) as raw:
        plan_id, university_id = _plan_scope(raw)
        student_a, _ = _create_user(raw, "history-student-a")
        student_b, _ = _create_user(raw, "history-student-b")
        assigned, _ = _create_user(raw, "history-advisor-assigned")
        unassigned, _ = _create_user(raw, "history-advisor-unassigned")
        analyst, _ = _create_user(raw, "history-analyst")
        foreign_advisor, _ = _create_user(raw, "history-advisor-foreign")
        for student in (student_a, student_b):
            _create_profile(raw, student, plan_id)
        _membership(raw, assigned, university_id, "ACADEMIC_ADVISOR")
        _membership(raw, unassigned, university_id, "ACADEMIC_ADVISOR")
        _membership(raw, analyst, university_id, "INSTITUTIONAL_ANALYST")
        _membership(raw, foreign_advisor, _foreign_university_id(raw), "ACADEMIC_ADVISOR")
        _assignment(raw, assigned, student_a, university_id)

        async with httpx.AsyncClient(timeout=30) as client:
            service, repository = _service(client)
            student_safe = _student_entry(student_a, university_id)
            advisor_safe = _advisor_entry(assigned, student_a, university_id)
            other_student = _student_entry(student_b, university_id)
            full_audit = _student_entry(
                student_a, university_id, redaction_profile=RedactionProfile.FULL_AUDIT,
            )
            for item in (student_safe, advisor_safe, other_student, full_audit):
                assert await repository.append(item) == item.ledger_entry_id

            owner = await service.list_student_history(CurrentUser(student_a))
            assert [item.ledger_entry_id for item in owner] == [student_safe.ledger_entry_id]
            assigned_page = await service.list_advisor_history(CurrentUser(assigned), student_a)
            assert {item.ledger_entry_id for item in assigned_page} == {
                student_safe.ledger_entry_id, advisor_safe.ledger_entry_id,
            }
            for item in (student_safe, advisor_safe):
                detail = await service.get_advisor_history_detail(
                    CurrentUser(assigned), student_a, item.ledger_entry_id,
                )
                assert detail.integrity_status == "VERIFIED"
            with pytest.raises(DecisionTracePersistenceError):
                await service.get_student_history_detail(CurrentUser(student_a), advisor_safe.ledger_entry_id)
            for principal, target in (
                (unassigned, student_a), (analyst, student_a),
                (foreign_advisor, student_a), (assigned, student_b),
                (assigned, uuid4()),
            ):
                with pytest.raises(DecisionTracePersistenceError) as denied:
                    await service.list_advisor_history(CurrentUser(principal), target)
                assert denied.value.code.value == "ACCESS_DENIED"
            for target in (other_student.ledger_entry_id, full_audit.ledger_entry_id, str(uuid4())):
                with pytest.raises(DecisionTracePersistenceError):
                    await service.get_advisor_history_detail(CurrentUser(assigned), student_a, target)
