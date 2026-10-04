"""Current-validity derivation without changing immutable history."""

from __future__ import annotations

from app.mock_registration.models import (
    IntentLifecycle, RegistrationIntent, TargetPeriod, ValidatedIntent, ValidationStatus,
)
from app.mock_registration.validation import validate_registration_intent
from app.mock_registration_persistence.models import PersistedIntentRevision, PersistedTargetPeriod

from .context import domain_context
from .models import AcademicContextSnapshot, CurrentValidity, RevalidationResult, RevalidationStatus


def domain_period(period: PersistedTargetPeriod) -> TargetPeriod:
    return TargetPeriod(str(period.university_id), period.period_key, period.period_class,
                        period.source_version, period.verified_provider_source)


def stored_domain_record(row: PersistedIntentRevision, period: PersistedTargetPeriod) -> ValidatedIntent:
    intent = RegistrationIntent(
        str(row.intent_id), str(row.owner_user_id), str(row.university_id), str(row.major_id),
        str(row.study_plan_id), row.study_plan_version, domain_period(period), row.revision,
        row.lifecycle_status, tuple(item.course_code for item in row.courses),
        row.intent_provenance, row.intent_source_version, row.p6_contract_version,
    )
    return ValidatedIntent(intent, tuple(item.course_code for item in row.courses),
        row.content_fingerprint, row.validation_status, row.validation_reason_codes, (),
        0, (), ("Submission-time evidence; current validity is derived separately.",))


def revalidate(row: PersistedIntentRevision, period: PersistedTargetPeriod,
               snapshot: AcademicContextSnapshot | None) -> RevalidationResult:
    if period.is_expired:
        return RevalidationResult(CurrentValidity.EXPIRED, RevalidationStatus.COMPLETE, None, ())
    if snapshot is None or row.study_plan_id != snapshot.study_plan_id or row.study_plan_version != snapshot.study_plan_version:
        return RevalidationResult(CurrentValidity.STALE_REQUIRES_REVALIDATION,
                                  RevalidationStatus.INCOMPLETE, None, ())
    if row.lifecycle_status is IntentLifecycle.WITHDRAWN:
        return RevalidationResult(CurrentValidity.CURRENT_INVALID, RevalidationStatus.COMPLETE, None, ())
    intent = RegistrationIntent(
        str(row.intent_id), str(row.owner_user_id), str(row.university_id), str(row.major_id),
        str(row.study_plan_id), row.study_plan_version, domain_period(period), row.revision,
        row.lifecycle_status, tuple(item.course_code for item in row.courses),
        row.intent_provenance, row.intent_source_version, row.p6_contract_version,
    )
    validated = validate_registration_intent(intent, domain_context(snapshot, domain_period(period)))
    validity = {
        ValidationStatus.VALID: CurrentValidity.CURRENT_VALID,
        ValidationStatus.INVALID: CurrentValidity.CURRENT_INVALID,
        ValidationStatus.REVIEW_REQUIRED: CurrentValidity.REVIEW_REQUIRED,
    }[validated.status]
    return RevalidationResult(validity, RevalidationStatus.COMPLETE, validated, validated.reason_codes)

