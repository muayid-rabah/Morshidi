"""Deterministic P14 controls. No academic records or production data are mutated."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from statistics import median
from typing import Mapping

from app.mock_registration.privacy import should_suppress
from app.mock_registration.models import PrivacyConfiguration


class Purpose(StrEnum):
    ACADEMIC_SUPPORT = "ACADEMIC_SUPPORT"
    ACADEMIC_PLANNING = "ACADEMIC_PLANNING"
    ADVISOR_SUPPORT = "ADVISOR_SUPPORT"
    INSTITUTIONAL_ANALYTICS = "INSTITUTIONAL_ANALYTICS"
    PRODUCT_EVALUATION = "PRODUCT_EVALUATION"
    RESEARCH_STUDY = "RESEARCH_STUDY"
    PILOT_OPERATIONS = "PILOT_OPERATIONS"


OPTIONAL_PURPOSES = frozenset({Purpose.PRODUCT_EVALUATION, Purpose.RESEARCH_STUDY, Purpose.PILOT_OPERATIONS})


class ConsentStatus(StrEnum):
    PENDING = "PENDING"
    GRANTED = "GRANTED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    NOT_REQUIRED = "NOT_REQUIRED"


class AccessDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True)
class Consent:
    consent_id: str
    subject_id: str
    institution_id: str
    purpose: Purpose
    consent_version: str
    policy_reference: str
    scopes: tuple[str, ...]
    granted_at: datetime
    expires_at: datetime | None
    withdrawn_at: datetime | None
    status: ConsentStatus
    provenance: str
    actor_id: str

    def active(self, now: datetime, scope: str) -> bool:
        return (self.status is ConsentStatus.GRANTED and self.withdrawn_at is None
                and (self.expires_at is None or now < self.expires_at) and scope in self.scopes)


@dataclass(frozen=True)
class AccessRequest:
    actor_id: str
    subject_id: str
    institution_id: str
    subject_institution_id: str
    purpose: Purpose
    scope: str
    role_authorized: bool
    consent: Consent | None = None


def decide_access(request: AccessRequest, now: datetime) -> AccessDecision:
    if not isinstance(request.purpose, Purpose) or not request.actor_id or not request.subject_id or \
       not request.institution_id or not request.scope:
        return AccessDecision.ABSTAIN
    if request.institution_id != request.subject_institution_id or not request.role_authorized:
        return AccessDecision.DENY
    if request.purpose in OPTIONAL_PURPOSES:
        consent = request.consent
        if (consent is None or consent.subject_id != request.subject_id
                or consent.institution_id != request.institution_id or consent.purpose is not request.purpose
                or not consent.active(now, request.scope)):
            return AccessDecision.DENY
    return AccessDecision.ALLOW


class RequestStatus(StrEnum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class DataCategory(StrEnum):
    DELETABLE_OPTIONAL_DATA = "DELETABLE_OPTIONAL_DATA"
    RETENTION_REQUIRED_DATA = "RETENTION_REQUIRED_DATA"
    AUTHORITATIVE_INSTITUTIONAL_RECORD = "AUTHORITATIVE_INSTITUTIONAL_RECORD"
    AUDIT_REQUIRED_RECORD = "AUDIT_REQUIRED_RECORD"


@dataclass(frozen=True)
class RetentionRule:
    category: DataCategory
    purpose: Purpose
    period: str
    authority: str
    deletion_behavior: str
    version: str
    effective_at: datetime
    status: str = "UNVERIFIED_POLICY"


@dataclass(frozen=True)
class PrivacyRequest:
    request_id: str
    subject_id: str
    institution_id: str
    kind: str
    category: DataCategory
    reason: str
    source_reference: str | None
    requested_at: datetime
    status: RequestStatus = RequestStatus.OPEN
    retained_reason: str | None = None
    effective_at: datetime | None = None


@dataclass(frozen=True)
class PrivacyEvent:
    event_id: str
    event_type: str
    actor_id: str
    subject_id: str
    institution_id: str
    purpose: Purpose
    scope: str
    result: str
    at: datetime
    version: str = "P14_LOCAL_V1"
    provenance: str = "LOCAL_IN_MEMORY"


class StudyStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class ParticipationStatus(StrEnum):
    INVITED = "INVITED"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    WITHDRAWN = "WITHDRAWN"
    EXCLUDED = "EXCLUDED"


class MeasureKind(StrEnum):
    TASK_SUCCESS = "TASK_SUCCESS"
    TASK_COMPLETION_TIME = "TASK_COMPLETION_TIME"
    COMPREHENSION = "COMPREHENSION"
    TRUST = "TRUST"
    WORKLOAD = "WORKLOAD"
    ACCESSIBILITY_FEEDBACK = "ACCESSIBILITY_FEEDBACK"
    USER_SATISFACTION = "USER_SATISFACTION"


@dataclass(frozen=True)
class StudyTask:
    task_id: str
    instruction_ar: str
    instruction_en: str
    expected_workflow: str
    version: str
    accessibility_note: str
    max_seconds: int = 1800


@dataclass(frozen=True)
class EvaluationStudy:
    study_id: str
    institution_id: str
    title_ar: str
    title_en: str
    description: str
    version: str
    status: StudyStatus
    consent_version: str
    eligible_subjects: frozenset[str]
    tasks: tuple[StudyTask, ...]
    allowed_measures: frozenset[MeasureKind]
    starts_at: datetime
    ends_at: datetime
    provenance: str = "SYNTHETIC_STUDY_NO_REAL_PARTICIPANTS"
    local_approval_reference: str | None = None
    local_approval_verified: bool = False

    def active(self, now: datetime) -> bool:
        return bool(self.status is StudyStatus.ACTIVE and self.local_approval_verified
                    and self.local_approval_reference and self.starts_at <= now < self.ends_at)


@dataclass(frozen=True)
class Participation:
    study_id: str
    subject_id: str
    institution_id: str
    pseudonym: str
    status: ParticipationStatus
    consent_id: str


@dataclass(frozen=True)
class Measure:
    study_id: str
    institution_id: str
    task_id: str
    pseudonym: str
    kind: MeasureKind
    value: int
    recorded_at: datetime
    consent_id: str
    accessibility_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Feedback:
    feedback_id: str
    study_id: str
    subject_id: str
    institution_id: str
    clarity: int
    usefulness: int
    understanding: int
    workload: int
    accessibility_issue: bool
    comment: str | None
    submitted_at: datetime


def aggregate_measures(study: EvaluationStudy, rows: tuple[Measure, ...],
                       eligible_pseudonyms: frozenset[str], privacy: PrivacyConfiguration,
                       query_budget: int) -> dict:
    """Aggregate-only, single bounded query; not a repeated-query defense."""
    if query_budget < 1:
        return {"status": "QUERY_BUDGET_EXHAUSTED", "metrics": {}}
    scoped = tuple(row for row in rows if row.study_id == study.study_id
                   and row.institution_id == study.institution_id
                   and row.pseudonym in eligible_pseudonyms
                   and row.kind in study.allowed_measures
                   and any(task.task_id == row.task_id for task in study.tasks))
    owners = {row.pseudonym for row in scoped}
    if should_suppress(len(owners), privacy) or len(owners) == 0:
        return {"status": "SUPPRESSED", "metrics": {}}
    result = {}
    for kind in sorted(study.allowed_measures, key=lambda item: item.value):
        values = [row.value for row in scoped if row.kind is kind]
        if values and len({row.pseudonym for row in scoped if row.kind is kind}) >= privacy.minimum_disclosure_group_size:
            result[kind.value] = {"count": len(values), "median": median(values)}
    return {"status": "AGGREGATE_ONLY", "metrics": result,
            "limitation": "SUPPRESSION_AND_BUDGET_DO_NOT_PREVENT_ALL_DIFFERENCING"}


class PilotStatus(StrEnum):
    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class PilotGovernance:
    pilot_id: str
    institution_id: str
    sponsor: str
    approval_reference: str | None
    approved_population: frozenset[str]
    consent_version: str
    starts_at: datetime
    ends_at: datetime
    capabilities: frozenset[str]
    provider_versions: Mapping[str, str]
    support_contact: str | None
    incident_procedure: str | None
    exit_plan: str | None
    monitoring_requirements: str | None
    data_policy_reference: str | None
    status: PilotStatus = PilotStatus.DRAFT
    approval_verified: bool = False

    def __post_init__(self) -> None:
        if self.status is PilotStatus.ACTIVE:
            raise ValueError("Global pilot activation is unavailable in the local model")

    def may_activate(self, now: datetime, subject_id: str, institution_id: str,
                     consent: Consent | None) -> bool:
        return bool(self.status is PilotStatus.APPROVED and self.approval_verified
                    and self.approval_reference
                    and self.institution_id == institution_id and subject_id in self.approved_population
                    and self.starts_at <= now < self.ends_at and self.capabilities
                    and self.support_contact and self.incident_procedure and self.exit_plan
                    and self.monitoring_requirements and self.data_policy_reference
                    and consent and consent.consent_version == self.consent_version
                    and consent.purpose is Purpose.PILOT_OPERATIONS
                    and consent.active(now, "pilot_participation"))

    def activate_for(self, now: datetime, subject_id: str, institution_id: str,
                     consent: Consent | None) -> PilotEnrollment:
        if not self.may_activate(now, subject_id, institution_id, consent):
            raise ValueError("PILOT_ACTIVATION_DENIED")
        return PilotEnrollment(self.pilot_id, institution_id, subject_id,
                               self.capabilities, dict(self.provider_versions),
                               consent.consent_id, now)


@dataclass(frozen=True)
class PilotEnrollment:
    pilot_id: str
    institution_id: str
    subject_id: str
    capabilities: frozenset[str]
    provider_versions: Mapping[str, str]
    consent_id: str
    activated_at: datetime
    status: str = "ACTIVE"
    ended_at: datetime | None = None

    def stop(self, now: datetime, status: str = "ENDED") -> PilotEnrollment:
        if status not in {"PAUSED", "ENDED", "CANCELLED"}:
            raise ValueError("Invalid pilot exit state")
        return replace(self, status=status, ended_at=now)

    def allows(self, capability: str, institution_id: str, now: datetime,
               consent: Consent | None) -> bool:
        return bool(self.status == "ACTIVE" and self.institution_id == institution_id
                    and capability in self.capabilities and consent
                    and consent.consent_id == self.consent_id
                    and consent.active(now, "pilot_participation"))


@dataclass(frozen=True)
class PilotIncident:
    incident_id: str
    pilot_id: str
    kind: str
    severity: str
    detected_at: datetime
    status: str
    summary_code: str
    response_owner: str
    resolution_code: str | None
    follow_up_required: bool

    def __post_init__(self) -> None:
        if self.kind not in {"PRIVACY_EVENT", "INCORRECT_DATA_SOURCE", "PROVIDER_FAILURE",
                             "ACCESS_CONTROL_EVENT", "MISLEADING_OUTPUT", "SERVICE_OUTAGE"} or \
           self.severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} or \
           self.status not in {"OPEN", "INVESTIGATING", "RESOLVED", "CLOSED"} or \
           not self.incident_id or not self.pilot_id or not self.response_owner or \
           not self.summary_code or len(self.summary_code) > 80:
            raise ValueError("Invalid bounded pilot incident")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
