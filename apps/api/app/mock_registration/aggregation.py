"""Privacy-preserving descriptive aggregation over resolved current intents."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .capacity import capacity_match, offering_match
from .models import (
    CapacityState,
    CoverageMetadata,
    DemandAggregationError,
    DemandAggregationInput,
    DemandAggregationResult,
    DemandMetric,
    DemandStatus,
    FactProvenance,
    IntentLifecycle,
    IntentProvenance,
    ResolutionDisposition,
    ValidationStatus,
)
from .privacy import should_suppress, validate_privacy_configuration
from .registries import DataQualityFlag, DemandMetricId, METRIC_REGISTRY, ReasonCode

ZERO = Decimal("0")


def aggregate_institutional_demand(request: DemandAggregationInput) -> DemandAggregationResult:
    _validate_input(request)
    current = tuple(
        item.record for item in request.resolved_intents
        if item.disposition is ResolutionDisposition.CURRENT
        and _in_scope(item.record, request)
    )
    valid = tuple(
        item for item in current
        if item.status is ValidationStatus.VALID
        and item.intent.lifecycle_status is IntentLifecycle.SUBMITTED
    )
    review = tuple(item for item in current if item.status is ValidationStatus.REVIEW_REQUIRED)
    valid_owners = {item.intent.owner_scope_id for item in valid}
    review_owners = {item.intent.owner_scope_id for item in review} if request.include_review_metric else set()
    contributing = valid_owners | review_owners

    provenance = tuple(sorted({item.intent.source_class for item in (*valid, *review)}, key=lambda item: item.value))
    sources = tuple(sorted(set(request.source_versions) | {
        item.intent.source_version for item in (*valid, *review)
    }))
    if not contributing:
        return _empty_result(request, provenance, sources)
    disclosure_populations = _disclosure_populations(request, valid, review_owners)
    if any(
        should_suppress(population, request.privacy_configuration)
        for population in disclosure_populations
    ):
        return _suppressed_result(request, provenance, sources)

    flags: set[DataQualityFlag] = set()
    reasons: set[ReasonCode] = set()
    if request.coverage.complete_declared_intent_input_set:
        flags.add(DataQualityFlag.COMPLETE_DECLARED_INTENT_INPUT_SET)
    denominator = request.coverage.population_denominator
    coverage_ratio = None
    observed_only = denominator is None
    if denominator is None:
        flags.add(DataQualityFlag.UNKNOWN_POPULATION_COVERAGE)
        reasons.add(ReasonCode.DEMAND_UNKNOWN_POPULATION_COVERAGE)
    elif denominator < len(valid_owners):
        raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "population denominator is smaller than observed valid owners")
    elif denominator > len(valid_owners):
        flags.add(DataQualityFlag.PARTIAL_INTENT_COVERAGE)
        reasons.add(ReasonCode.DEMAND_PARTIAL_INTENT_COVERAGE)
        coverage_ratio = Decimal(len(valid_owners)) / Decimal(denominator) if denominator else None
    elif denominator:
        coverage_ratio = Decimal("1")
    if review:
        flags.add(DataQualityFlag.REVIEW_REQUIRED_INTENTS_EXCLUDED)
        reasons.add(ReasonCode.DEMAND_REVIEW_INTENTS_EXCLUDED)
    if request.offering_facts is None:
        flags.add(DataQualityFlag.MISSING_OFFERING_DATA)
        reasons.add(ReasonCode.DEMAND_OFFERING_DATA_UNAVAILABLE)
    selected_codes = {code for item in valid for code in item.canonical_course_codes}
    if request.capacity_facts is None or any(
        capacity_match(request.capacity_facts, request.aggregation_scope, request.target_period, code) is None
        for code in selected_codes
    ):
        flags.add(DataQualityFlag.MISSING_CAPACITY_DATA)
        reasons.add(ReasonCode.DEMAND_CAPACITY_DATA_UNAVAILABLE)

    metrics = _metrics(request, valid, valid_owners, review_owners)
    status = DemandStatus.PARTIAL if (
        DataQualityFlag.PARTIAL_INTENT_COVERAGE in flags
        or DataQualityFlag.UNKNOWN_POPULATION_COVERAGE in flags
    ) else DemandStatus.AVAILABLE
    return DemandAggregationResult(
        contract_version="1.0",
        status=status,
        aggregation_scope=request.aggregation_scope,
        target_period=request.target_period,
        metrics=metrics,
        suppressed_metric_ids=(),
        coverage=CoverageMetadata(observed_only, len(valid_owners), denominator, coverage_ratio),
        quality_flags=_ordered_flags(flags),
        reason_codes=_ordered_reasons(reasons),
        provenance=provenance,
        source_versions=sources,
        limitations=_limitations(),
    )


def _metrics(request, valid, valid_owners, review_owners):
    catalog = {
        (item.major_id, item.study_plan_id, item.study_plan_version, item.course_code): item
        for item in request.normalized_plan_course_catalog
    }
    owner_course: set[tuple[str, str]] = set()
    by_plan_course: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    groups: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    plans: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    credits = ZERO
    for record in valid:
        intent = record.intent
        plan = (intent.major_id, intent.study_plan_id, intent.study_plan_version)
        plans[plan].add(intent.owner_scope_id)
        for code in record.canonical_course_codes:
            fact = catalog[(intent.major_id, intent.study_plan_id, intent.study_plan_version, code)]
            pair = (intent.owner_scope_id, code)
            if pair not in owner_course:
                owner_course.add(pair)
            by_plan_course[(*plan, code)].add(intent.owner_scope_id)
            groups[(*plan, fact.requirement_group_id)].add(intent.owner_scope_id)
            credits += fact.credit_hours
    result = [
        DemandMetric(DemandMetricId.VALID_ACTIVE_INTENT_OWNER_COUNT, len(valid_owners)),
        DemandMetric(DemandMetricId.TOTAL_DECLARED_COURSE_SELECTION_COUNT, len(owner_course)),
        DemandMetric(DemandMetricId.TOTAL_DECLARED_CREDIT_LOAD, credits),
    ]
    for (major, plan, version, code), owners in sorted(by_plan_course.items()):
        offering_state, offering_provenance = offering_match(
            request.offering_facts, request.aggregation_scope, request.target_period, code
        )
        fact = (
            capacity_match(request.capacity_facts, request.aggregation_scope, request.target_period, code)
            if request.aggregation_scope.study_plan_id is not None
            else None
        )
        base = dict(course_code=code, major_id=major, study_plan_id=plan, study_plan_version=version)
        result.append(DemandMetric(
            DemandMetricId.COURSE_INTENT_OWNER_COUNT,
            len(owners),
            **base,
            offering_state=offering_state,
            capacity_state=CapacityState.MATCHING_CAPACITY_FACT if fact else CapacityState.CAPACITY_DATA_UNAVAILABLE,
            fact_provenance=offering_provenance,
        ))
        result.append(DemandMetric(
            DemandMetricId.COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS,
            Decimal(len(owners)) / Decimal(len(plans[(major, plan, version)])),
            **base,
            denominator_metric_id=DemandMetricId.VALID_ACTIVE_INTENT_OWNER_COUNT,
        ))
        if fact is not None:
            result.append(DemandMetric(
                DemandMetricId.DECLARED_DEMAND_MINUS_CAPACITY,
                len(owners) - fact.capacity,
                **base,
                capacity_state=CapacityState.MATCHING_CAPACITY_FACT,
                fact_provenance=fact.provenance,
            ))
    if request.aggregation_scope.study_plan_id is None:
        global_courses: dict[str, set[str]] = defaultdict(set)
        for owner, code in owner_course:
            global_courses[code].add(owner)
        for code, owners in sorted(global_courses.items()):
            offering_state, offering_provenance = offering_match(
                request.offering_facts, request.aggregation_scope, request.target_period, code
            )
            fact = capacity_match(
                request.capacity_facts, request.aggregation_scope, request.target_period, code
            )
            result.append(DemandMetric(
                DemandMetricId.COURSE_INTENT_OWNER_COUNT, len(owners), course_code=code,
                offering_state=offering_state,
                capacity_state=CapacityState.MATCHING_CAPACITY_FACT if fact else CapacityState.CAPACITY_DATA_UNAVAILABLE,
                fact_provenance=offering_provenance,
            ))
            result.append(DemandMetric(
                DemandMetricId.COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS,
                Decimal(len(owners)) / Decimal(len(valid_owners)), course_code=code,
                denominator_metric_id=DemandMetricId.VALID_ACTIVE_INTENT_OWNER_COUNT,
            ))
            if fact is not None:
                result.append(DemandMetric(
                    DemandMetricId.DECLARED_DEMAND_MINUS_CAPACITY,
                    len(owners) - fact.capacity, course_code=code,
                    capacity_state=CapacityState.MATCHING_CAPACITY_FACT,
                    fact_provenance=fact.provenance,
                ))
    for (major, plan, version, group), owners in sorted(groups.items()):
        result.append(DemandMetric(
            DemandMetricId.REQUIREMENT_GROUP_INTENT_OWNER_COUNT, len(owners),
            major_id=major, study_plan_id=plan, study_plan_version=version,
            requirement_group_id=group,
        ))
    for (major, plan, version), owners in sorted(plans.items()):
        result.append(DemandMetric(
            DemandMetricId.PLAN_INTENT_OWNER_COUNT, len(owners), major_id=major,
            study_plan_id=plan, study_plan_version=version,
        ))
    if request.include_review_metric:
        result.append(DemandMetric(DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT, len(review_owners)))
    order = {item: index for index, item in enumerate(METRIC_REGISTRY)}
    return tuple(sorted(result, key=lambda item: (
        order[item.metric_id], item.major_id or "", item.study_plan_version or "",
        item.study_plan_id or "", item.requirement_group_id or "", item.course_code or "",
    )))


def _disclosure_populations(request, valid, review_owners):
    """Return every nonzero owner population whose category would be disclosed."""

    catalog = {
        (item.major_id, item.study_plan_id, item.study_plan_version, item.course_code): item
        for item in request.normalized_plan_course_catalog
    }
    valid_owners = {item.intent.owner_scope_id for item in valid}
    populations: list[int] = [len(valid_owners)] if valid_owners else []
    course_global: dict[str, set[str]] = defaultdict(set)
    course_plan: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    groups: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    plans: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for record in valid:
        intent = record.intent
        plan = (intent.major_id, intent.study_plan_id, intent.study_plan_version)
        plans[plan].add(intent.owner_scope_id)
        for code in record.canonical_course_codes:
            fact = catalog[(intent.major_id, intent.study_plan_id, intent.study_plan_version, code)]
            course_global[code].add(intent.owner_scope_id)
            course_plan[(*plan, code)].add(intent.owner_scope_id)
            groups[(*plan, fact.requirement_group_id)].add(intent.owner_scope_id)
    populations.extend(len(owners) for owners in course_plan.values())
    if request.aggregation_scope.study_plan_id is None:
        populations.extend(len(owners) for owners in course_global.values())
    populations.extend(len(owners) for owners in groups.values())
    populations.extend(len(owners) for owners in plans.values())
    if review_owners:
        populations.append(len(review_owners))
    return tuple(populations)


def _validate_input(request):
    if request.contract_version != "1.0":
        raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "contract version mismatch")
    validate_privacy_configuration(request.privacy_configuration)
    limits = request.aggregation_limits
    if (
        not isinstance(limits.max_intents, int) or isinstance(limits.max_intents, bool)
        or not isinstance(limits.max_catalog_courses, int) or isinstance(limits.max_catalog_courses, bool)
        or limits.max_intents < 1 or limits.max_catalog_courses < 1
    ):
        raise DemandAggregationError(ReasonCode.DEMAND_LIMIT_EXCEEDED, "positive aggregation limits are required")
    if len(request.resolved_intents) > limits.max_intents or len(request.normalized_plan_course_catalog) > limits.max_catalog_courses:
        raise DemandAggregationError(ReasonCode.DEMAND_LIMIT_EXCEEDED, "aggregation input exceeds configured limit")
    scope = request.aggregation_scope
    if request.target_period.university_id != scope.university_id:
        raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "target period crosses university scope")
    for resolved in request.resolved_intents:
        intent = resolved.record.intent
        if intent.university_id != scope.university_id or intent.target_period != request.target_period:
            raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "intent crosses university or period scope")
        if not _identity_in_scope(intent, scope):
            raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "intent crosses academic scope")
    catalog_keys = []
    for fact in request.normalized_plan_course_catalog:
        if (
            fact.university_id != scope.university_id
            or not _fact_in_scope(fact, scope)
            or fact.credit_hours < 0
            or not all((fact.major_id, fact.study_plan_id, fact.study_plan_version, fact.course_code, fact.requirement_group_id, fact.source_version))
        ):
            raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "catalog crosses academic scope")
        catalog_keys.append((fact.major_id, fact.study_plan_id, fact.study_plan_version, fact.course_code))
    if len(catalog_keys) != len(set(catalog_keys)):
        raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "catalog contains duplicate plan-course identity")
    for fact in request.offering_facts or ():
        if (
            fact.university_id != scope.university_id
            or fact.target_period != request.target_period
            or fact.provenance is FactProvenance.UNAVAILABLE
        ):
            raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "offering fact crosses scope")
    capacity_keys = []
    for fact in request.capacity_facts or ():
        if (
            fact.university_id != scope.university_id
            or fact.target_period != request.target_period
            or fact.capacity < 0
            or fact.provenance is FactProvenance.UNAVAILABLE
        ):
            raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "capacity fact crosses scope or is invalid")
        capacity_keys.append((fact.university_id, fact.target_period, fact.course_code, fact.major_id, fact.study_plan_id, fact.study_plan_version))
    if len(capacity_keys) != len(set(capacity_keys)):
        raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "capacity input contains duplicate exact facts")
    keys = {(item.major_id, item.study_plan_id, item.study_plan_version, item.course_code) for item in request.normalized_plan_course_catalog}
    for resolved in request.resolved_intents:
        if resolved.disposition is ResolutionDisposition.CURRENT and resolved.record.status is ValidationStatus.VALID:
            intent = resolved.record.intent
            if any((intent.major_id, intent.study_plan_id, intent.study_plan_version, code) not in keys for code in resolved.record.canonical_course_codes):
                raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "valid intent lacks exact catalog mapping")
    denominator = request.coverage.population_denominator
    if denominator is not None and (not isinstance(denominator, int) or isinstance(denominator, bool) or denominator < 0):
        raise DemandAggregationError(ReasonCode.DEMAND_SCOPE_MISMATCH, "invalid population denominator")


def _identity_in_scope(intent, scope):
    return (
        (scope.major_id is None or intent.major_id == scope.major_id)
        and (scope.study_plan_id is None or intent.study_plan_id == scope.study_plan_id)
        and (scope.study_plan_version is None or intent.study_plan_version == scope.study_plan_version)
    )


def _fact_in_scope(fact, scope):
    return (
        (scope.major_id is None or fact.major_id == scope.major_id)
        and (scope.study_plan_id is None or fact.study_plan_id == scope.study_plan_id)
        and (scope.study_plan_version is None or fact.study_plan_version == scope.study_plan_version)
    )


def _in_scope(record, request):
    return record.intent.target_period == request.target_period and _identity_in_scope(record.intent, request.aggregation_scope)


def _empty_result(request, provenance, sources):
    return DemandAggregationResult(
        "1.0", DemandStatus.INSUFFICIENT_DATA, request.aggregation_scope, request.target_period,
        (), (), CoverageMetadata(True, 0, request.coverage.population_denominator, None),
        (DataQualityFlag.UNKNOWN_POPULATION_COVERAGE,) if request.coverage.population_denominator is None else (),
        (ReasonCode.DEMAND_NO_VALID_ACTIVE_INTENTS,), provenance, sources, _limitations(),
    )


def _suppressed_result(request, provenance, sources):
    return DemandAggregationResult(
        "1.0", DemandStatus.SUPPRESSED, request.aggregation_scope, request.target_period,
        (), tuple(METRIC_REGISTRY), CoverageMetadata(True, None, None, None),
        (DataQualityFlag.SUPPRESSED_FOR_PRIVACY,), (ReasonCode.DEMAND_PRIVACY_SUPPRESSED,),
        provenance, sources, _limitations(),
    )


def _ordered_flags(values):
    return tuple(item for item in DataQualityFlag if item in values)


def _ordered_reasons(values):
    return tuple(item for item in ReasonCode if item in values)


def _limitations():
    return (
        "Describes observed current intent only; not enrollment, a forecast, or an institutional recommendation.",
        "No bottleneck ranking, section estimate, faculty workload inference, or SIS mutation is performed.",
    )
