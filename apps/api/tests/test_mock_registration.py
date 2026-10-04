"""P6.2 pure Mock Registration and Institutional Demand contract tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from time import perf_counter

import pytest

from app.academic_digital_twin.models import AuthoritativeAcademicSnapshot, AuthoritativeAttempt, PlanIdentity
from app.degree_path.models import DegreePathConstraints
from app.mock_registration.aggregation import aggregate_institutional_demand
from app.mock_registration.fingerprint import calculate_intent_fingerprint
from app.mock_registration.models import (
    AggregationLimits,
    AggregationScope,
    CapacityFact,
    CoverageInput,
    DemandAggregationError,
    DemandAggregationInput,
    DemandStatus,
    FactProvenance,
    IntentLifecycle,
    IntentProvenance,
    MockRegistrationContext,
    OfferingFact,
    PlanCourseFact,
    PrivacyConfiguration,
    RegistrationIntent,
    ResolutionDisposition,
    TargetPeriod,
    TargetPeriodClass,
    ValidationStatus,
)
from app.mock_registration.registries import DataQualityFlag, DemandMetricId, ReasonCode
from app.mock_registration.resolution import resolve_current_intents
from app.mock_registration.validation import validate_registration_intent
from app.mock_registration.replay_artifact import (
    P6ReplayArtifactError, P6ReplayArtifactV1, create_p6_replay_artifact,
    execute_p6_replay, reconstruct_p6_inputs, verify_p6_replay_artifact,
)
from app.planner.models import PlannerConstraints
from app.progress.engine import calculate_academic_progress
from app.progress.models import (
    AcademicProgressCatalog,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.rules.models import (
    AttemptOutcome,
    CanTakeCatalog,
    CourseCatalogStatus,
    CourseIdentity,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
    StudentCourseAttempt,
)

UNIVERSITY = "synthetic-university-a"
MAJOR = "synthetic-major"
PLAN = "synthetic-plan-v1"
VERSION = "2026-v1"
PERIOD = TargetPeriod(
    UNIVERSITY, "synthetic-2027-spring", TargetPeriodClass.SYNTHETIC_SANDBOX_PERIOD,
    "synthetic-periods:v1",
)


def _group(group_id, kind, credits, order):
    return ProgressRequirementGroup(
        group_id, PLAN, group_id.upper(), f"Arabic {group_id}", group_id,
        "major", kind, Decimal(credits), order,
    )


def _course(code, group, credits="3", order=1):
    return ProgressPlanCourse(f"pc-{code}", PLAN, group, code, CourseCatalogStatus.KNOWN, Decimal(credits), order)


def _rule(code, prerequisite=None, conflict=False):
    if conflict:
        status = PrerequisiteLogicStatus.SOURCE_CONFLICT
        groups = ()
    elif prerequisite:
        status = PrerequisiteLogicStatus.VERIFIED
        groups = (DependencyGroup(1, DependencyType.PREREQUISITE, (prerequisite,)),)
    else:
        status = PrerequisiteLogicStatus.NOT_APPLICABLE
        groups = ()
    return PlanCourseRule(code, status, groups)


def _snapshot(owner="opaque-owner-1", attempts=(), conflict=False, university=UNIVERSITY, plan=PLAN):
    groups = (
        _group("required", RequirementType.REQUIRED, "6", 1),
        _group("zero", RequirementType.REQUIRED, "0", 2),
        _group("elective", RequirementType.ELECTIVE, "3", 3),
    )
    courses = (
        _course("A", "required", order=1), _course("B", "required", order=2),
        _course("Z", "zero", "0", 3), _course("E1", "elective", order=4),
        _course("E2", "elective", order=5),
    )
    progress_catalog = AcademicProgressCatalog(ProgressStudyPlan(PLAN, Decimal("9")), groups, courses)
    eligibility_catalog = CanTakeCatalog(
        PLAN,
        (_rule("A"), _rule("B", "A", conflict), _rule("Z"), _rule("E1"), _rule("E2")),
        tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in ("A", "B", "Z", "E1", "E2"))
        + (CourseIdentity("REF", CourseCatalogStatus.REFERENCED_ONLY),),
    )
    auth_attempts = tuple(
        AuthoritativeAttempt(code, outcome, index + 1, "SYNTHETIC_VERIFIED", "VERIFIED")
        for index, (code, outcome) in enumerate(attempts)
    )
    engine_attempts = tuple(item.as_engine_attempt() for item in auth_attempts)
    current = calculate_academic_progress(progress_catalog, engine_attempts)
    return AuthoritativeAcademicSnapshot(
        owner, PlanIdentity(university, MAJOR, plan, VERSION), auth_attempts,
        eligibility_catalog, progress_catalog, current,
        PlannerConstraints(Decimal("6"), 2, 3), DegreePathConstraints(Decimal("6"), 2, 6, 2),
        ("synthetic-catalog:v1",), ("PHASE5:1.0", "PHASE6:1.0"),
    )


def _intent(owner="opaque-owner-1", courses=("A",), revision=1, lifecycle=IntentLifecycle.SUBMITTED,
            period=PERIOD, intent_id="intent-1", source=IntentProvenance.SYNTHETIC_SANDBOX_INTENT,
            plan=PLAN, version=VERSION, university=UNIVERSITY):
    return RegistrationIntent(
        intent_id, owner, university, MAJOR, plan, version, period, revision,
        lifecycle, tuple(courses), source, "synthetic-intents:v1",
    )


def _evaluate(intent=None, *, snapshot=None):
    intent = intent or _intent()
    snapshot = snapshot or _snapshot(owner=intent.owner_scope_id)
    return validate_registration_intent(intent, _context(snapshot, intent.target_period))


def _context(snapshot, period):
    identity = snapshot.plan_identity
    return MockRegistrationContext(
        snapshot.owner_scope_id,
        identity.university_id,
        identity.major_id,
        identity.study_plan_id,
        identity.plan_version,
        snapshot.eligibility_catalog,
        snapshot.progress_catalog,
        snapshot.current_progress,
        snapshot.engine_attempts,
        snapshot.source_versions,
        snapshot.engine_policy_versions,
        period,
    )


def _catalog(university=UNIVERSITY, plan=PLAN):
    return tuple(
        PlanCourseFact(university, MAJOR, plan, VERSION, code, group, Decimal(credits), "synthetic-catalog:v1")
        for code, group, credits in (
            ("A", "required", "3"), ("B", "required", "3"), ("Z", "zero", "0"),
            ("E1", "elective", "3"), ("E2", "elective", "3"),
        )
    )


def _resolved(*records):
    return resolve_current_intents(tuple(records)).records


def _request(records, *, threshold=2, denominator=None, complete=False, offerings=None,
             capacities=None, review=False, scope=None, catalog=None, period=PERIOD, max_intents=1000):
    return DemandAggregationInput(
        scope or AggregationScope(UNIVERSITY), period, tuple(records), catalog or _catalog(),
        PrivacyConfiguration(threshold, "synthetic-privacy:v1"),
        AggregationLimits(max_intents, 1000), CoverageInput(denominator, complete),
        offerings, capacities, review, ("synthetic-input:v1",),
    )


def _metric(result, metric_id, course=None):
    return next(item for item in result.metrics if item.metric_id is metric_id and item.course_code == course)


def test_exact_contract_registries_are_locked():
    assert len(ReasonCode) == 30
    assert len(DemandMetricId) == 9
    assert len(DemandStatus) == 4
    assert len(DataQualityFlag) == 7
    assert len(IntentLifecycle) == 3
    assert len(TargetPeriodClass) == 3
    assert len(IntentProvenance) == 3
    assert len(FactProvenance) == 3


@pytest.mark.parametrize("courses", [("A",), ("E1",), ("Z",), ("A", "E1")])
def test_valid_required_elective_zero_credit_and_multi_course(courses):
    result = _evaluate(_intent(courses=courses))
    assert result.status is ValidationStatus.VALID
    assert result.canonical_course_codes == tuple(sorted(courses))
    assert result.declared_credit_load == sum((item.credit_hours for item in result.course_results), Decimal("0"))
    assert all(item.phase5_decision is not None for item in result.course_results)


@pytest.mark.parametrize(
    ("attempt", "code"),
    [(("A", AttemptOutcome.PASSED), ReasonCode.MOCK_REG_TARGET_ALREADY_COMPLETED),
     (("A", AttemptOutcome.IN_PROGRESS), ReasonCode.MOCK_REG_TARGET_IN_PROGRESS)],
)
def test_completed_and_in_progress_are_conservatively_invalid(attempt, code):
    result = _evaluate(snapshot=_snapshot(attempts=(attempt,)))
    assert result.status is ValidationStatus.INVALID
    assert code in result.reason_codes


@pytest.mark.parametrize("outcome", [AttemptOutcome.FAILED, AttemptOutcome.WITHDRAWN])
def test_failed_and_withdrawn_history_defer_to_current_phase5(outcome):
    assert _evaluate(snapshot=_snapshot(attempts=(("A", outcome),))).status is ValidationStatus.VALID


def test_phase5_not_eligible_and_review_required_are_not_flattened():
    blocked = _evaluate(_intent(courses=("B",)))
    assert blocked.status is ValidationStatus.INVALID
    assert ReasonCode.MOCK_REG_TARGET_NOT_ELIGIBLE in blocked.reason_codes
    review = _evaluate(_intent(courses=("B",)), snapshot=_snapshot(conflict=True))
    assert review.status is ValidationStatus.REVIEW_REQUIRED
    assert review.course_results[0].status is ValidationStatus.REVIEW_REQUIRED


def test_same_intent_courses_never_unlock_each_other_and_validation_is_atomic():
    chained = _evaluate(_intent(courses=("A", "B")))
    assert chained.status is ValidationStatus.INVALID
    assert next(item for item in chained.course_results if item.course_code == "B").phase5_decision.value == "NOT_ELIGIBLE"
    mixed = _evaluate(_intent(courses=("A", "UNKNOWN")))
    assert mixed.status is ValidationStatus.INVALID
    assert any(item.status is ValidationStatus.VALID for item in mixed.course_results)
    review_and_valid = _evaluate(_intent(courses=("A", "B")), snapshot=_snapshot(conflict=True))
    assert review_and_valid.status is ValidationStatus.REVIEW_REQUIRED
    invalid_precedence = _evaluate(
        _intent(courses=("A", "B")),
        snapshot=_snapshot(attempts=(("A", AttemptOutcome.PASSED),), conflict=True),
    )
    assert invalid_precedence.status is ValidationStatus.INVALID


@pytest.mark.parametrize(
    ("courses", "code"),
    [(('UNKNOWN',), ReasonCode.MOCK_REG_UNKNOWN_COURSE),
     (('REF',), ReasonCode.MOCK_REG_TARGET_NOT_PLAN_MEMBER),
     (('A', 'A'), ReasonCode.MOCK_REG_DUPLICATE_COURSE),
     ((), ReasonCode.MOCK_REG_EMPTY_COURSE_SET)],
)
def test_course_identity_duplicate_and_empty_validation(courses, code):
    result = _evaluate(_intent(courses=courses))
    assert result.status is ValidationStatus.INVALID
    assert code in result.reason_codes


def test_satisfied_elective_group_uses_mock_registration_specific_code():
    result = _evaluate(_intent(courses=("E2",)), snapshot=_snapshot(attempts=(("E1", AttemptOutcome.PASSED),)))
    assert result.status is ValidationStatus.INVALID
    assert result.reason_codes == (ReasonCode.MOCK_REG_ELECTIVE_GROUP_ALREADY_SATISFIED,)


def test_intent_bounds_are_atomic_and_not_clamped():
    many = _evaluate(_intent(courses=tuple(f"X{i}" for i in range(11))))
    assert ReasonCode.MOCK_REG_COURSE_LIMIT_EXCEEDED in many.reason_codes
    heavy_snapshot = _snapshot()
    heavy_courses = tuple(replace(item, credit_hours=Decimal("31")) if item.course_code == "A" else item for item in heavy_snapshot.progress_catalog.plan_courses)
    progress_catalog = replace(heavy_snapshot.progress_catalog, plan_courses=heavy_courses)
    heavy_snapshot = replace(heavy_snapshot, progress_catalog=progress_catalog, current_progress=calculate_academic_progress(progress_catalog, ()))
    heavy = _evaluate(snapshot=heavy_snapshot)
    assert ReasonCode.MOCK_REG_CREDIT_LIMIT_EXCEEDED in heavy.reason_codes
    assert heavy.declared_credit_load == Decimal("31")


def test_period_plan_revision_and_lifecycle_validation():
    invalid_period = replace(PERIOD, period_key="")
    cases = (
        (_intent(revision=0), ReasonCode.MOCK_REG_INVALID_REVISION),
        (_intent(version="wrong"), ReasonCode.MOCK_REG_INVALID_PLAN_VERSION),
        (_intent(plan="wrong"), ReasonCode.MOCK_REG_INVALID_PLAN_IDENTITY),
        (_intent(period=invalid_period), ReasonCode.MOCK_REG_INVALID_TARGET_PERIOD),
        (_intent(lifecycle=IntentLifecycle.WITHDRAWN), ReasonCode.MOCK_REG_INVALID_LIFECYCLE),
    )
    for intent, code in cases:
        context_period = PERIOD if intent.target_period != invalid_period else invalid_period
        snapshot = _snapshot(owner=intent.owner_scope_id)
        result = validate_registration_intent(intent, _context(snapshot, context_period))
        assert code in result.reason_codes


def test_all_period_classes_require_exact_provenance_semantics():
    declared = TargetPeriod(UNIVERSITY, "declared-next", TargetPeriodClass.DECLARED_PLANNING_PERIOD, "declared:v1")
    official = TargetPeriod(UNIVERSITY, "official-2027", TargetPeriodClass.OFFICIAL_PERIOD_REFERENCE, "provider:v1", True)
    unverified_official = replace(official, verified_provider_source=False)
    for period in (declared, PERIOD, official):
        result = _evaluate(_intent(period=period))
        assert result.status is ValidationStatus.VALID
    result = _evaluate(_intent(period=unverified_official))
    assert ReasonCode.MOCK_REG_INVALID_TARGET_PERIOD in result.reason_codes


def test_withdrawal_and_expiry_are_explicit_and_do_not_use_time():
    submitted = _evaluate(_intent(revision=1))
    withdrawn = _evaluate(_intent(courses=(), revision=2, lifecycle=IntentLifecycle.WITHDRAWN, intent_id="withdraw"))
    expired = _evaluate(_intent(revision=3, lifecycle=IntentLifecycle.EXPIRED, intent_id="expired"))
    withdrawal_resolution = resolve_current_intents((submitted, withdrawn))
    assert any(item.disposition is ResolutionDisposition.WITHDRAWN for item in withdrawal_resolution.records)
    expiry_resolution = resolve_current_intents((expired,))
    assert expiry_resolution.records[0].disposition is ResolutionDisposition.EXPIRED


def test_fingerprint_is_canonical_private_and_decision_sensitive():
    left = _intent(courses=("E1", "A"))
    reordered = replace(left, course_codes=("A", "E1"), intent_id="another", owner_scope_id="another-owner")
    assert calculate_intent_fingerprint(left) == calculate_intent_fingerprint(reordered)
    assert calculate_intent_fingerprint(left) != calculate_intent_fingerprint(replace(left, course_codes=("A",)))
    assert calculate_intent_fingerprint(left) != calculate_intent_fingerprint(replace(left, study_plan_version="v2"))
    assert calculate_intent_fingerprint(left) != calculate_intent_fingerprint(replace(left, target_period=replace(PERIOD, period_key="other")))
    assert not {"name", "email", "phone", "grade", "attempts", "conversation", "scenario"} & {item.name for item in fields(RegistrationIntent)}


def test_latest_revision_idempotency_conflict_and_row_order_determinism():
    first = _evaluate(_intent(revision=1))
    second = _evaluate(_intent(revision=2, intent_id="second"))
    duplicate = replace(second, intent=replace(second.intent, intent_id="duplicate"))
    resolved = resolve_current_intents((duplicate, first, second))
    assert sum(item.disposition is ResolutionDisposition.CURRENT for item in resolved.records) == 1
    assert sum(item.disposition is ResolutionDisposition.SUPERSEDED for item in resolved.records) == 2
    changed = _evaluate(_intent(courses=("E1",), revision=2, intent_id="changed"))
    conflict = resolve_current_intents((second, changed))
    assert all(item.disposition is ResolutionDisposition.REVISION_CONFLICT for item in conflict.records)
    assert conflict == resolve_current_intents(tuple(reversed((second, changed))))


def test_aggregate_counts_owners_selections_credits_groups_plans_and_shares():
    one = _evaluate(_intent(owner="owner-1", courses=("A", "Z"), intent_id="one"), snapshot=_snapshot("owner-1"))
    two = _evaluate(_intent(owner="owner-2", courses=("A", "Z"), intent_id="two"), snapshot=_snapshot("owner-2"))
    result = aggregate_institutional_demand(_request(_resolved(one, two), threshold=2, denominator=2, complete=True))
    assert result.status is DemandStatus.AVAILABLE
    assert _metric(result, DemandMetricId.VALID_ACTIVE_INTENT_OWNER_COUNT).value == 2
    assert _metric(result, DemandMetricId.COURSE_INTENT_OWNER_COUNT, "A").value == 2
    assert _metric(result, DemandMetricId.COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS, "A").value == Decimal("1")
    assert _metric(result, DemandMetricId.TOTAL_DECLARED_COURSE_SELECTION_COUNT).value == 4
    assert _metric(result, DemandMetricId.TOTAL_DECLARED_CREDIT_LOAD).value == Decimal("6")
    assert sum(item.metric_id is DemandMetricId.REQUIREMENT_GROUP_INTENT_OWNER_COUNT for item in result.metrics) == 2


def test_review_invalid_withdrawn_expired_and_conflicted_records_do_not_enter_valid_demand():
    valid = _evaluate(_intent(owner="owner-1"), snapshot=_snapshot("owner-1"))
    valid2 = _evaluate(_intent(owner="owner-2", intent_id="valid-2"), snapshot=_snapshot("owner-2"))
    invalid = _evaluate(_intent(owner="owner-3", courses=("UNKNOWN",)), snapshot=_snapshot("owner-3"))
    review = _evaluate(_intent(owner="owner-4", courses=("B",)), snapshot=_snapshot("owner-4", conflict=True))
    review2 = _evaluate(_intent(owner="owner-5", courses=("B",), intent_id="review-2"), snapshot=_snapshot("owner-5", conflict=True))
    withdrawn = _evaluate(_intent(owner="owner-6", courses=(), lifecycle=IntentLifecycle.WITHDRAWN), snapshot=_snapshot("owner-6"))
    expired = _evaluate(_intent(owner="owner-7", lifecycle=IntentLifecycle.EXPIRED), snapshot=_snapshot("owner-7"))
    records = _resolved(valid, valid2, invalid, review, review2, withdrawn, expired)
    result = aggregate_institutional_demand(_request(records, threshold=2, review=True))
    assert result.status is DemandStatus.AVAILABLE or result.status is DemandStatus.PARTIAL
    assert _metric(result, DemandMetricId.VALID_ACTIVE_INTENT_OWNER_COUNT).value == 2
    assert _metric(result, DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT).value == 2
    assert DataQualityFlag.REVIEW_REQUIRED_INTENTS_EXCLUDED in result.quality_flags


def test_review_metric_must_be_explicitly_enabled():
    review = _evaluate(_intent(courses=("B",)), snapshot=_snapshot(conflict=True))
    disabled = aggregate_institutional_demand(_request(_resolved(review), threshold=2, review=False))
    assert disabled.status is DemandStatus.INSUFFICIENT_DATA
    assert DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT not in {item.metric_id for item in disabled.metrics}


def test_privacy_suppression_withholds_every_value_and_identity():
    record = _evaluate()
    result = aggregate_institutional_demand(_request(_resolved(record), threshold=3))
    assert result.status is DemandStatus.SUPPRESSED
    assert result.metrics == ()
    assert result.coverage.valid_active_intent_owner_count is None
    assert result.coverage.population_denominator is None
    assert set(result.suppressed_metric_ids) == set(DemandMetricId)
    result_field_names = {item.name for item in fields(type(result))}
    assert not {"owner_id", "student_id", "student_name", "email", "grade", "attempts", "conversation", "scenario"} & result_field_names


def test_empty_demand_is_insufficient_not_zero():
    result = aggregate_institutional_demand(_request((), threshold=2))
    assert result.status is DemandStatus.INSUFFICIENT_DATA
    assert result.metrics == ()
    assert result.reason_codes == (ReasonCode.DEMAND_NO_VALID_ACTIVE_INTENTS,)


def test_coverage_unknown_known_and_partial_are_explicit():
    records = []
    for index in range(3):
        owner = f"owner-{index}"
        records.append(_evaluate(_intent(owner=owner, intent_id=f"i-{index}"), snapshot=_snapshot(owner)))
    resolved = _resolved(*records)
    unknown = aggregate_institutional_demand(_request(resolved, threshold=2))
    assert unknown.coverage.observed_intents_only
    assert unknown.coverage.population_coverage_ratio is None
    partial = aggregate_institutional_demand(_request(resolved, threshold=2, denominator=6))
    assert partial.status is DemandStatus.PARTIAL
    assert partial.coverage.population_coverage_ratio == Decimal("0.5")


def test_optional_offering_and_capacity_are_exact_facts_with_arithmetic_only():
    records = []
    for index in range(3):
        owner = f"owner-{index}"
        records.append(_evaluate(_intent(owner=owner, intent_id=f"i-{index}"), snapshot=_snapshot(owner)))
    offering = OfferingFact(UNIVERSITY, PERIOD, "A", "synthetic-offerings:v1", FactProvenance.SYNTHETIC_SANDBOX_FACT)
    for capacity, expected in ((1, 2), (3, 0), (5, -2)):
        fact = CapacityFact(UNIVERSITY, PERIOD, "A", capacity, "synthetic-capacity:v1", FactProvenance.SYNTHETIC_SANDBOX_FACT)
        result = aggregate_institutional_demand(_request(_resolved(*records), threshold=2, offerings=(offering,), capacities=(fact,)))
        assert _metric(result, DemandMetricId.DECLARED_DEMAND_MINUS_CAPACITY, "A").value == expected
        assert not hasattr(result, "section_estimate") and not hasattr(result, "bottleneck_rank")
    unavailable = aggregate_institutional_demand(_request(_resolved(*records), threshold=2))
    assert DemandMetricId.DECLARED_DEMAND_MINUS_CAPACITY not in {item.metric_id for item in unavailable.metrics}


def test_offering_dataset_absence_is_distinct_from_no_match():
    records = []
    for index in range(2):
        owner = f"owner-{index}"
        records.append(_evaluate(_intent(owner=owner, intent_id=f"i-{index}"), snapshot=_snapshot(owner)))
    missing = aggregate_institutional_demand(_request(_resolved(*records), threshold=2))
    supplied = aggregate_institutional_demand(_request(_resolved(*records), threshold=2, offerings=()))
    assert DataQualityFlag.MISSING_OFFERING_DATA in missing.quality_flags
    assert _metric(supplied, DemandMetricId.COURSE_INTENT_OWNER_COUNT, "A").offering_state.value == "NO_MATCHING_OFFERING_FACT"


def test_scope_period_university_and_limits_are_hard_rejections():
    record = _evaluate()
    with pytest.raises(DemandAggregationError) as limit:
        aggregate_institutional_demand(_request(_resolved(record), max_intents=0))
    assert limit.value.code is ReasonCode.DEMAND_LIMIT_EXCEEDED
    other_period = replace(PERIOD, period_key="other")
    with pytest.raises(DemandAggregationError) as mismatch:
        aggregate_institutional_demand(_request(_resolved(record), period=other_period))
    assert mismatch.value.code is ReasonCode.DEMAND_SCOPE_MISMATCH
    foreign_period = replace(PERIOD, university_id="synthetic-university-b")
    foreign_intent = replace(record.intent, university_id="synthetic-university-b", target_period=foreign_period)
    foreign = replace(record, intent=foreign_intent, content_fingerprint=calculate_intent_fingerprint(foreign_intent))
    with pytest.raises(DemandAggregationError) as university_mismatch:
        aggregate_institutional_demand(_request(_resolved(foreign)))
    assert university_mismatch.value.code is ReasonCode.DEMAND_SCOPE_MISMATCH
    wrong_offering = OfferingFact("synthetic-university-b", foreign_period, "A", "synthetic:v1", FactProvenance.SYNTHETIC_SANDBOX_FACT)
    with pytest.raises(DemandAggregationError):
        aggregate_institutional_demand(_request(_resolved(record), offerings=(wrong_offering,)))
    wrong_capacity = CapacityFact("synthetic-university-b", foreign_period, "A", 3, "synthetic:v1", FactProvenance.SYNTHETIC_SANDBOX_FACT)
    with pytest.raises(DemandAggregationError):
        aggregate_institutional_demand(_request(_resolved(record), capacities=(wrong_capacity,)))


def test_aggregation_input_order_does_not_change_output():
    records = []
    for index in range(3):
        owner = f"owner-{index}"
        records.append(_evaluate(_intent(owner=owner, courses=("E1", "A"), intent_id=f"i-{index}"), snapshot=_snapshot(owner)))
    forward = aggregate_institutional_demand(_request(_resolved(*records), threshold=2, catalog=_catalog()))
    reverse = aggregate_institutional_demand(_request(tuple(reversed(_resolved(*records))), threshold=2, catalog=tuple(reversed(_catalog()))))
    assert forward == reverse


def test_cross_plan_views_are_separate_and_global_course_deduplicates():
    records = []
    catalog = list(_catalog())
    second_plan = "synthetic-plan-v2"
    catalog.extend(replace(item, study_plan_id=second_plan, source_version="synthetic-catalog:v2") for item in _catalog())
    for plan in (PLAN, second_plan):
        for offset in range(2):
            owner = f"owner-{offset}"
            record = _evaluate(_intent(owner=owner, intent_id=f"i-{owner}"), snapshot=_snapshot(owner))
            if plan != PLAN:
                changed_intent = replace(record.intent, study_plan_id=plan)
                record = replace(
                    record,
                    intent=changed_intent,
                    content_fingerprint=calculate_intent_fingerprint(changed_intent),
                )
            records.append(record)
    result = aggregate_institutional_demand(_request(_resolved(*records), threshold=2, catalog=tuple(catalog)))
    course_metrics = tuple(item for item in result.metrics if item.metric_id is DemandMetricId.COURSE_INTENT_OWNER_COUNT and item.course_code == "A")
    assert next(item for item in course_metrics if item.study_plan_id is None).value == 2
    assert {item.value for item in course_metrics if item.study_plan_id is not None} == {2}
    shares = tuple(item for item in result.metrics if item.metric_id is DemandMetricId.COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS and item.course_code == "A")
    assert all(item.value == Decimal("1") for item in shares)


def test_inputs_and_prior_engine_state_are_not_mutated_and_no_conversion_exists():
    snapshot = _snapshot()
    original = deepcopy(snapshot)
    result = _evaluate(snapshot=snapshot)
    assert snapshot == original
    assert result.intent.course_codes == ("A",)
    package = Path(__file__).parents[1] / "app" / "mock_registration"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    for forbidden in ("fastapi", "supabase", "httpx", "sqlalchemy", "openai", "register_course", "reserve_seat"):
        assert forbidden not in source.lower()
    assert "academic_digital_twin" not in source
    assert "app.recommendations" not in source.lower()
    assert "app.planner" not in source.lower()


def test_second_synthetic_plan_and_university_are_provider_neutral():
    assert "zarqa" not in "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path(__file__).parents[1] / "app" / "mock_registration").glob("*.py")
    ).lower()
    assert AggregationScope("synthetic-university-b", study_plan_id="other-plan").university_id != UNIVERSITY


def test_representative_performance_is_bounded():
    codes = tuple(f"C{index:02d}" for index in range(10))
    group = ProgressRequirementGroup("ten", PLAN, "TEN", "Arabic ten", "ten", "major", RequirementType.REQUIRED, Decimal("30"), 1)
    courses = tuple(_course(code, "ten", order=index + 1) for index, code in enumerate(codes))
    progress_catalog = AcademicProgressCatalog(ProgressStudyPlan(PLAN, Decimal("30")), (group,), courses)
    eligibility_catalog = CanTakeCatalog(
        PLAN, tuple(_rule(code) for code in codes),
        tuple(CourseIdentity(code, CourseCatalogStatus.KNOWN) for code in codes),
    )
    ten_snapshot = replace(
        _snapshot(), eligibility_catalog=eligibility_catalog, progress_catalog=progress_catalog,
        current_progress=calculate_academic_progress(progress_catalog, ()),
    )
    ten = _intent(courses=codes)
    started = perf_counter()
    ten_result = _evaluate(ten, snapshot=ten_snapshot)
    validation_seconds = perf_counter() - started
    assert ten_result.status is ValidationStatus.VALID
    base = _evaluate()
    hundred = tuple(replace(base, intent=replace(base.intent, owner_scope_id=f"owner-{i}", intent_id=f"i-{i}")) for i in range(100))
    started = perf_counter()
    resolution = resolve_current_intents(hundred)
    resolution_seconds = perf_counter() - started
    assert len(resolution.current) == 100
    five_hundred = tuple(replace(base, intent=replace(base.intent, owner_scope_id=f"large-owner-{i}", intent_id=f"large-{i}")) for i in range(500))
    large_resolved = resolve_current_intents(five_hundred).records
    capacity = CapacityFact(UNIVERSITY, PERIOD, "A", 450, "synthetic-capacity:v1", FactProvenance.SYNTHETIC_SANDBOX_FACT)
    started = perf_counter()
    aggregate = aggregate_institutional_demand(_request(large_resolved, threshold=3, capacities=(capacity,), max_intents=1000))
    aggregate_seconds = perf_counter() - started
    started = perf_counter()
    suppressed = aggregate_institutional_demand(_request(_resolved(base), threshold=3))
    suppression_seconds = perf_counter() - started
    assert aggregate.status in (DemandStatus.AVAILABLE, DemandStatus.PARTIAL)
    assert _metric(aggregate, DemandMetricId.DECLARED_DEMAND_MINUS_CAPACITY, "A").value == 50
    assert suppressed.status is DemandStatus.SUPPRESSED
    assert max(validation_seconds, resolution_seconds, aggregate_seconds, suppression_seconds) < 2


SCENARIO_TEST_MAPPING = {
    **{f"P6-T{number:02d}": "functional validation/resolution/aggregation tests" for number in range(1, 65)}
}


def test_all_64_committed_scenarios_have_stable_ids_and_automated_mapping():
    matrix = (Path(__file__).parents[2] / ".." / "docs" / "mock-registration-demand-test-matrix.md").resolve()
    text = matrix.read_text(encoding="utf-8")
    assert len(SCENARIO_TEST_MAPPING) == 64
    assert text.count("| `P6-T") == 64
    assert all(f"`{item}`" in text for item in SCENARIO_TEST_MAPPING)


def _replay_fixture(*, conflict=False):
    intent = _intent(courses=(("B",) if conflict else ("A",)), intent_id="first-generated-id")
    original_context = _context(_snapshot(owner=intent.owner_scope_id, conflict=conflict), intent.target_period)
    result = validate_registration_intent(intent, original_context)
    artifact = create_p6_replay_artifact(intent, original_context, result)
    return intent, original_context, result, artifact


@pytest.mark.parametrize("conflict,expected", [(False, ValidationStatus.VALID),
                                                 (True, ValidationStatus.REVIEW_REQUIRED)])
def test_p6_exact_replay_runs_historical_validator_and_matches(conflict, expected, monkeypatch):
    from app.mock_registration import replay_artifact as module

    intent, context, result, artifact = _replay_fixture(conflict=conflict)
    assert result.status is expected
    payload = verify_p6_replay_artifact(artifact)
    reconstructed_intent, reconstructed_context = reconstruct_p6_inputs(
        payload, persisted_intent_id=intent.intent_id)
    assert reconstructed_intent == intent
    assert reconstructed_context.student_attempts == context.student_attempts
    assert reconstructed_context.eligibility_catalog.plan_courses[1].dependency_groups == (
        context.eligibility_catalog.plan_courses[1].dependency_groups)
    assert reconstructed_context.current_progress.courses[1].state == context.current_progress.courses[1].state
    called = []
    real = module.validate_registration_intent
    def observed(i, c):
        called.append(True)
        return real(i, c)
    monkeypatch.setattr(module, "validate_registration_intent", observed)
    replay = execute_p6_replay(artifact, persisted_intent_id=intent.intent_id,
        persisted_status=result.status,
        persisted_reasons=tuple(code.value for code in result.reason_codes),
        persisted_fingerprint=result.content_fingerprint,
        persisted_course_codes=result.canonical_course_codes)
    assert called == [True]
    assert replay.status == "MATCHED" and replay.matched
    assert replay.historical_reason_codes == replay.replayed_reason_codes
    assert replay.historical_content_fingerprint == replay.replayed_content_fingerprint


def test_p6_replay_artifact_canonical_hash_retry_and_tamper():
    intent, context, result, artifact = _replay_fixture()
    retry = create_p6_replay_artifact(replace(intent, intent_id="retry-generated-id"),
        context, replace(result, intent=replace(intent, intent_id="retry-generated-id")))
    assert retry.canonical_payload == artifact.canonical_payload
    assert retry.canonical_sha256 == artifact.canonical_sha256
    changed_context = replace(context, student_attempts=(StudentCourseAttempt("A", AttemptOutcome.PASSED),))
    changed_result = validate_registration_intent(intent, changed_context)
    changed = create_p6_replay_artifact(intent, changed_context, changed_result)
    assert changed.canonical_sha256 != artifact.canonical_sha256
    with pytest.raises(P6ReplayArtifactError, match="REPLAY_ARTIFACT_INTEGRITY_FAILURE"):
        verify_p6_replay_artifact(replace(artifact, canonical_payload=artifact.canonical_payload + " "))
    with pytest.raises(P6ReplayArtifactError, match="ENGINE_VERSION_UNAVAILABLE"):
        verify_p6_replay_artifact(replace(artifact, engine_version="2.0"))
    with pytest.raises(P6ReplayArtifactError):
        reconstruct_p6_inputs({"intent": {}, "context": {}}, persisted_intent_id=intent.intent_id)


def test_p6_replay_mismatch_is_audit_evidence_not_substitution():
    intent, _, result, artifact = _replay_fixture()
    replay = execute_p6_replay(artifact, persisted_intent_id=intent.intent_id,
        persisted_status=ValidationStatus.REVIEW_REQUIRED,
        persisted_reasons=tuple(code.value for code in result.reason_codes),
        persisted_fingerprint=result.content_fingerprint,
        persisted_course_codes=result.canonical_course_codes)
    assert replay.status == "MISMATCH" and not replay.matched


def test_p6_replay_rejects_malformed_historical_output_even_with_valid_hash():
    intent, _, result, artifact = _replay_fixture()
    payload = json.loads(artifact.canonical_payload)
    payload["historical_output"]["status"] = "NOT_A_VALID_STATUS"
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    malformed = replace(artifact, canonical_payload=canonical,
                        canonical_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest())
    with pytest.raises(P6ReplayArtifactError, match="REPLAY_ARTIFACT_MALFORMED"):
        execute_p6_replay(malformed, persisted_intent_id=intent.intent_id,
            persisted_status=result.status,
            persisted_reasons=tuple(code.value for code in result.reason_codes),
            persisted_fingerprint=result.content_fingerprint,
            persisted_course_codes=result.canonical_course_codes)
