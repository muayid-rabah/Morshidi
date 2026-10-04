"""Test-injected local P14 store; deliberately not configured in production."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, replace
from datetime import datetime
from threading import RLock
from typing import Mapping, Any
from uuid import uuid4

from .domain import (AccessDecision, AccessRequest, Consent, ConsentStatus, DataCategory,
                     EvaluationStudy, Feedback, Measure, MeasureKind, Participation,
                     ParticipationStatus, PrivacyEvent, PrivacyRequest, Purpose,
                     RetentionRule, StudyStatus, aggregate_measures, decide_access, utc_now)
from app.mock_registration.models import PrivacyConfiguration


class PrivacyDenied(PermissionError):
    """Bounded denial; callers must not reveal other subjects' records."""


class LocalPrivacyStore:
    """Process-local synthetic data only; restart loses state; never a production provider."""

    def __init__(self, studies: tuple[EvaluationStudy, ...] = (),
                 retention: tuple[RetentionRule, ...] = ()) -> None:
        self._lock = RLock()
        self._studies = {study.study_id: study for study in studies}
        self._retention = retention
        self._consents: dict[str, Consent] = {}
        self._requests: dict[str, PrivacyRequest] = {}
        self._events: list[PrivacyEvent] = []
        self._participation: dict[tuple[str, str, str], Participation] = {}
        self._feedback: dict[str, Feedback] = {}
        self._measures: list[Measure] = []

    def _event(self, owner: str, institution: str, kind: str, purpose: Purpose,
               scope: str, result: str, now: datetime, actor: str | None = None) -> None:
        self._events.append(PrivacyEvent(str(uuid4()), kind, actor or owner, owner, institution,
                                         purpose, scope, result, now))

    def _active_consent(self, owner: str, institution: str, purpose: Purpose,
                        scope: str, now: datetime) -> Consent | None:
        matches = (record for record in self._consents.values()
                   if record.subject_id == owner and record.institution_id == institution
                   and record.purpose is purpose and record.active(now, scope))
        return max(matches, key=lambda item: item.granted_at, default=None)

    @staticmethod
    def _consent_view(record: Consent, now: datetime) -> dict:
        if record.status is ConsentStatus.GRANTED and record.expires_at is not None and now >= record.expires_at:
            return asdict(replace(record, status=ConsentStatus.EXPIRED))
        return asdict(record)

    def access(self, actor: str, owner: str, institution: str, purpose: Purpose,
               scope: str, role_authorized: bool, now: datetime | None = None) -> AccessDecision:
        now = now or utc_now()
        with self._lock:
            consent = self._active_consent(owner, institution, purpose, scope, now)
            result = decide_access(AccessRequest(actor, owner, institution, institution,
                                                 purpose, scope, role_authorized, consent), now)
            if result is not AccessDecision.ALLOW:
                self._event(owner, institution, "DATA_ACCESS_DENIED", purpose, scope,
                            result.value, now, actor)
            return result

    def grant(self, owner: str, institution: str, purpose: Purpose, version: str,
              policy_reference: str, scopes: tuple[str, ...], expires_at: datetime | None = None,
              now: datetime | None = None) -> Consent:
        now = now or utc_now()
        if purpose not in {Purpose.PRODUCT_EVALUATION, Purpose.RESEARCH_STUDY, Purpose.PILOT_OPERATIONS}:
            raise ValueError("Core purposes do not use optional consent")
        if not owner or not institution or not version.strip() or not policy_reference.strip() or not scopes or \
           any(not scope.strip() for scope in scopes) or len(set(scopes)) != len(scopes) or \
           (expires_at is not None and (expires_at.tzinfo is None or expires_at <= now)):
            raise ValueError("Invalid consent contract")
        with self._lock:
            for consent_id, record in tuple(self._consents.items()):
                if record.subject_id == owner and record.institution_id == institution and \
                   record.purpose is purpose and record.status is ConsentStatus.GRANTED and \
                   set(record.scopes).intersection(scopes):
                    self._consents[consent_id] = replace(record, status=ConsentStatus.REVOKED)
            record = Consent(str(uuid4()), owner, institution, purpose, version,
                             policy_reference, scopes, now, expires_at, None,
                             ConsentStatus.GRANTED, "EXPLICIT_LOCAL_OWNER_ACTION", owner)
            self._consents[record.consent_id] = record
            self._event(owner, institution, "CONSENT_GRANTED", purpose, "consent", "GRANTED", now)
            return record

    def withdraw(self, owner: str, institution: str, consent_id: str,
                 now: datetime | None = None) -> Consent:
        now = now or utc_now()
        with self._lock:
            record = self._consents.get(consent_id)
            if record is None or record.subject_id != owner or record.institution_id != institution:
                raise PrivacyDenied("CONSENT_UNAVAILABLE")
            if record.status is ConsentStatus.WITHDRAWN:
                return record
            if record.status is not ConsentStatus.GRANTED:
                raise PrivacyDenied("CONSENT_NOT_ACTIVE")
            updated = replace(record, status=ConsentStatus.WITHDRAWN, withdrawn_at=now)
            self._consents[consent_id] = updated
            for key, participation in tuple(self._participation.items()):
                if participation.subject_id == owner and participation.institution_id == institution and \
                   participation.consent_id == consent_id and participation.status is ParticipationStatus.ACTIVE:
                    self._participation[key] = replace(participation, status=ParticipationStatus.WITHDRAWN)
                    self._event(owner, institution, "STUDY_EXITED", record.purpose, "study", "WITHDRAWN", now)
            self._event(owner, institution, "CONSENT_WITHDRAWN", record.purpose, "consent", "WITHDRAWN", now)
            return updated

    def grant_study_consent(self, owner: str, institution: str, study_id: str,
                            now: datetime | None = None) -> Consent:
        now = now or utc_now()
        with self._lock:
            study = self._studies.get(study_id)
            if study is None or study.institution_id != institution or \
               owner not in study.eligible_subjects or not study.active(now) or \
               ((prior := self._participation.get((owner, institution, study_id))) is not None
                and prior.status in {ParticipationStatus.WITHDRAWN, ParticipationStatus.EXCLUDED}):
                raise PrivacyDenied("STUDY_UNAVAILABLE")
            return self.grant(owner, institution, Purpose.PRODUCT_EVALUATION,
                              study.consent_version,
                              f"SYNTHETIC_STUDY:{study.study_id}:{study.version}",
                              (f"study:{study.study_id}",), now=now)

    def request(self, owner: str, institution: str, kind: str, category: DataCategory,
                reason: str, source_reference: str | None = None,
                now: datetime | None = None) -> PrivacyRequest:
        now = now or utc_now()
        if kind not in {"EXPORT", "CORRECTION", "DELETION"} or not reason.strip() or len(reason) > 500:
            raise ValueError("Invalid privacy request")
        retained_reason = None
        if kind == "DELETION" and category is not DataCategory.DELETABLE_OPTIONAL_DATA:
            retained_reason = "HUMAN_REVIEW_REQUIRED_NO_AUTOMATIC_DELETION"
        with self._lock:
            if kind == "DELETION" and category is DataCategory.DELETABLE_OPTIONAL_DATA and source_reference:
                feedback = self._feedback.get(source_reference)
                if feedback is None or feedback.subject_id != owner or feedback.institution_id != institution:
                    raise PrivacyDenied("OPTIONAL_DATA_UNAVAILABLE")
            item = PrivacyRequest(str(uuid4()), owner, institution, kind, category,
                                  reason, source_reference, now, retained_reason=retained_reason)
            self._requests[item.request_id] = item
            self._event(owner, institution, f"{kind}_REQUESTED", Purpose.ACADEMIC_SUPPORT,
                        category.value, "OPEN", now)
            return item

    def get_request(self, owner: str, institution: str, request_id: str) -> PrivacyRequest:
        with self._lock:
            item = self._requests.get(request_id)
            if item is None or item.subject_id != owner or item.institution_id != institution:
                raise PrivacyDenied("REQUEST_UNAVAILABLE")
            return item

    def request_conversation_deletion(self, owner: str, institution: str,
                                      owned_thread: Mapping[str, Any], reason: str) -> PrivacyRequest:
        """Queue human review of an already owner-verified thread; never delete chat."""
        thread_id = owned_thread.get("id")
        if (owned_thread.get("owner_user_id") != owner or
                owned_thread.get("institution_id") != institution or not thread_id):
            raise PrivacyDenied("OPTIONAL_DATA_UNAVAILABLE")
        item = self.request(owner, institution, "DELETION", DataCategory.DELETABLE_OPTIONAL_DATA,
                            reason)
        with self._lock:
            item = replace(item, source_reference=f"CONVERSATION_THREAD:{thread_id}",
                           retained_reason="HUMAN_REVIEW_REQUIRED_RETENTION_POLICY_NOT_VERIFIED")
            self._requests[item.request_id] = item
        return item

    def study_join(self, owner: str, institution: str, study_id: str,
                   now: datetime | None = None) -> Participation:
        now = now or utc_now()
        with self._lock:
            study = self._studies.get(study_id)
            if study is None or study.institution_id != institution or not study.active(now) or \
               owner not in study.eligible_subjects:
                raise PrivacyDenied("STUDY_UNAVAILABLE")
            consent = self._active_consent(owner, institution, Purpose.PRODUCT_EVALUATION,
                                           f"study:{study_id}", now)
            if consent is None or consent.consent_version != study.consent_version:
                raise PrivacyDenied("STUDY_CONSENT_REQUIRED")
            key = (owner, institution, study_id)
            previous = self._participation.get(key)
            if previous is not None and previous.status in {ParticipationStatus.WITHDRAWN,
                                                             ParticipationStatus.EXCLUDED}:
                raise PrivacyDenied("STUDY_UNAVAILABLE")
            if previous is not None:
                return previous
            pseudonym = hashlib.sha256(f"{uuid4()}:{study_id}".encode()).hexdigest()
            item = Participation(study_id, owner, institution, pseudonym,
                                 ParticipationStatus.ACTIVE, consent.consent_id)
            self._participation[key] = item
            self._event(owner, institution, "STUDY_JOINED", Purpose.PRODUCT_EVALUATION,
                        f"study:{study_id}", "ACTIVE", now)
            return item

    def available_studies(self, owner: str, institution: str,
                          now: datetime | None = None) -> tuple[dict, ...]:
        now = now or utc_now()
        with self._lock:
            return tuple({"study_id": study.study_id, "title_ar": study.title_ar,
                          "title_en": study.title_en, "version": study.version,
                          "consent_version": study.consent_version,
                          "tasks": tuple({"task_id": task.task_id,
                                          "instruction_ar": task.instruction_ar,
                                          "instruction_en": task.instruction_en,
                                          "accessibility_note": task.accessibility_note}
                                         for task in study.tasks),
                          "label": "SYNTHETIC STUDY — NO REAL PARTICIPANTS"}
                         for study in self._studies.values()
                         if study.institution_id == institution and study.active(now)
                         and owner in study.eligible_subjects
                         and not ((prior := self._participation.get((owner, institution, study.study_id))) is not None
                                  and prior.status in {ParticipationStatus.WITHDRAWN,
                                                       ParticipationStatus.EXCLUDED}))

    def measure(self, owner: str, institution: str, study_id: str, task_id: str,
                kind: MeasureKind, value: int, flags: tuple[str, ...] = (),
                now: datetime | None = None) -> Measure:
        now = now or utc_now()
        with self._lock:
            study = self._studies.get(study_id)
            item = self._participation.get((owner, institution, study_id))
            if study is None or study.institution_id != institution or not study.active(now) or \
               item is None or item.status is not ParticipationStatus.ACTIVE or \
               self.access(owner, owner, institution, Purpose.PRODUCT_EVALUATION,
                           f"study:{study_id}", True, now) is not AccessDecision.ALLOW:
                raise PrivacyDenied("STUDY_UNAVAILABLE")
            task = next((task for task in study.tasks if task.task_id == task_id), None)
            bounds = {MeasureKind.TASK_SUCCESS: (0, 1),
                      MeasureKind.TASK_COMPLETION_TIME: (0, task.max_seconds if task else 0),
                      MeasureKind.COMPREHENSION: (1, 5), MeasureKind.TRUST: (1, 5),
                      MeasureKind.WORKLOAD: (1, 5), MeasureKind.ACCESSIBILITY_FEEDBACK: (0, 1),
                      MeasureKind.USER_SATISFACTION: (1, 5)}
            if task is None or kind not in study.allowed_measures or not isinstance(value, int) or \
               isinstance(value, bool) or not bounds[kind][0] <= value <= bounds[kind][1] or \
               set(flags) - {"KEYBOARD", "SCREEN_READER", "RTL", "MOBILE", "CONTRAST", "LANGUAGE"}:
                raise ValueError("Invalid bounded measure")
            result = Measure(study_id, institution, task_id, item.pseudonym, kind, value, now,
                             item.consent_id, tuple(sorted(set(flags))))
            self._measures.append(result)
            return result

    def feedback(self, owner: str, institution: str, study_id: str, clarity: int,
                 usefulness: int, understanding: int, workload: int,
                 accessibility_issue: bool, comment: str | None = None,
                 now: datetime | None = None) -> Feedback:
        now = now or utc_now()
        with self._lock:
            participation = self._participation.get((owner, institution, study_id))
            if participation is None or participation.status is not ParticipationStatus.ACTIVE or \
               self.access(owner, owner, institution, Purpose.PRODUCT_EVALUATION,
                           f"study:{study_id}", True, now) is not AccessDecision.ALLOW:
                raise PrivacyDenied("STUDY_UNAVAILABLE")
            if any(not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5
                   for value in (clarity, usefulness, understanding, workload)) or \
               (comment is not None and len(comment) > 280):
                raise ValueError("Invalid bounded feedback")
            item = Feedback(str(uuid4()), study_id, owner, institution, clarity,
                            usefulness, understanding, workload, accessibility_issue,
                            comment, now)
            self._feedback[item.feedback_id] = item
            return item

    def feedback_item(self, owner: str, institution: str, feedback_id: str) -> Feedback:
        with self._lock:
            item = self._feedback.get(feedback_id)
            if item is None or item.subject_id != owner or item.institution_id != institution:
                raise PrivacyDenied("FEEDBACK_UNAVAILABLE")
            return item

    def export(self, owner: str, institution: str, now: datetime | None = None) -> dict:
        now = now or utc_now()
        with self._lock:
            self.request(owner, institution, "EXPORT", DataCategory.DELETABLE_OPTIONAL_DATA,
                         "Owner requested local privacy export", now=now)
            self._event(owner, institution, "EXPORT_GENERATED", Purpose.ACADEMIC_SUPPORT,
                        "owner_privacy_records", "GENERATED", now)
            return {"schema_version": "P14_LOCAL_V1", "generated_at": now.isoformat(),
                    "subject": owner, "institution_id": institution,
                    "scope": "OWNER_PRIVACY_RECORDS_ONLY",
                    "source_sections": {
                        "consents": [self._consent_view(row, now) for row in self._consents.values()
                                     if row.subject_id == owner and row.institution_id == institution],
                        "participation": [asdict(row) for row in self._participation.values()
                                          if row.subject_id == owner and row.institution_id == institution],
                        "feedback": [asdict(row) for row in self._feedback.values()
                                     if row.subject_id == owner and row.institution_id == institution],
                        "requests": [asdict(row) for row in self._requests.values()
                                     if row.subject_id == owner and row.institution_id == institution]},
                    "privacy_notice": "LOCAL_MODEL_ONLY_NO_OFFICIAL_ACADEMIC_EXPORT"}

    def summary(self, owner: str, institution: str, now: datetime | None = None) -> dict:
        now = now or utc_now()
        with self._lock:
            return {"status": "LOCAL_MODEL_ONLY", "purposes": [item.value for item in Purpose],
                    "consents": [self._consent_view(row, now) for row in self._consents.values()
                                 if row.subject_id == owner and row.institution_id == institution],
                    "participation": [asdict(row) for row in self._participation.values()
                                      if row.subject_id == owner and row.institution_id == institution],
                    "requests": [asdict(row) for row in self._requests.values()
                                 if row.subject_id == owner and row.institution_id == institution],
                    "feedback": [asdict(row) for row in self._feedback.values()
                                 if row.subject_id == owner and row.institution_id == institution],
                    "retention": [asdict(rule) for rule in self._retention],
                    "study_label": "SYNTHETIC STUDY — NO REAL PARTICIPANTS",
                    "limitations": ["NO_PRODUCTION_PERSISTENCE", "NO_OFFICIAL_ACADEMIC_EXPORT",
                                    "NO_REAL_STUDENT_PILOT"]}

    def aggregate_study(self, study_id: str, institution: str,
                        privacy: PrivacyConfiguration, query_budget: int,
                        now: datetime | None = None) -> dict:
        """Internal aggregate only; no institutional API or research role is created."""
        now = now or utc_now()
        with self._lock:
            study = self._studies.get(study_id)
            if study is None or study.institution_id != institution or not study.active(now):
                raise PrivacyDenied("STUDY_UNAVAILABLE")
            eligible = frozenset(item.pseudonym for item in self._participation.values()
                                 if item.study_id == study_id and item.institution_id == institution
                                 and item.status is ParticipationStatus.ACTIVE
                                 and (consent := self._consents.get(item.consent_id)) is not None
                                 and consent.active(now, f"study:{study_id}"))
            return aggregate_measures(study, tuple(self._measures), eligible, privacy, query_budget)

    @property
    def audit_events(self) -> tuple[PrivacyEvent, ...]:
        with self._lock:
            return tuple(self._events)
