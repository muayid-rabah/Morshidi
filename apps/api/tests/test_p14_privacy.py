"""Focused local P14 controls; no Supabase stack, real tenant, or real participants."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import CurrentUser, get_current_user
from app.main import app
from app.mock_registration.models import PrivacyConfiguration
from app.p14_privacy.domain import (AccessDecision, AccessRequest, ConsentStatus, DataCategory,
                                    EvaluationStudy, Measure, MeasureKind, PilotGovernance, PilotIncident, PilotStatus,
                                    Purpose, RetentionRule, StudyStatus, StudyTask,
                                    aggregate_measures, decide_access)
from app.p14_privacy.store import LocalPrivacyStore, PrivacyDenied

OWNER = "10000000-0000-0000-0000-000000000111"
OTHER = "10000000-0000-0000-0000-000000000222"
TENANT = "isolated-p14-tenant-a"
TENANT_B = "isolated-p14-tenant-b"
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def study(tenant=TENANT, status=StudyStatus.ACTIVE):
    return EvaluationStudy("study-p14", tenant, "دراسة تجريبية", "Synthetic study",
                           "No real participants", "v1", status, "consent-v1",
                           frozenset({OWNER}),
                           (StudyTask("task-1", "افهم سبب المنع", "Explain the block",
                                      "eligibility explanation", "v1", "Keyboard and RTL"),),
                           frozenset(MeasureKind), NOW - timedelta(days=1),
                           NOW + timedelta(days=1),
                           local_approval_reference="LOCAL_SYNTHETIC_REVIEW",
                           local_approval_verified=True)


def consent(store, owner=OWNER, tenant=TENANT, purpose=Purpose.PRODUCT_EVALUATION,
            version="consent-v1", expires=None):
    return store.grant(owner, tenant, purpose, version, "modeled-policy-v1",
                       ("study:study-p14",), expires_at=expires, now=NOW)


@pytest.mark.parametrize("purpose", list(Purpose))
def test_typed_purpose_never_replaces_role_or_tenant_authorization(purpose):
    request = AccessRequest(OWNER, OWNER, TENANT, TENANT, purpose, "study:study-p14", False)
    assert decide_access(request, NOW) is AccessDecision.DENY
    assert decide_access(replace(request, role_authorized=True,
                                 subject_institution_id=TENANT_B), NOW) is AccessDecision.DENY


def test_optional_purpose_requires_exact_versioned_scoped_consent():
    store = LocalPrivacyStore()
    first = consent(store)
    assert store.access(OWNER, OWNER, TENANT, Purpose.PRODUCT_EVALUATION,
                        "study:study-p14", True, NOW) is AccessDecision.ALLOW
    assert store.access(OWNER, OWNER, TENANT, Purpose.RESEARCH_STUDY,
                        "study:study-p14", True, NOW) is AccessDecision.DENY
    assert store.access(OWNER, OWNER, TENANT, Purpose.PRODUCT_EVALUATION,
                        "different-scope", True, NOW) is AccessDecision.DENY
    second = consent(store, version="consent-v2")
    assert second.consent_id != first.consent_id
    assert store.summary(OWNER, TENANT)["consents"][0]["status"] is ConsentStatus.REVOKED
    assert store.summary(OWNER, TENANT)["consents"][1]["consent_version"] == "consent-v2"


def test_expiry_withdrawal_and_core_services_are_separate():
    store = LocalPrivacyStore((study(),))
    expired = consent(store, expires=NOW + timedelta(seconds=1))
    assert store.summary(OWNER, TENANT, NOW + timedelta(seconds=2))["consents"][0]["status"] == "EXPIRED"
    assert store.access(OWNER, OWNER, TENANT, Purpose.PRODUCT_EVALUATION,
                        "study:study-p14", True, NOW + timedelta(seconds=2)) is AccessDecision.DENY
    current = consent(store)
    store.study_join(OWNER, TENANT, "study-p14", NOW)
    withdrawn = store.withdraw(OWNER, TENANT, current.consent_id, NOW)
    assert withdrawn.status is ConsentStatus.WITHDRAWN
    assert withdrawn.withdrawn_at == NOW
    assert store.summary(OWNER, TENANT)["participation"][0]["status"] == "WITHDRAWN"
    assert store.access(OWNER, OWNER, TENANT, Purpose.PRODUCT_EVALUATION,
                        "study:study-p14", True, NOW) is AccessDecision.DENY
    assert store.access(OWNER, OWNER, TENANT, Purpose.ACADEMIC_SUPPORT,
                        "core_profile", True, NOW) is AccessDecision.ALLOW
    with pytest.raises(PrivacyDenied):
        store.study_join(OWNER, TENANT, "study-p14", NOW)
    with pytest.raises(PrivacyDenied):
        store.grant_study_consent(OWNER, TENANT, "study-p14", NOW)
    assert store.available_studies(OWNER, TENANT, NOW) == ()
    with pytest.raises(PrivacyDenied):
        store.measure(OWNER, TENANT, "study-p14", "task-1", MeasureKind.TASK_SUCCESS, 1, now=NOW)
    assert expired.status is ConsentStatus.GRANTED  # time, not a history rewrite, makes it inactive


@pytest.mark.parametrize("category,retained", [
    (DataCategory.DELETABLE_OPTIONAL_DATA, False),
    (DataCategory.RETENTION_REQUIRED_DATA, True),
    (DataCategory.AUTHORITATIVE_INSTITUTIONAL_RECORD, True),
    (DataCategory.AUDIT_REQUIRED_RECORD, True),
])
def test_governed_deletion_request_never_deletes_academic_truth(category, retained):
    store = LocalPrivacyStore()
    item = store.request(OWNER, TENANT, "DELETION", category, "Review this data", now=NOW)
    assert (item.retained_reason is not None) is retained
    assert item.status == "OPEN"
    assert item.effective_at is None
    assert store.get_request(OWNER, TENANT, item.request_id) == item
    with pytest.raises(PrivacyDenied):
        store.get_request(OTHER, TENANT, item.request_id)


def test_export_correction_retention_and_minimal_audit():
    rule = RetentionRule(DataCategory.RETENTION_REQUIRED_DATA, Purpose.ACADEMIC_SUPPORT,
                         "UNSPECIFIED", "MODELED", "HUMAN_REVIEW", "v1", NOW)
    store = LocalPrivacyStore(retention=(rule,))
    consent(store)
    correction = store.request(OWNER, TENANT, "CORRECTION",
                               DataCategory.AUTHORITATIVE_INSTITUTIONAL_RECORD,
                               "Incorrect course result", "course-record", NOW)
    store.request(OTHER, TENANT, "CORRECTION", DataCategory.DELETABLE_OPTIONAL_DATA,
                  "Other request", now=NOW)
    result = store.export(OWNER, TENANT, NOW)
    assert result["scope"] == "OWNER_PRIVACY_RECORDS_ONLY"
    assert result["source_sections"]["requests"][0]["request_id"] == correction.request_id
    assert [row["kind"] for row in result["source_sections"]["requests"]] == ["CORRECTION", "EXPORT"]
    assert OTHER not in str(result)
    assert store.summary(OWNER, TENANT)["retention"][0]["status"] == "UNVERIFIED_POLICY"
    assert {event.event_type for event in store.audit_events} >= {
        "CONSENT_GRANTED", "CORRECTION_REQUESTED", "EXPORT_REQUESTED", "EXPORT_GENERATED"}
    assert all(not hasattr(event, "reason") for event in store.audit_events)


def test_study_assignment_tasks_measures_feedback_and_aggregate_suppression():
    store = LocalPrivacyStore((study(),))
    with pytest.raises(PrivacyDenied):
        store.study_join(OWNER, TENANT, "study-p14", NOW)
    consent(store)
    participant = store.study_join(OWNER, TENANT, "study-p14", NOW)
    assert participant.pseudonym != OWNER
    for kind, value in ((MeasureKind.TASK_SUCCESS, 1), (MeasureKind.TASK_COMPLETION_TIME, 30),
                        (MeasureKind.COMPREHENSION, 4), (MeasureKind.TRUST, 4),
                        (MeasureKind.WORKLOAD, 3), (MeasureKind.ACCESSIBILITY_FEEDBACK, 1)):
        store.measure(OWNER, TENANT, "study-p14", "task-1", kind, value,
                      ("KEYBOARD", "RTL"), NOW)
    feedback = store.feedback(OWNER, TENANT, "study-p14", 4, 5, 4, 2, True, now=NOW)
    assert store.feedback_item(OWNER, TENANT, feedback.feedback_id) == feedback
    with pytest.raises(PrivacyDenied):
        store.feedback_item(OTHER, TENANT, feedback.feedback_id)
    with pytest.raises(PrivacyDenied):
        store.request(OTHER, TENANT, "DELETION", DataCategory.DELETABLE_OPTIONAL_DATA,
                      "Delete guessed feedback", feedback.feedback_id, NOW)
    own_deletion = store.request(OWNER, TENANT, "DELETION", DataCategory.DELETABLE_OPTIONAL_DATA,
                                 "Delete own feedback", feedback.feedback_id, NOW)
    assert own_deletion.status == "OPEN"
    export = store.export(OWNER, TENANT, NOW)
    assert export["source_sections"]["feedback"][0]["feedback_id"] == feedback.feedback_id
    assert store.aggregate_study("study-p14", TENANT, PrivacyConfiguration(2, "v1"), 1, NOW)["status"] == "SUPPRESSED"
    assert store.aggregate_study("study-p14", TENANT, PrivacyConfiguration(2, "v1"), 0, NOW)["status"] == "QUERY_BUDGET_EXHAUSTED"


def test_aggregate_results_are_tenant_bound_suppressed_and_exclude_withdrawn():
    rows = (Measure("study-p14", TENANT, "task-1", "pseudo-a", MeasureKind.TRUST, 4, NOW, "consent-a"),
            Measure("study-p14", TENANT, "task-1", "pseudo-b", MeasureKind.TRUST, 2, NOW, "consent-b"),
            Measure("study-p14", TENANT_B, "task-1", "pseudo-c", MeasureKind.TRUST, 5, NOW, "consent-c"))
    privacy = PrivacyConfiguration(2, "v1")
    result = aggregate_measures(study(), rows, frozenset({"pseudo-a", "pseudo-b", "pseudo-c"}), privacy, 1)
    assert result["status"] == "AGGREGATE_ONLY"
    assert result["metrics"]["TRUST"] == {"count": 2, "median": 3.0}
    assert "pseudo" not in str(result)
    assert aggregate_measures(study(), rows, frozenset({"pseudo-a"}), privacy, 1)["status"] == "SUPPRESSED"


def test_inactive_foreign_and_withdrawn_studies_fail_closed():
    store = LocalPrivacyStore((study(status=StudyStatus.DRAFT),))
    consent(store)
    with pytest.raises(PrivacyDenied):
        store.study_join(OWNER, TENANT, "study-p14", NOW)
    foreign = LocalPrivacyStore((study(TENANT_B),))
    consent(foreign)
    with pytest.raises(PrivacyDenied):
        foreign.study_join(OWNER, TENANT, "study-p14", NOW)
    unapproved = LocalPrivacyStore((replace(study(), local_approval_verified=False),))
    consent(unapproved)
    with pytest.raises(PrivacyDenied):
        unapproved.study_join(OWNER, TENANT, "study-p14", NOW)


def test_pilot_approval_consent_support_and_institution_boundaries():
    store = LocalPrivacyStore()
    pilot_consent = store.grant(OWNER, TENANT, Purpose.PILOT_OPERATIONS, "v1", "modeled-pilot",
                                ("pilot_participation",), now=NOW)
    base = PilotGovernance("pilot-local", TENANT, "modeled-sponsor", None,
                           frozenset({OWNER}), "v1", NOW - timedelta(days=1),
                           NOW + timedelta(days=1), frozenset({"roadmap"}), {"catalog": "v1"},
                           "support", "incident", "exit", "monitor", "modeled-policy")
    assert not base.may_activate(NOW, OWNER, TENANT, pilot_consent)
    with pytest.raises(ValueError):
        replace(base, status=PilotStatus.ACTIVE)
    approved = replace(base, approval_reference="UNVERIFIED_LOCAL_REFERENCE",
                       status=PilotStatus.APPROVED)
    assert not approved.may_activate(NOW, OWNER, TENANT, pilot_consent)
    approved = replace(approved, approval_verified=True)
    assert approved.may_activate(NOW, OWNER, TENANT, pilot_consent)
    enrollment = approved.activate_for(NOW, OWNER, TENANT, pilot_consent)
    assert enrollment.allows("roadmap", TENANT, NOW, pilot_consent)
    assert not enrollment.allows("unapproved", TENANT, NOW, pilot_consent)
    assert not enrollment.allows("roadmap", TENANT_B, NOW, pilot_consent)
    assert not enrollment.stop(NOW, "PAUSED").allows("roadmap", TENANT, NOW, pilot_consent)
    assert not enrollment.stop(NOW).allows("roadmap", TENANT, NOW, pilot_consent)
    assert not approved.may_activate(NOW, OWNER, TENANT_B, pilot_consent)
    assert not approved.may_activate(NOW, OTHER, TENANT, pilot_consent)
    assert not replace(approved, incident_procedure=None).may_activate(NOW, OWNER, TENANT, pilot_consent)
    assert not replace(approved, status=PilotStatus.PAUSED).may_activate(NOW, OWNER, TENANT, pilot_consent)
    assert not replace(approved, status=PilotStatus.ENDED).may_activate(NOW, OWNER, TENANT, pilot_consent)
    store.withdraw(OWNER, TENANT, pilot_consent.consent_id, NOW)
    assert not approved.may_activate(NOW, OWNER, TENANT, store._consents[pilot_consent.consent_id])
    assert not enrollment.allows("roadmap", TENANT, NOW, store._consents[pilot_consent.consent_id])


def test_pilot_incident_metadata_is_bounded_without_sensitive_payload():
    from app.p14_privacy.domain import PilotIncident
    item = PilotIncident("incident-1", "pilot-local", "PRIVACY_EVENT", "HIGH", NOW,
                         "OPEN", "BOUNDED_PRIVACY_EVENT", "privacy-owner", None, True)
    assert item.follow_up_required
    with pytest.raises(ValueError):
        replace(item, kind="RAW_STUDENT_TRANSCRIPT")
    with pytest.raises(ValueError):
        replace(item, summary_code="x" * 81)


def test_no_participant_or_researcher_detail_endpoint_is_exposed():
    paths = set(app.openapi()["paths"])
    assert "/api/v1/me/privacy" in paths
    assert not any(path.startswith("/api/v1/institutional/evaluation") for path in paths)


class StudentStub:
    async def resolve_student_university_id(self, owner):
        return TENANT if owner == OWNER else TENANT_B


def test_api_requires_auth_and_no_production_provider():
    with TestClient(app) as client:
        assert client.get("/api/v1/me/privacy").status_code == 401
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(OWNER)
        try:
            assert client.get("/api/v1/me/privacy").status_code == 503
        finally:
            app.dependency_overrides.clear()


def test_api_owner_scope_spoofing_and_idor(monkeypatch):
    monkeypatch.setattr("app.p14_privacy.store.utc_now", lambda: NOW)
    identity = {"owner": OWNER}
    store = LocalPrivacyStore((study(),))
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(identity["owner"])
    try:
        with TestClient(app) as client:
            app.state.student_service = StudentStub()
            app.state.p14_privacy_store = store
            body = {"study_id": "study-p14"}
            assert client.post("/api/v1/me/privacy/consents", json={**body, "student_id": OTHER}).status_code == 422
            granted = client.post("/api/v1/me/privacy/consents", json=body)
            assert granted.status_code == 200
            assert granted.json()["policy_reference"] == "SYNTHETIC_STUDY:study-p14:v1"
            assert client.post("/api/v1/me/privacy/consents", json={
                **body, "policy_reference": "attacker-policy"}).status_code == 422
            consent_id = granted.json()["consent_id"]
            assert client.get("/api/v1/me/privacy", params={"student_id": OTHER}).json()["consents"][0]["subject_id"] == OWNER
            assert client.post("/api/v1/me/privacy/studies/study-p14/join").status_code == 200
            feedback = client.post("/api/v1/me/privacy/studies/study-p14/feedback", json={
                "clarity": 4, "usefulness": 4, "understanding": 4, "workload": 3,
                "accessibility_issue": False})
            assert feedback.status_code == 200
            feedback_id = feedback.json()["feedback_id"]
            created = client.post("/api/v1/me/privacy/requests", json={"kind": "CORRECTION",
                "category": "AUTHORITATIVE_INSTITUTIONAL_RECORD", "reason": "Review"})
            request_id = created.json()["request_id"]
            assert client.post("/api/v1/me/privacy/export").json()["subject"] == OWNER
            identity["owner"] = OTHER
            assert client.get(f"/api/v1/me/privacy/requests/{request_id}").status_code == 404
            assert client.get(f"/api/v1/me/privacy/feedback/{feedback_id}").status_code == 404
            assert client.post("/api/v1/me/privacy/requests", json={"kind": "DELETION",
                "category": "DELETABLE_OPTIONAL_DATA", "reason": "Delete this",
                "source_reference": feedback_id}).status_code == 404
            assert client.post(f"/api/v1/me/privacy/consents/{consent_id}/withdraw").status_code == 404
            assert client.post("/api/v1/me/privacy/studies/study-p14/join").status_code == 404
            assert client.post("/api/v1/me/privacy/export").json()["source_sections"]["consents"] == []
            identity["owner"] = OWNER
            assert client.post(f"/api/v1/me/privacy/consents/{consent_id}/withdraw").status_code == 200
            assert client.post("/api/v1/me/privacy/studies/study-p14/measures", json={
                "task_id": "task-1", "kind": "TASK_SUCCESS", "value": 1}).status_code == 404
    finally:
        app.dependency_overrides.clear()
        app.state.p14_privacy_store = None
        app.state.student_service = None


def test_chat_export_and_deletion_request_are_owner_scoped_and_non_destructive():
    from uuid import uuid4
    from app.student_conversation.store import ConversationNotFound

    thread_id = str(uuid4())
    identity = {"owner": OWNER}
    thread = {"id": thread_id, "owner_user_id": OWNER, "institution_id": TENANT,
              "title": "Private academic chat", "summary_text": "regular_load=15",
              "status": "ARCHIVED"}

    class ChatStore:
        async def get_thread(self, owner, institution, candidate):
            if (owner, institution, candidate) != (OWNER, TENANT, thread_id):
                raise ConversationNotFound("Conversation not found")
            return thread

        async def export_owned_chats(self, owner, institution):
            if (owner, institution) != (OWNER, TENANT):
                return {"threads": [], "messages": [], "active_planning_preferences": {},
                        "retention_policy": "RETENTION_POLICY_NOT_VERIFIED"}
            return {"threads": [thread], "messages": [{"thread_id": thread_id,
                    "role": "USER", "content": "I prefer 15 credits"}],
                    "active_planning_preferences": {"regular_load": "15"},
                    "retention_policy": "RETENTION_POLICY_NOT_VERIFIED"}

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(identity["owner"])
    try:
        with TestClient(app) as client:
            app.state.student_service = StudentStub()
            app.state.p14_privacy_store = LocalPrivacyStore()
            app.state.student_conversation_store = ChatStore()
            exported = client.post("/api/v1/me/privacy/export").json()
            assert exported["source_sections"]["conversations"]["threads"][0]["id"] == thread_id
            assert exported["source_sections"]["conversations"]["active_planning_preferences"] == {
                "regular_load": "15"}
            assert "reasoning" not in str(exported).lower()
            body = {"kind": "DELETION", "category": "DELETABLE_OPTIONAL_DATA", "reason": "Review",
                    "source_kind": "CONVERSATION_THREAD", "source_reference": thread_id}
            request = client.post("/api/v1/me/privacy/requests", json=body)
            assert request.status_code == 200
            assert request.json()["source_reference"] == f"CONVERSATION_THREAD:{thread_id}"
            assert request.json()["retained_reason"] == "HUMAN_REVIEW_REQUIRED_RETENTION_POLICY_NOT_VERIFIED"
            assert thread["status"] == "ARCHIVED"
            identity["owner"] = OTHER
            assert client.post("/api/v1/me/privacy/export").json()["source_sections"]["conversations"]["threads"] == []
            assert client.post("/api/v1/me/privacy/requests", json=body).status_code == 404
            assert client.get(f"/api/v1/me/privacy/requests/{request.json()['request_id']}").status_code == 404
    finally:
        app.dependency_overrides.clear()
        app.state.student_service = None
        app.state.p14_privacy_store = None
        app.state.student_conversation_store = None
