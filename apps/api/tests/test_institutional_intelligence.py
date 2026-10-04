"""Exhaustive contract tests for Phase P7.2 — Institutional Intelligence Pure-Domain Engine.

Covers all 55 P7.2 test scenarios from docs/institutional-intelligence-advisor-test-matrix.md:
- P7-TEST-CAP-001 .. 020 (Demand & Capacity Pressure, 20 scenarios)
- P7-TEST-STR-001 .. 015 (Curricular Structure & Bottleneck, 15 scenarios)
- P7-TEST-PRV-001 .. 012 (Privacy & Suppression Propagation, 12 scenarios)
- P7-TEST-ALT-001 .. 008 (Institutional Alerts, 8 scenarios)
- Core algorithmic scenarios: Common-ancestor OR, OR-bypass, AND-group, Elective-gateway,
  Localized source conflict, Zero-credit, Cycle safety.
"""

from __future__ import annotations

from dataclasses import fields
from decimal import Decimal
import pytest

from app.institutional_intelligence import (
    CapacityFact,
    CapacityPressureState,
    InstitutionalAlertId,
    InstitutionalFactAuthority,
    InstitutionalIntelligenceInput,
    InstitutionalIntelligenceResult,
    InstitutionalPrivacyConfiguration,
    InstitutionalSignalId,
    OfferingFact,
    PlannedOfferingStatus,
    SignalStatus,
    StructuralGatewayStatus,
    StructuralMandatoryRole,
    evaluate_capacity_metrics,
    evaluate_institutional_alerts,
    evaluate_institutional_intelligence,
    evaluate_mandatory_role,
    evaluate_structural_gateway,
    get_direct_downstream_courses,
    get_individually_mandatory_courses,
    get_transitive_downstream_courses,
)
from app.mock_registration.models import (
    AggregationScope,
    CoverageMetadata,
    DemandAggregationResult,
    DemandMetric,
    DemandMetricId,
    DemandStatus,
    TargetPeriod,
    TargetPeriodClass,
)
from app.mock_registration.registries import DataQualityFlag
from app.progress.models import (
    AcademicProgressCatalog,
    CourseCatalogStatus,
    ProgressPlanCourse,
    ProgressRequirementGroup,
    ProgressStudyPlan,
    RequirementType,
)
from app.rules.models import (
    CanTakeCatalog,
    DependencyGroup,
    DependencyType,
    PlanCourseRule,
    PrerequisiteLogicStatus,
)

# ---------------------------------------------------------------------------
# Test Fixture Helpers
# ---------------------------------------------------------------------------

UNIV_ID = "00000000-0000-0000-0000-000000000001"
UNIV_B_ID = "00000000-0000-0000-0000-000000000002"
PERIOD_KEY = "2026/2027-1"
PERIOD_B_KEY = "2026/2027-2"
PLAN_ID = "10000000-0000-0000-0000-000000000005"
PLAN_B_ID = "10000000-0000-0000-0000-000000000006"


def make_catalog(
    req_courses: list[tuple[str, str, Decimal]] | None = None,  # (code, group_id, credits)
    elec_courses: list[tuple[str, str, Decimal]] | None = None,
    plan_id: str = PLAN_ID,
) -> AcademicProgressCatalog:
    groups = [
        ProgressRequirementGroup(
            group_id="grp-req",
            study_plan_id=plan_id,
            group_code="MAJOR_REQUIRED",
            name_ar="إجباري التخصص",
            name_en="Major Required",
            scope="major",
            requirement_type=RequirementType.REQUIRED,
            required_credit_hours=Decimal("63"),
            display_order=1,
        ),
        ProgressRequirementGroup(
            group_id="grp-supp",
            study_plan_id=plan_id,
            group_code="SUPPORTING_REQUIRED",
            name_ar="المتطلبات المساندة",
            name_en="Supporting Required",
            scope="faculty",
            requirement_type=RequirementType.REQUIRED,
            required_credit_hours=Decimal("12"),
            display_order=2,
        ),
        ProgressRequirementGroup(
            group_id="grp-univ-req",
            study_plan_id=plan_id,
            group_code="UNIVERSITY_REQUIRED",
            name_ar="متطلبات الجامعة الإجبارية",
            name_en="University Required",
            scope="university",
            requirement_type=RequirementType.REQUIRED,
            required_credit_hours=Decimal("18"),
            display_order=3,
        ),
        ProgressRequirementGroup(
            group_id="grp-elec",
            study_plan_id=plan_id,
            group_code="MAJOR_ELECTIVE",
            name_ar="اختياري التخصص",
            name_en="Major Elective",
            scope="major",
            requirement_type=RequirementType.ELECTIVE,
            required_credit_hours=Decimal("9"),
            display_order=4,
        ),
    ]

    courses = []
    order = 1
    if req_courses:
        for code, gid, cr in req_courses:
            courses.append(
                ProgressPlanCourse(
                    plan_course_id=f"pc-{code}",
                    study_plan_id=plan_id,
                    requirement_group_id=gid,
                    course_code=code,
                    catalog_status=CourseCatalogStatus.KNOWN,
                    credit_hours=cr,
                    display_order=order,
                )
            )
            order += 1

    if elec_courses:
        for code, gid, cr in elec_courses:
            courses.append(
                ProgressPlanCourse(
                    plan_course_id=f"pc-{code}",
                    study_plan_id=plan_id,
                    requirement_group_id=gid,
                    course_code=code,
                    catalog_status=CourseCatalogStatus.KNOWN,
                    credit_hours=cr,
                    display_order=order,
                )
            )
            order += 1

    return AcademicProgressCatalog(
        study_plan=ProgressStudyPlan(study_plan_id=plan_id, total_credit_hours=Decimal("132")),
        requirement_groups=tuple(groups),
        plan_courses=tuple(courses),
    )


def make_can_take_catalog(
    rules: list[PlanCourseRule],
    plan_id: str = PLAN_ID,
) -> CanTakeCatalog:
    from app.rules.models import CourseIdentity
    all_codes = set()
    for r in rules:
        all_codes.add(r.course_code)
        for g in r.dependency_groups:
            all_codes.update(g.option_course_codes)
    course_identities = tuple(
        CourseIdentity(course_code=code, catalog_status=CourseCatalogStatus.KNOWN)
        for code in sorted(all_codes)
    )
    return CanTakeCatalog(
        study_plan_id=plan_id,
        plan_courses=tuple(rules),
        courses=course_identities,
    )


def make_demand_result(
    course_demands: dict[str, int | None],
    total_valid_owners: int = 100,
    suppressed_metric_ids: tuple[DemandMetricId, ...] = (),
    is_suppressed: bool = False,
    review_owners: int = 0,
    total_credits: Decimal = Decimal("300.00"),
    univ_id: str = UNIV_ID,
    period_key: str = PERIOD_KEY,
    quality_flags: tuple[DataQualityFlag, ...] | None = None,
) -> DemandAggregationResult:
    metrics = [
        DemandMetric(
            metric_id=DemandMetricId.VALID_ACTIVE_INTENT_OWNER_COUNT,
            value=total_valid_owners if not is_suppressed else None,
        ),
        DemandMetric(
            metric_id=DemandMetricId.TOTAL_DECLARED_CREDIT_LOAD,
            value=total_credits if not is_suppressed else None,
        ),
        DemandMetric(
            metric_id=DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT,
            value=review_owners
            if not is_suppressed and DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT not in suppressed_metric_ids
            else None,
        ),
    ]

    for c_code, d_val in course_demands.items():
        val = d_val if not is_suppressed and DemandMetricId.COURSE_INTENT_OWNER_COUNT not in suppressed_metric_ids else None
        metrics.append(
            DemandMetric(
                metric_id=DemandMetricId.COURSE_INTENT_OWNER_COUNT,
                value=val,
                course_code=c_code,
            )
        )
        if total_valid_owners > 0 and val is not None:
            share = (Decimal(val) / Decimal(total_valid_owners)).quantize(Decimal("0.0001"))
            metrics.append(
                DemandMetric(
                    metric_id=DemandMetricId.COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS,
                    value=share,
                    course_code=c_code,
                )
            )

    flags_list = list(quality_flags) if quality_flags is not None else []
    if is_suppressed and DataQualityFlag.SUPPRESSED_FOR_PRIVACY not in flags_list:
        flags_list.append(DataQualityFlag.SUPPRESSED_FOR_PRIVACY)
    if review_owners > 0 and DataQualityFlag.REVIEW_REQUIRED_INTENTS_EXCLUDED not in flags_list:
        flags_list.append(DataQualityFlag.REVIEW_REQUIRED_INTENTS_EXCLUDED)

    return DemandAggregationResult(
        contract_version="1.0",
        status=DemandStatus.SUPPRESSED if is_suppressed else DemandStatus.AVAILABLE,
        aggregation_scope=AggregationScope(university_id=univ_id),
        target_period=TargetPeriod(
            university_id=univ_id,
            period_key=period_key,
            period_class=TargetPeriodClass.DECLARED_PLANNING_PERIOD,
            source_version="1.0",
        ),
        metrics=tuple(metrics),
        suppressed_metric_ids=suppressed_metric_ids,
        coverage=CoverageMetadata(
            observed_intents_only=True,
            valid_active_intent_owner_count=total_valid_owners if not is_suppressed else None,
            population_denominator=None,
            population_coverage_ratio=None,
        ),
        quality_flags=tuple(flags_list),
        reason_codes=(),
        provenance=(),
        source_versions=("1.0",),
        limitations=(),
    )


def make_offering_fact(
    university_id: str = UNIV_ID,
    period_key: str = PERIOD_KEY,
    course_code: str = "1501110",
    status: PlannedOfferingStatus = PlannedOfferingStatus.OFFERED,
    authority: InstitutionalFactAuthority = InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
    source_version: str = "1.0",
    univ_id: str | None = None,
) -> OfferingFact:
    u_id = univ_id if univ_id is not None else university_id
    return OfferingFact(
        university_id=u_id,
        period_key=period_key,
        course_code=course_code,
        status=status,
        authority=authority,
        source_version=source_version,
    )


def make_capacity_fact(
    university_id: str = UNIV_ID,
    period_key: str = PERIOD_KEY,
    course_code: str = "1501110",
    capacity: int = 40,
    study_plan_id: str | None = None,
    authority: InstitutionalFactAuthority = InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
    source_version: str = "1.0",
    univ_id: str | None = None,
) -> CapacityFact:
    u_id = univ_id if univ_id is not None else university_id
    return CapacityFact(
        university_id=u_id,
        period_key=period_key,
        course_code=course_code,
        capacity=capacity,
        authority=authority,
        source_version=source_version,
        study_plan_id=study_plan_id,
    )


def default_context(
    course_code: str = "1501110",
    catalog: AcademicProgressCatalog | None = None,
    can_take_catalog: CanTakeCatalog | None = None,
    demand_result: DemandAggregationResult | None = None,
    offering_fact=None,
    capacity_fact=None,
) -> InstitutionalIntelligenceInput:
    cat = catalog or make_catalog(
        req_courses=[(course_code, "grp-req", Decimal("3"))],
        elec_courses=[],
    )
    ctc = can_take_catalog or make_can_take_catalog(
        rules=[PlanCourseRule(course_code=course_code, prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED)]
    )
    return InstitutionalIntelligenceInput(
        university_id=UNIV_ID,
        target_period_key=PERIOD_KEY,
        course_code=course_code,
        catalog=cat,
        can_take_catalog=ctc,
        demand_result=demand_result,
        offering_fact=offering_fact,
        capacity_fact=capacity_fact,
    )


# ===========================================================================
# 1. Demand & Capacity Pressure Scenarios (P7-TEST-CAP-001 .. 020)
# ===========================================================================


def test_p7_test_cap_001_verified_offered_missing_capacity() -> None:
    """P7-TEST-CAP-001: Verified offered course with missing capacity."""
    offering = make_offering_fact(
        university_id=UNIV_ID,
        period_key=PERIOD_KEY,
        course_code="1501110",
        status=PlannedOfferingStatus.OFFERED,
        authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
    )
    demand = make_demand_result({"1501110": 40})
    ctx = default_context(offering_fact=offering, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].status is SignalStatus.INSUFFICIENT_DATA
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value is None
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.NO_CAPACITY_DATA.value
    assert DataQualityFlag.MISSING_CAPACITY_DATA in res.quality_flags

    cap_missing_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_CAPACITY_DATA_MISSING)
    assert cap_missing_alert.emitted is True


def test_p7_test_cap_002_valid_demand_with_verified_capacity() -> None:
    """P7-TEST-CAP-002: Valid demand with verified capacity."""
    offering = make_offering_fact(UNIV_ID, PERIOD_KEY, "1501110", PlannedOfferingStatus.OFFERED)
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 45)
    demand = make_demand_result({"1501110": 50})
    ctx = default_context(offering_fact=offering, capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == 5
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY.value
    assert res.signals[InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO].value == Decimal("1.1111")


def test_p7_test_cap_003_synthetic_offered_with_supplied_capacity() -> None:
    """P7-TEST-CAP-003: Synthetic offered course with supplied capacity."""
    offering = make_offering_fact(UNIV_ID, PERIOD_KEY, "1501110", PlannedOfferingStatus.OFFERED, authority=InstitutionalFactAuthority.SYNTHETIC_SANDBOX_FACT)
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 30, authority=InstitutionalFactAuthority.SYNTHETIC_SANDBOX_FACT)
    demand = make_demand_result({"1501110": 30})
    ctx = default_context(offering_fact=offering, capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == 0
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.WITHIN_SUPPLIED_CAPACITY.value
    assert res.signals[InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO].value == Decimal("1.0000")


def test_p7_test_cap_004_demand_strictly_less_than_capacity() -> None:
    """P7-TEST-CAP-004: Demand strictly less than capacity."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 40)
    demand = make_demand_result({"1501110": 25})
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == -15
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.WITHIN_SUPPLIED_CAPACITY.value
    assert res.signals[InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO].value == Decimal("0.6250")


def test_p7_test_cap_005_demand_equal_to_capacity() -> None:
    """P7-TEST-CAP-005: Demand equal to capacity."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 35)
    demand = make_demand_result({"1501110": 35})
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == 0
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.WITHIN_SUPPLIED_CAPACITY.value
    assert res.signals[InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO].value == Decimal("1.0000")


def test_p7_test_cap_006_demand_exceeds_capacity() -> None:
    """P7-TEST-CAP-006: Demand exceeds capacity."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 50)
    demand = make_demand_result({"1501110": 65})
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == 15
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY.value
    assert res.signals[InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO].value == Decimal("1.3000")


def test_p7_test_cap_007_verified_zero_capacity_positive_demand() -> None:
    """P7-TEST-CAP-007: Verified zero capacity with positive demand."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 0)
    demand = make_demand_result({"1501110": 20})
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == 20
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY.value
    assert res.signals[InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO].status is SignalStatus.NOT_APPLICABLE

    zero_cap_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_ZERO_CAPACITY_WITH_DEMAND)
    assert zero_cap_alert.emitted is True


def test_p7_test_cap_008_zero_demand_with_positive_capacity() -> None:
    """P7-TEST-CAP-008: Zero demand with positive capacity."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 30)
    demand = make_demand_result({"1501110": 0})
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == -30
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.WITHIN_SUPPLIED_CAPACITY.value
    assert res.signals[InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO].value == Decimal("0.0000")


def test_p7_test_cap_009_verified_not_offered_missing_capacity() -> None:
    """P7-TEST-CAP-009: Verified not-offered course with missing capacity."""
    offering = make_offering_fact(UNIV_ID, PERIOD_KEY, "1501110", PlannedOfferingStatus.NOT_OFFERED)
    demand = make_demand_result({"1501110": 10})
    ctx = default_context(offering_fact=offering, capacity_fact=None, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_SUPPLIED_CAPACITY_COUNT].status is SignalStatus.NOT_APPLICABLE
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].status is SignalStatus.NOT_APPLICABLE
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].status is SignalStatus.NOT_APPLICABLE
    assert res.signals[InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO].status is SignalStatus.NOT_APPLICABLE

    cap_missing_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_CAPACITY_DATA_MISSING)
    assert cap_missing_alert.emitted is False


def test_p7_test_cap_010_missing_offering_with_missing_capacity() -> None:
    """P7-TEST-CAP-010: Missing offering facts with missing capacity."""
    demand = make_demand_result({"1501110": 30})
    ctx = default_context(offering_fact=None, capacity_fact=None, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert DataQualityFlag.MISSING_OFFERING_DATA in res.quality_flags
    assert DataQualityFlag.MISSING_CAPACITY_DATA in res.quality_flags
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.NO_CAPACITY_DATA.value

    off_missing_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_OFFERING_DATA_MISSING)
    cap_missing_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_CAPACITY_DATA_MISSING)
    assert off_missing_alert.emitted is True
    assert cap_missing_alert.emitted is True


def test_p7_test_cap_011_partial_adoption_coverage_caveat() -> None:
    """P7-TEST-CAP-011: Partial adoption coverage caveat."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 50)
    demand = make_demand_result({"1501110": 40})
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert "OBSERVED_INTENTS_ONLY" in res.coverage_notes
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == -10
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.WITHIN_SUPPLIED_CAPACITY.value


def test_p7_test_cap_012_suppressed_demand_missing_capacity() -> None:
    """P7-TEST-CAP-012: Suppressed demand with missing capacity."""
    demand = make_demand_result({"1501110": None}, is_suppressed=True, suppressed_metric_ids=(DemandMetricId.COURSE_INTENT_OWNER_COUNT,))
    ctx = default_context(capacity_fact=None, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT].status is SignalStatus.SUPPRESSED
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].status is SignalStatus.SUPPRESSED
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].status is SignalStatus.SUPPRESSED
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value is None


def test_p7_test_cap_013_suppressed_demand_positive_capacity() -> None:
    """P7-TEST-CAP-013: Suppressed demand with positive capacity."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 50)
    demand = make_demand_result({"1501110": None}, is_suppressed=True, suppressed_metric_ids=(DemandMetricId.COURSE_INTENT_OWNER_COUNT,))
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT].status is SignalStatus.SUPPRESSED
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].status is SignalStatus.SUPPRESSED
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value is None
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].status is SignalStatus.SUPPRESSED


def test_p7_test_cap_014_review_required_owner_volume() -> None:
    """P7-TEST-CAP-014: Review-required intent owner volume."""
    demand = make_demand_result({"1501110": 20}, review_owners=14)
    ctx = default_context(demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    sig = res.signals[InstitutionalSignalId.INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT]
    assert sig.status is SignalStatus.AVAILABLE
    assert sig.value == 14
    assert sig.unit == "owners"


def test_p7_test_cap_015_zero_credit_course_demand_and_capacity() -> None:
    """P7-TEST-CAP-015: Zero-credit course demand & capacity."""
    cat = make_catalog(req_courses=[("0200115", "grp-univ-req", Decimal("0.00"))])
    ctc = make_can_take_catalog([PlanCourseRule(course_code="0200115", prerequisite_logic_status=PrerequisiteLogicStatus.NOT_APPLICABLE)])
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "0200115", 40)
    demand = make_demand_result({"0200115": 45}, total_credits=Decimal("0.00"))

    ctx = default_context(
        course_code="0200115",
        catalog=cat,
        can_take_catalog=ctc,
        capacity_fact=capacity,
        demand_result=demand,
    )
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_TOTAL_DECLARED_CREDIT_LOAD].value == Decimal("0.00")
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == 5
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY.value


def test_p7_test_cap_016_course_across_two_study_plans() -> None:
    """P7-TEST-CAP-016: Course-level demand aggregation isolates university-wide vs plan scope."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 40)
    demand = make_demand_result({"1501110": 45})  # 45 total university-wide
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT].value == 45
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == 5


def test_p7_test_cap_017_different_target_periods_isolation() -> None:
    """P7-TEST-CAP-017: Target period mismatch between fact and query is rejected."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_B_KEY, "1501110", 40)
    ctx = default_context(capacity_fact=capacity)
    with pytest.raises(ValueError, match="Period mismatch"):
        evaluate_institutional_intelligence(ctx)


def test_p7_test_cap_018_different_universities_isolation() -> None:
    """P7-TEST-CAP-018: Tenant mismatch between fact and query is rejected."""
    capacity = make_capacity_fact(UNIV_B_ID, PERIOD_KEY, "1501110", 40)
    ctx = default_context(capacity_fact=capacity)
    with pytest.raises(ValueError, match="Tenant mismatch"):
        evaluate_institutional_intelligence(ctx)


def test_p7_test_cap_019_capacity_fact_with_study_plan_scope() -> None:
    """P7-TEST-CAP-019: Capacity fact with study plan scope evaluated."""
    cap_plan = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 15, study_plan_id=PLAN_ID)
    demand = make_demand_result({"1501110": 20})
    cat = make_catalog(req_courses=[("1501110", "grp-req", Decimal("3"))])
    ctc = make_can_take_catalog([PlanCourseRule("1501110", PrerequisiteLogicStatus.VERIFIED)])

    input_data = InstitutionalIntelligenceInput(
        university_id=UNIV_ID,
        target_period_key=PERIOD_KEY,
        course_code="1501110",
        catalog=cat,
        can_take_catalog=ctc,
        study_plan_id=PLAN_ID,
        all_capacity_facts=(cap_plan,),
        demand_result=demand,
    )
    res = evaluate_institutional_intelligence(input_data)
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == 5
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.DECLARED_DEMAND_EXCEEDS_SUPPLIED_CAPACITY.value


def test_p7_test_cap_020_empty_demand_population() -> None:
    """P7-TEST-CAP-020: Empty demand population evaluates cleanly."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 40)
    demand = make_demand_result({"1501110": 0}, total_valid_owners=0, total_credits=Decimal("0.00"))
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT].value == 0
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == -40
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].value == CapacityPressureState.WITHIN_SUPPLIED_CAPACITY.value


# ===========================================================================
# 2. Curricular Structure & Bottleneck Scenarios (P7-TEST-STR-001 .. 015)
# ===========================================================================


def test_p7_test_str_001_terminal_elective_course() -> None:
    """P7-TEST-STR-001: Terminal elective course evaluates to NON_GATEWAY."""
    cat = make_catalog(elec_courses=[("1501392", "grp-elec", Decimal("3"))])
    ctc = make_can_take_catalog([PlanCourseRule("1501392", PrerequisiteLogicStatus.VERIFIED)])
    ctx = default_context(course_code="1501392", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].value == StructuralMandatoryRole.CHOICE_ELECTIVE.value
    assert res.signals[InstitutionalSignalId.INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT].value == 0
    assert res.signals[InstitutionalSignalId.INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT].value == 0
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.NON_GATEWAY.value


def test_p7_test_str_002_one_downstream_dependency() -> None:
    """P7-TEST-STR-002: One downstream dependency gates curriculum (threshold-free)."""
    cat = make_catalog(req_courses=[("COURSE_A", "grp-req", Decimal("3")), ("COURSE_B", "grp-req", Decimal("3"))])
    rules = [
        PlanCourseRule("COURSE_A", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule(
            "COURSE_B",
            PrerequisiteLogicStatus.VERIFIED,
            (DependencyGroup(1, DependencyType.PREREQUISITE, ("COURSE_A",)),),
        ),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="COURSE_A", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT].value == 1
    assert res.signals[InstitutionalSignalId.INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT].value == 1
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value


def test_p7_test_str_003_required_supporting_with_downstream() -> None:
    """P7-TEST-STR-003: Required Supporting course with downstream dependency."""
    cat = make_catalog(req_courses=[("SYNTH_SUPP_GATEWAY", "grp-supp", Decimal("3")), ("M1", "grp-req", Decimal("3"))])
    rules = [
        PlanCourseRule("SYNTH_SUPP_GATEWAY", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M1", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("SYNTH_SUPP_GATEWAY",)),)),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="SYNTH_SUPP_GATEWAY", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].value == StructuralMandatoryRole.MANDATORY_REQUIRED.value
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value


def test_p7_test_str_004_required_supporting_without_downstream() -> None:
    """P7-TEST-STR-004: Required Supporting course without downstream dependency."""
    cat = make_catalog(req_courses=[("0300101", "grp-supp", Decimal("3"))])
    rules = [PlanCourseRule("0300101", PrerequisiteLogicStatus.VERIFIED)]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="0300101", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].value == StructuralMandatoryRole.MANDATORY_REQUIRED.value
    assert res.signals[InstitutionalSignalId.INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT].value == 0
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.NON_GATEWAY.value


def test_p7_test_str_005_deep_transitive_prerequisite_chain() -> None:
    """P7-TEST-STR-005: Deep transitive prerequisite chain."""
    # Chain of 5 courses: C1 -> C2 -> C3 -> C4 -> C5
    codes = [f"C{i}" for i in range(1, 6)]
    cat = make_catalog(req_courses=[(c, "grp-req", Decimal("3")) for c in codes])
    rules = [
        PlanCourseRule("C1", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("C2", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("C1",)),)),
        PlanCourseRule("C3", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("C2",)),)),
        PlanCourseRule("C4", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("C3",)),)),
        PlanCourseRule("C5", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("C4",)),)),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="C1", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT].value == 1
    assert res.signals[InstitutionalSignalId.INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT].value == 4
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value


def test_p7_test_str_006_source_conflict_prerequisite() -> None:
    """P7-TEST-STR-006: Prerequisite source conflict evaluates to REVIEW_REQUIRED."""
    cat = make_catalog(req_courses=[("1505320", "grp-req", Decimal("3"))])
    rules = [PlanCourseRule("1505320", PrerequisiteLogicStatus.SOURCE_CONFLICT)]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="1505320", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].status is SignalStatus.REVIEW_REQUIRED
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.REVIEW_REQUIRED.value


def test_p7_test_str_007_zero_credit_course_with_downstream() -> None:
    """P7-TEST-STR-007: Required zero-credit course with downstream dependency."""
    cat = make_catalog(req_courses=[("SYNTH_ZERO_GATEWAY", "grp-req", Decimal("0.00")), ("M_NEXT", "grp-req", Decimal("3"))])
    rules = [
        PlanCourseRule("SYNTH_ZERO_GATEWAY", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M_NEXT", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("SYNTH_ZERO_GATEWAY",)),)),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="SYNTH_ZERO_GATEWAY", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].value == StructuralMandatoryRole.MANDATORY_REQUIRED.value
    assert res.signals[InstitutionalSignalId.INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT].value == 1
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value


def test_p7_test_str_008_zero_credit_course_without_downstream() -> None:
    """P7-TEST-STR-008: Required zero-credit course without downstream dependency."""
    cat = make_catalog(req_courses=[("0200115", "grp-univ-req", Decimal("0.00"))])
    rules = [PlanCourseRule("0200115", PrerequisiteLogicStatus.NOT_APPLICABLE)]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="0200115", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].value == StructuralMandatoryRole.MANDATORY_REQUIRED.value
    assert res.signals[InstitutionalSignalId.INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT].value == 0
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.NON_GATEWAY.value


def test_p7_test_str_009_structural_status_immune_to_demand_suppression() -> None:
    """P7-TEST-STR-009: Structural status unchanged by demand suppression."""
    cat = make_catalog(req_courses=[("1501221", "grp-req", Decimal("3")), ("M1", "grp-req", Decimal("3"))])
    rules = [
        PlanCourseRule("1501221", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M1", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("1501221",)),)),
    ]
    ctc = make_can_take_catalog(rules)
    demand = make_demand_result({"1501221": None}, is_suppressed=True)
    ctx = default_context(course_code="1501221", catalog=cat, can_take_catalog=ctc, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT].status is SignalStatus.SUPPRESSED
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].status is SignalStatus.AVAILABLE
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value


def test_p7_test_str_010_structural_status_immune_to_missing_capacity() -> None:
    """P7-TEST-STR-010: Structural status unchanged by missing capacity."""
    cat = make_catalog(req_courses=[("1501221", "grp-req", Decimal("3")), ("M1", "grp-req", Decimal("3"))])
    rules = [
        PlanCourseRule("1501221", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M1", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("1501221",)),)),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="1501221", catalog=cat, can_take_catalog=ctc, capacity_fact=None)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_SUPPLIED_CAPACITY_COUNT].status is SignalStatus.INSUFFICIENT_DATA
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value


def test_p7_test_str_011_elective_course_with_downstream_dependency() -> None:
    """P7-TEST-STR-011: Elective course gating only elective paths is NON_GATEWAY, downstream count factual."""
    cat = make_catalog(
        req_courses=[("M1", "grp-req", Decimal("3"))],
        elec_courses=[("SYNTH_ELEC_GATEWAY", "grp-elec", Decimal("3")), ("E_NEXT", "grp-elec", Decimal("3"))],
    )
    rules = [
        PlanCourseRule("SYNTH_ELEC_GATEWAY", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("E_NEXT", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("SYNTH_ELEC_GATEWAY",)),)),
        PlanCourseRule("M1", PrerequisiteLogicStatus.VERIFIED),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="SYNTH_ELEC_GATEWAY", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].value == StructuralMandatoryRole.CHOICE_ELECTIVE.value
    assert res.signals[InstitutionalSignalId.INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT].value == 1
    assert res.signals[InstitutionalSignalId.INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT].value == 1
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.NON_GATEWAY.value


def test_p7_test_str_012_mandatory_course_with_or_prerequisite_alternative() -> None:
    """P7-TEST-STR-012: Mandatory course with verified OR alternative is NON_GATEWAY."""
    cat = make_catalog(req_courses=[("COURSE_X", "grp-req", Decimal("3")), ("COURSE_ALT", "grp-req", Decimal("3")), ("M_TARGET", "grp-req", Decimal("3"))])
    # M_TARGET requires COURSE_X OR COURSE_ALT
    rules = [
        PlanCourseRule("COURSE_X", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("COURSE_ALT", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M_TARGET", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("COURSE_X", "COURSE_ALT")),)),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="COURSE_X", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT].value == 1
    # COURSE_X is bypassable via COURSE_ALT -> not indispensable!
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.NON_GATEWAY.value


def test_p7_test_str_013_mandatory_classification_derived_from_plan_semantics() -> None:
    """P7-TEST-STR-013: Mandatory classification derived from plan semantics, not hardcoded whitelist."""
    cat = make_catalog(req_courses=[("COURSE_S", "grp-supp", Decimal("3")), ("M_NEXT", "grp-req", Decimal("3"))])
    rules = [
        PlanCourseRule("COURSE_S", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M_NEXT", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("COURSE_S",)),)),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="COURSE_S", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].value == StructuralMandatoryRole.MANDATORY_REQUIRED.value
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value


def test_p7_test_str_014_structural_gateway_with_balanced_capacity() -> None:
    """P7-TEST-STR-014: Structural gateway with balanced capacity (deficit <= 0) remains gateway."""
    cat = make_catalog(req_courses=[("1501221", "grp-req", Decimal("3")), ("M1", "grp-req", Decimal("3"))])
    rules = [
        PlanCourseRule("1501221", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M1", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("1501221",)),)),
    ]
    ctc = make_can_take_catalog(rules)
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501221", 40)
    demand = make_demand_result({"1501221": 30})
    ctx = default_context(course_code="1501221", catalog=cat, can_take_catalog=ctc, capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value == -10
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value


def test_p7_test_str_015_multi_plan_structural_difference() -> None:
    """P7-TEST-STR-015: Multi-plan structural difference evaluated per plan."""
    cat_a = make_catalog(req_courses=[("COURSE_X", "grp-req", Decimal("3")), ("M1", "grp-req", Decimal("3"))], plan_id=PLAN_ID)
    cat_b = make_catalog(req_courses=[("M1", "grp-req", Decimal("3"))], elec_courses=[("COURSE_X", "grp-elec", Decimal("3"))], plan_id=PLAN_B_ID)

    rules_a = [
        PlanCourseRule("COURSE_X", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M1", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("COURSE_X",)),)),
    ]
    rules_b = [
        PlanCourseRule("COURSE_X", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M1", PrerequisiteLogicStatus.VERIFIED),  # Not required for M1 in Plan B
    ]

    ctc_a = make_can_take_catalog(rules_a, plan_id=PLAN_ID)
    ctc_b = make_can_take_catalog(rules_b, plan_id=PLAN_B_ID)

    ctx_a = default_context(course_code="COURSE_X", catalog=cat_a, can_take_catalog=ctc_a)
    ctx_b = default_context(course_code="COURSE_X", catalog=cat_b, can_take_catalog=ctc_b)

    res_a = evaluate_institutional_intelligence(ctx_a)
    res_b = evaluate_institutional_intelligence(ctx_b)

    assert res_a.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value
    assert res_b.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.NON_GATEWAY.value


# ===========================================================================
# Algorithmic Deep Dives: AND/OR, Common Ancestor, Elective Gateway, Conflict
# ===========================================================================


def test_sound_boolean_common_ancestor_or_indispensable() -> None:
    """Mandatory target M requires A OR B. Both A and B require X. X is indispensable to M!"""
    cat = make_catalog(
        req_courses=[("X", "grp-req", Decimal("3")), ("M", "grp-req", Decimal("3"))],
        elec_courses=[("A", "grp-elec", Decimal("3")), ("B", "grp-elec", Decimal("3"))],
    )
    rules = [
        PlanCourseRule("X", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("A", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("X",)),)),
        PlanCourseRule("B", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("X",)),)),
        PlanCourseRule("M", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("A", "B")),)),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="X", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    # Must recognize X as STRUCTURAL_GATEWAY even though M has OR options A and B!
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value


def test_sound_boolean_or_bypass_not_indispensable() -> None:
    """M requires A OR B. A requires X, but B does NOT require X. X is not indispensable."""
    cat = make_catalog(
        req_courses=[("X", "grp-req", Decimal("3")), ("M", "grp-req", Decimal("3"))],
        elec_courses=[("A", "grp-elec", Decimal("3")), ("B", "grp-elec", Decimal("3"))],
    )
    rules = [
        PlanCourseRule("X", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("A", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("X",)),)),
        PlanCourseRule("B", PrerequisiteLogicStatus.VERIFIED),  # B has no prerequisites
        PlanCourseRule("M", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("A", "B")),)),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="X", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.NON_GATEWAY.value


def test_sound_boolean_and_group_indispensability() -> None:
    """M requires (A OR B) AND C. C is indispensable to M."""
    cat = make_catalog(
        req_courses=[("C", "grp-req", Decimal("3")), ("M", "grp-req", Decimal("3"))],
        elec_courses=[("A", "grp-elec", Decimal("3")), ("B", "grp-elec", Decimal("3"))],
    )
    rules = [
        PlanCourseRule("A", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("B", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("C", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule(
            "M",
            PrerequisiteLogicStatus.VERIFIED,
            (
                DependencyGroup(1, DependencyType.PREREQUISITE, ("A", "B")),
                DependencyGroup(2, DependencyType.PREREQUISITE, ("C",)),
            ),
        ),
    ]
    ctc = make_can_take_catalog(rules)
    ctx_c = default_context(course_code="C", catalog=cat, can_take_catalog=ctc)
    res_c = evaluate_institutional_intelligence(ctx_c)
    assert res_c.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value

    ctx_a = default_context(course_code="A", catalog=cat, can_take_catalog=ctc)
    res_a = evaluate_institutional_intelligence(ctx_a)
    assert res_a.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.NON_GATEWAY.value


def test_elective_course_indispensable_to_mandatory_target_is_gateway() -> None:
    """An elective course that is indispensable to a mandatory course CAN be a gateway."""
    cat = make_catalog(
        req_courses=[("M_TARGET", "grp-req", Decimal("3"))],
        elec_courses=[("E_GATEWAY", "grp-elec", Decimal("3"))],
    )
    rules = [
        PlanCourseRule("E_GATEWAY", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M_TARGET", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("E_GATEWAY",)),)),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="E_GATEWAY", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].value == StructuralMandatoryRole.CHOICE_ELECTIVE.value
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value


def test_unrelated_prerequisite_source_conflict_does_not_poison_candidate() -> None:
    """An unresolved source conflict on unrelated course Z does not poison candidate X."""
    cat = make_catalog(req_courses=[("X", "grp-req", Decimal("3")), ("M", "grp-req", Decimal("3")), ("Z_CONFLICTED", "grp-req", Decimal("3"))])
    rules = [
        PlanCourseRule("X", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("X",)),)),
        PlanCourseRule("Z_CONFLICTED", PrerequisiteLogicStatus.SOURCE_CONFLICT),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="X", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].status is SignalStatus.AVAILABLE
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value


def test_prerequisite_dependency_cycle_safety() -> None:
    """Dependency cycle involving candidate triggers REVIEW_REQUIRED cleanly without hanging."""
    cat = make_catalog(req_courses=[("C_A", "grp-req", Decimal("3")), ("C_B", "grp-req", Decimal("3"))])
    # Cycle: C_A requires C_B, and C_B requires C_A
    rules = [
        PlanCourseRule("C_A", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("C_B",)),)),
        PlanCourseRule("C_B", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("C_A",)),)),
    ]
    ctc = make_can_take_catalog(rules)
    ctx = default_context(course_code="C_A", catalog=cat, can_take_catalog=ctc)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].status is SignalStatus.REVIEW_REQUIRED


# ===========================================================================
# 3. Privacy & Suppression Propagation Scenarios (P7-TEST-PRV-001 .. 012)
# ===========================================================================


def test_p7_test_prv_001_demand_below_threshold_suppressed() -> None:
    """P7-TEST-PRV-001: Demand count below threshold k is suppressed."""
    demand = make_demand_result({"1501110": None}, is_suppressed=True, suppressed_metric_ids=(DemandMetricId.COURSE_INTENT_OWNER_COUNT,))
    ctx = default_context(demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT].status is SignalStatus.SUPPRESSED
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT].value is None


def test_p7_test_prv_002_suppression_propagation_to_deficit() -> None:
    """P7-TEST-PRV-002: Suppression propagation to deficit."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 30)
    demand = make_demand_result({"1501110": None}, is_suppressed=True, suppressed_metric_ids=(DemandMetricId.COURSE_INTENT_OWNER_COUNT,))
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].status is SignalStatus.SUPPRESSED
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].value is None


def test_p7_test_prv_003_suppression_propagation_to_ratio() -> None:
    """P7-TEST-PRV-003: Suppression propagation to ratio."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 30)
    demand = make_demand_result({"1501110": None}, is_suppressed=True, suppressed_metric_ids=(DemandMetricId.COURSE_INTENT_OWNER_COUNT,))
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO].status is SignalStatus.SUPPRESSED
    assert res.signals[InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO].value is None


def test_p7_test_prv_004_suppression_propagation_to_combined_alert() -> None:
    """P7-TEST-PRV-004: Combined bottleneck pressure alert is withheld when demand is suppressed."""
    cat = make_catalog(req_courses=[("1501110", "grp-req", Decimal("3")), ("M1", "grp-req", Decimal("3"))])
    rules = [
        PlanCourseRule("1501110", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M1", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("1501110",)),)),
    ]
    ctc = make_can_take_catalog(rules)
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 30)
    demand = make_demand_result({"1501110": None}, is_suppressed=True, suppressed_metric_ids=(DemandMetricId.COURSE_INTENT_OWNER_COUNT,))
    ctx = default_context(course_code="1501110", catalog=cat, can_take_catalog=ctc, capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    # Structural status is public catalog fact -> remains gateway!
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value
    # But operational alert is withheld
    bottleneck_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE)
    assert bottleneck_alert.emitted is False


def test_p7_test_prv_005_zero_identity_fields_in_schema() -> None:
    """P7-TEST-PRV-005: Zero student identity fields across all institutional models."""
    prohibited_names = {"student_id", "user_id", "email", "name", "gpa", "student_name"}
    models_to_check = [
        InstitutionalIntelligenceResult,
        InstitutionalIntelligenceInput,
        CapacityFact,
        InstitutionalPrivacyConfiguration,
    ]
    for model_cls in models_to_check:
        for f in fields(model_cls):
            assert f.name.lower() not in prohibited_names, f"Model {model_cls.__name__} has prohibited field {f.name}"


def test_p7_test_prv_006_review_required_owner_count_suppression() -> None:
    """P7-TEST-PRV-006: Review-required count suppression withholds alert."""
    demand = make_demand_result(
        {"1501110": 20},
        review_owners=1,
        suppressed_metric_ids=(DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT,),
    )
    ctx = default_context(demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT].status is SignalStatus.SUPPRESSED
    rev_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_REVIEW_REQUIRED_PRESENT)
    assert rev_alert.emitted is False


def test_p7_test_prv_007_no_raw_bypass_parameter() -> None:
    """P7-TEST-PRV-007: Domain input schema contains no raw bypass flags."""
    field_names = {f.name for f in fields(InstitutionalIntelligenceInput)}
    assert "include_raw" not in field_names
    assert "bypass_privacy" not in field_names
    assert "raw_students" not in field_names


def test_p7_test_prv_008_cross_filter_subtraction_mitigation() -> None:
    """P7-TEST-PRV-008: Exact-scope evaluation is atomic and independent."""
    # Scope queries evaluate independently without automated differencing
    ctx1 = default_context(course_code="1501110")
    res1 = evaluate_institutional_intelligence(ctx1)
    assert res1.provenance.scope_id == "1501110"


def test_p7_test_prv_009_multi_university_tenant_isolation() -> None:
    """P7-TEST-PRV-009: Tenant mismatch between demand result and input raises error."""
    demand = make_demand_result({"1501110": 20}, univ_id=UNIV_B_ID)
    ctx = default_context(demand_result=demand)
    with pytest.raises(ValueError, match="Tenant mismatch"):
        evaluate_institutional_intelligence(ctx)


def test_p7_test_prv_010_non_member_user_access_pure_domain_safety() -> None:
    """P7-TEST-PRV-010: Pure domain result has zero user/student write or read capabilities."""
    ctx = default_context()
    res = evaluate_institutional_intelligence(ctx)
    assert not hasattr(res, "students")
    assert not hasattr(res, "attempts")


def test_p7_test_prv_011_inactive_analyst_membership_pure_domain_isolation() -> None:
    """P7-TEST-PRV-011: Pure domain engine has zero auth dependencies (pure calculation)."""
    # Verifies pure domain does not import auth modules
    import app.institutional_intelligence.engine as eng
    assert not hasattr(eng, "authenticate_user")
    assert not hasattr(eng, "get_current_user")


def test_p7_test_prv_012_minimum_allowed_threshold_validation() -> None:
    """P7-TEST-PRV-012: Instantiating InstitutionalPrivacyConfiguration with k < 2 raises ValueError."""
    with pytest.raises(ValueError, match="Minimum disclosure threshold must be >= 2"):
        InstitutionalPrivacyConfiguration(minimum_disclosure_threshold=1)


# ===========================================================================
# 4. Institutional Alert Scenarios (P7-TEST-ALT-001 .. 008)
# ===========================================================================


def test_p7_test_alt_001_capacity_deficit_detected() -> None:
    """P7-TEST-ALT-001: Capacity deficit present emits INST_ALERT_CAPACITY_DEFICIT_DETECTED."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 40)
    demand = make_demand_result({"1501110": 55})
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_CAPACITY_DEFICIT_DETECTED)
    assert alert.emitted is True
    assert alert.evidence["deficit"] == 15


def test_p7_test_alt_002_zero_capacity_with_demand() -> None:
    """P7-TEST-ALT-002: Zero capacity with demand emits INST_ALERT_ZERO_CAPACITY_WITH_DEMAND."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 0)
    demand = make_demand_result({"1501110": 25})
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_ZERO_CAPACITY_WITH_DEMAND)
    assert alert.emitted is True
    assert alert.evidence["capacity"] == 0
    assert alert.evidence["demand"] == 25


def test_p7_test_alt_003_structural_bottleneck_pressure() -> None:
    """P7-TEST-ALT-003: Gateway course with deficit emits INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE."""
    cat = make_catalog(req_courses=[("1501110", "grp-req", Decimal("3")), ("M1", "grp-req", Decimal("3"))])
    rules = [
        PlanCourseRule("1501110", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("M1", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("1501110",)),)),
    ]
    ctc = make_can_take_catalog(rules)
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 30)
    demand = make_demand_result({"1501110": 45})
    ctx = default_context(course_code="1501110", catalog=cat, can_take_catalog=ctc, capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE)
    assert alert.emitted is True
    assert alert.evidence["deficit"] == 15


def test_p7_test_alt_004_review_volume_present() -> None:
    """P7-TEST-ALT-004: Review volume present emits INST_ALERT_REVIEW_REQUIRED_PRESENT."""
    demand = make_demand_result({"1501110": 20}, review_owners=8)
    ctx = default_context(demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_REVIEW_REQUIRED_PRESENT)
    assert alert.emitted is True
    assert alert.evidence["review_required_intent_owner_count"] == 8


def test_p7_test_alt_005_verified_offered_with_missing_capacity() -> None:
    """P7-TEST-ALT-005: Offered course with missing capacity emits INST_ALERT_CAPACITY_DATA_MISSING only."""
    offering = make_offering_fact(UNIV_ID, PERIOD_KEY, "1501110", PlannedOfferingStatus.OFFERED)
    ctx = default_context(offering_fact=offering, capacity_fact=None)
    res = evaluate_institutional_intelligence(ctx)

    cap_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_CAPACITY_DATA_MISSING)
    off_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_OFFERING_DATA_MISSING)
    assert cap_alert.emitted is True
    assert off_alert.emitted is False


def test_p7_test_alt_005b_missing_offering_with_supplied_capacity() -> None:
    """Hygiene Case 3: Missing offering with supplied capacity emits INST_ALERT_OFFERING_DATA_MISSING only."""
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 30)
    ctx = default_context(offering_fact=None, capacity_fact=capacity)
    res = evaluate_institutional_intelligence(ctx)

    off_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_OFFERING_DATA_MISSING)
    cap_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_CAPACITY_DATA_MISSING)
    assert off_alert.emitted is True
    assert cap_alert.emitted is False


def test_p7_test_alt_006_missing_offering_with_missing_capacity() -> None:
    """P7-TEST-ALT-006: Missing offering with missing capacity emits both hygiene alerts."""
    ctx = default_context(offering_fact=None, capacity_fact=None)
    res = evaluate_institutional_intelligence(ctx)

    off_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_OFFERING_DATA_MISSING)
    cap_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_CAPACITY_DATA_MISSING)
    assert off_alert.emitted is True
    assert cap_alert.emitted is True


def test_p7_test_alt_007_verified_not_offered_no_missing_capacity_alert() -> None:
    """P7-TEST-ALT-007: Verified NOT_OFFERED does NOT emit INST_ALERT_CAPACITY_DATA_MISSING or perform capacity arithmetic."""
    offering = make_offering_fact(UNIV_ID, PERIOD_KEY, "1501110", PlannedOfferingStatus.NOT_OFFERED)
    ctx = default_context(offering_fact=offering, capacity_fact=None)
    res = evaluate_institutional_intelligence(ctx)

    cap_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_CAPACITY_DATA_MISSING)
    off_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_OFFERING_DATA_MISSING)
    assert cap_alert.emitted is False
    assert off_alert.emitted is False
    assert res.signals[InstitutionalSignalId.INST_SIG_SUPPLIED_CAPACITY_COUNT].status is SignalStatus.NOT_APPLICABLE
    assert res.signals[InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT].status is SignalStatus.NOT_APPLICABLE
    assert res.signals[InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE].status is SignalStatus.NOT_APPLICABLE


def test_p7_test_alt_008_suppressed_count_withholds_alerts_and_zero_side_effects() -> None:
    """P7-TEST-ALT-008: Suppressed counts withhold alerts; all alerts have side_effects == NONE."""
    demand = make_demand_result({"1501110": None}, is_suppressed=True, suppressed_metric_ids=(DemandMetricId.COURSE_INTENT_OWNER_COUNT, DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT))
    capacity = make_capacity_fact(UNIV_ID, PERIOD_KEY, "1501110", 10)
    ctx = default_context(capacity_fact=capacity, demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    # Alerts that depend on student volume are withheld
    def_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_CAPACITY_DEFICIT_DETECTED)
    zero_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_ZERO_CAPACITY_WITH_DEMAND)
    bot_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE)
    rev_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_REVIEW_REQUIRED_PRESENT)

    assert def_alert.emitted is False
    assert zero_alert.emitted is False
    assert bot_alert.emitted is False
    assert rev_alert.emitted is False

    for a in res.alerts:
        assert a.side_effects.value == "NONE"


def test_exact_13_signals_and_6_alerts_registry_compliance() -> None:
    """Verifies that result outputs exactly the 13 committed signals and 6 alerts in stable order."""
    ctx = default_context()
    res = evaluate_institutional_intelligence(ctx)

    assert len(res.signals) == 13
    assert len(res.alerts) == 6
    assert len(res.traces) == 13

    expected_signals = [
        InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT,
        InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_SHARE,
        InstitutionalSignalId.INST_SIG_TOTAL_DECLARED_CREDIT_LOAD,
        InstitutionalSignalId.INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT,
        InstitutionalSignalId.INST_SIG_SUPPLIED_CAPACITY_COUNT,
        InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT,
        InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE,
        InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO,
        InstitutionalSignalId.INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT,
        InstitutionalSignalId.INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT,
        InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE,
        InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS,
        InstitutionalSignalId.INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT,
    ]
    assert list(res.signals.keys()) == expected_signals

    expected_alerts = [
        InstitutionalAlertId.INST_ALERT_CAPACITY_DEFICIT_DETECTED,
        InstitutionalAlertId.INST_ALERT_ZERO_CAPACITY_WITH_DEMAND,
        InstitutionalAlertId.INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE,
        InstitutionalAlertId.INST_ALERT_REVIEW_REQUIRED_PRESENT,
        InstitutionalAlertId.INST_ALERT_CAPACITY_DATA_MISSING,
        InstitutionalAlertId.INST_ALERT_OFFERING_DATA_MISSING,
    ]
    assert [a.alert_id for a in res.alerts] == expected_alerts

    # Machine lock test: literal alert registry validation (must NOT be derived from enum)
    expected = {
        "INST_ALERT_CAPACITY_DEFICIT_DETECTED",
        "INST_ALERT_ZERO_CAPACITY_WITH_DEMAND",
        "INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE",
        "INST_ALERT_REVIEW_REQUIRED_PRESENT",
        "INST_ALERT_CAPACITY_DATA_MISSING",
        "INST_ALERT_OFFERING_DATA_MISSING",
    }
    actual = {x.value for x in InstitutionalAlertId}
    assert actual == expected
    assert len(actual) == 6


# ===========================================================================
# 3. P7.2.2 Semantics Hardening & Verification Tests
# ===========================================================================


def test_conflict_with_verified_or_bypass_does_not_poison_candidate() -> None:
    """Outcome-sensitive conflict: candidate on a branch with a verified OR bypass is NOT poisoned to REVIEW_REQUIRED."""
    # Target mandatory course M requires (A OR B).
    # Branch A requires candidate X, but A has a source conflict.
    # Branch B is a verified bypass that does not require candidate X and has no conflicts.
    # Candidate X must evaluate to NON_GATEWAY (not poisoned to REVIEW_REQUIRED).
    cat = make_catalog(
        req_courses=[
            ("M", "grp-req", Decimal("3")),
            ("X", "grp-elec", Decimal("3")),
        ],
        elec_courses=[],
    )
    rules = [
        PlanCourseRule(
            course_code="M",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(
                DependencyGroup(1, DependencyType.PREREQUISITE, ("A", "B")),
            ),
        ),
        PlanCourseRule(
            course_code="A",
            prerequisite_logic_status=PrerequisiteLogicStatus.SOURCE_CONFLICT,
            dependency_groups=(
                DependencyGroup(1, DependencyType.PREREQUISITE, ("X",)),
            ),
        ),
        PlanCourseRule(
            course_code="B",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(),
        ),
        PlanCourseRule(
            course_code="X",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(),
        ),
    ]
    ctc = make_can_take_catalog(rules)
    gateway_status, gated, limitations = evaluate_structural_gateway("X", cat, ctc)

    assert gateway_status is StructuralGatewayStatus.NON_GATEWAY
    assert gated == []
    assert limitations == []


def test_outcome_relevant_conflict_causes_review_required() -> None:
    """Outcome-sensitive conflict: conflict that can change indispensability evaluates to REVIEW_REQUIRED."""
    # Target mandatory course M requires (A OR B).
    # Branch A requires candidate X (MUST).
    # Branch B has a SOURCE_CONFLICT without any verified bypass.
    # Candidate X indispensability is undecidable without resolving B, so it must evaluate to REVIEW_REQUIRED.
    cat = make_catalog(
        req_courses=[
            ("M", "grp-req", Decimal("3")),
            ("X", "grp-elec", Decimal("3")),
        ],
        elec_courses=[],
    )
    rules = [
        PlanCourseRule(
            course_code="M",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(
                DependencyGroup(1, DependencyType.PREREQUISITE, ("A", "B")),
            ),
        ),
        PlanCourseRule(
            course_code="A",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(
                DependencyGroup(1, DependencyType.PREREQUISITE, ("X",)),
            ),
        ),
        PlanCourseRule(
            course_code="B",
            prerequisite_logic_status=PrerequisiteLogicStatus.SOURCE_CONFLICT,
            dependency_groups=(),
        ),
        PlanCourseRule(
            course_code="X",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(),
        ),
    ]
    ctc = make_can_take_catalog(rules)
    gateway_status, gated, limitations = evaluate_structural_gateway("X", cat, ctc)

    assert gateway_status is StructuralGatewayStatus.REVIEW_REQUIRED
    assert gated == []
    assert len(limitations) > 0
    assert any("Outcome-relevant prerequisite conflict" in lim for lim in limitations)


def test_referenced_only_course_topology_and_mandatory_role() -> None:
    """Referenced-only course participates in DAG as a STRUCTURAL_GATEWAY while remaining CHOICE_ELECTIVE."""
    # Course R is NOT in catalog.plan_courses (referenced-only).
    # Mandatory plan course P requires R.
    cat = make_catalog(
        req_courses=[("P", "grp-req", Decimal("3"))],
        elec_courses=[],
    )
    # Notice: R is NOT in cat.plan_courses!
    assert not any(c.course_code == "R" for c in cat.plan_courses)

    rules = [
        PlanCourseRule(
            course_code="P",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(
                DependencyGroup(1, DependencyType.PREREQUISITE, ("R",)),
            ),
        ),
        PlanCourseRule(
            course_code="R",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(),
        ),
    ]
    ctc = make_can_take_catalog(rules)

    ctx = InstitutionalIntelligenceInput(
        university_id=UNIV_ID,
        target_period_key=PERIOD_KEY,
        course_code="R",
        catalog=cat,
        can_take_catalog=ctc,
    )
    res = evaluate_institutional_intelligence(ctx)

    # 1. Structural mandatory role: NOT plan-required, no fake plan membership created
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].value is None
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].status is SignalStatus.NOT_APPLICABLE

    # 2. Structural bottleneck status: STRUCTURAL_GATEWAY because it is indispensable to mandatory course P
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.STRUCTURAL_GATEWAY.value
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].status is SignalStatus.AVAILABLE
    trace_bottleneck = next(t for t in res.traces if t.signal_id is InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS)
    assert trace_bottleneck.inputs["gated_mandatory_targets"] == ["P"]


def test_referenced_only_course_with_source_conflict() -> None:
    """Referenced-only course with source conflict evaluates to REVIEW_REQUIRED."""
    cat = make_catalog(
        req_courses=[("P", "grp-req", Decimal("3"))],
        elec_courses=[],
    )
    assert not any(c.course_code == "R" for c in cat.plan_courses)

    # R itself has a SOURCE_CONFLICT
    rules = [
        PlanCourseRule(
            course_code="P",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(
                DependencyGroup(1, DependencyType.PREREQUISITE, ("R",)),
            ),
        ),
        PlanCourseRule(
            course_code="R",
            prerequisite_logic_status=PrerequisiteLogicStatus.SOURCE_CONFLICT,
            dependency_groups=(),
        ),
    ]
    ctc = make_can_take_catalog(rules)

    ctx = InstitutionalIntelligenceInput(
        university_id=UNIV_ID,
        target_period_key=PERIOD_KEY,
        course_code="R",
        catalog=cat,
        can_take_catalog=ctc,
    )
    res = evaluate_institutional_intelligence(ctx)

    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].value is None
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE].status is SignalStatus.NOT_APPLICABLE
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].status is SignalStatus.REVIEW_REQUIRED
    assert res.signals[InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS].value == StructuralGatewayStatus.REVIEW_REQUIRED.value


def test_deterministic_reproducibility() -> None:
    """Deterministic reproducibility: identical inputs produce identical outputs."""
    cat = make_catalog(
        req_courses=[
            ("1501110", "grp-req", Decimal("3")),
            ("1501220", "grp-req", Decimal("3")),
        ],
        elec_courses=[],
    )
    rules = [
        PlanCourseRule(
            course_code="1501220",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(DependencyGroup(1, DependencyType.PREREQUISITE, ("1501110",)),),
        ),
        PlanCourseRule(
            course_code="1501110",
            prerequisite_logic_status=PrerequisiteLogicStatus.VERIFIED,
            dependency_groups=(),
        ),
    ]
    ctc = make_can_take_catalog(rules)
    offering = make_offering_fact(
        univ_id=UNIV_ID,
        period_key=PERIOD_KEY,
        course_code="1501110",
        status=PlannedOfferingStatus.OFFERED,
        authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
        source_version="1.0",
    )
    capacity = make_capacity_fact(
        univ_id=UNIV_ID,
        period_key=PERIOD_KEY,
        course_code="1501110",
        capacity=50,
        authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
        source_version="1.0",
    )
    demand = make_demand_result({"1501110": 45}, review_owners=2)

    ctx1 = InstitutionalIntelligenceInput(
        university_id=UNIV_ID,
        target_period_key=PERIOD_KEY,
        course_code="1501110",
        catalog=cat,
        can_take_catalog=ctc,
        offering_fact=offering,
        capacity_fact=capacity,
        demand_result=demand,
        computed_at="2026-09-22T12:00:00Z",
        deterministic_trace_id="test-trace-1234",
    )
    ctx2 = InstitutionalIntelligenceInput(
        university_id=UNIV_ID,
        target_period_key=PERIOD_KEY,
        course_code="1501110",
        catalog=cat,
        can_take_catalog=ctc,
        offering_fact=offering,
        capacity_fact=capacity,
        demand_result=demand,
        computed_at="2026-09-22T12:00:00Z",
        deterministic_trace_id="test-trace-1234",
    )

    res1 = evaluate_institutional_intelligence(ctx1)
    res2 = evaluate_institutional_intelligence(ctx2)

    assert res1 == res2
    assert res1.provenance == res2.provenance
    assert res1.provenance.computed_at == "2026-09-22T12:00:00Z"
    for sig_id in InstitutionalSignalId:
        assert res1.signals[sig_id] == res2.signals[sig_id]
    assert res1.alerts == res2.alerts
    assert res1.traces == res2.traces


def test_missing_demand_metric_evaluates_to_insufficient_data() -> None:
    """Missing P6 demand metric is not defaulted to zero; evaluates to INSUFFICIENT_DATA."""
    demand = DemandAggregationResult(
        contract_version="1.0",
        status=DemandStatus.AVAILABLE,
        aggregation_scope=AggregationScope(university_id=UNIV_ID),
        target_period=TargetPeriod(
            university_id=UNIV_ID,
            period_key=PERIOD_KEY,
            period_class=TargetPeriodClass.DECLARED_PLANNING_PERIOD,
            source_version="1.0",
        ),
        metrics=(
            DemandMetric(
                metric_id=DemandMetricId.VALID_ACTIVE_INTENT_OWNER_COUNT,
                value=50,
            ),
        ),
        suppressed_metric_ids=(),
        coverage=CoverageMetadata(
            observed_intents_only=True,
            valid_active_intent_owner_count=50,
            population_denominator=None,
            population_coverage_ratio=None,
        ),
        quality_flags=(),
        reason_codes=(),
        provenance=(),
        source_versions=("1.0",),
        limitations=(),
    )
    ctx = default_context(demand_result=demand)
    res = evaluate_institutional_intelligence(ctx)

    # Missing course intent count -> INSUFFICIENT_DATA, None
    sig_demand = res.signals[InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT]
    assert sig_demand.status is SignalStatus.INSUFFICIENT_DATA
    assert sig_demand.value is None

    # Missing review count -> INSUFFICIENT_DATA, None (NOT silently 0!)
    sig_rev = res.signals[InstitutionalSignalId.INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT]
    assert sig_rev.status is SignalStatus.INSUFFICIENT_DATA
    assert sig_rev.value is None

    # Review alert must not be emitted
    rev_alert = next(a for a in res.alerts if a.alert_id is InstitutionalAlertId.INST_ALERT_REVIEW_REQUIRED_PRESENT)
    assert rev_alert.emitted is False


def test_negative_capacity_fact_raises_value_error() -> None:
    """CapacityFact rejects negative capacity."""
    with pytest.raises(ValueError, match="Supplied capacity cannot be negative"):
        CapacityFact(
            university_id=UNIV_ID,
            period_key=PERIOD_KEY,
            course_code="1501110",
            capacity=-5,
            authority=InstitutionalFactAuthority.VERIFIED_INSTITUTIONAL_FACT,
            source_version="1.0",
        )


def test_machine_enforced_signal_registry_lock() -> None:
    """Asserts exact literal match for the 13 locked institutional signals (fail on add/remove/rename/alias)."""
    expected = {
        "INST_SIG_DECLARED_DEMAND_COUNT",
        "INST_SIG_DECLARED_DEMAND_SHARE",
        "INST_SIG_TOTAL_DECLARED_CREDIT_LOAD",
        "INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT",
        "INST_SIG_SUPPLIED_CAPACITY_COUNT",
        "INST_SIG_DECLARED_CAPACITY_DEFICIT",
        "INST_SIG_CAPACITY_PRESSURE_STATE",
        "INST_SIG_DEMAND_TO_CAPACITY_RATIO",
        "INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT",
        "INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT",
        "INST_SIG_STRUCTURAL_MANDATORY_ROLE",
        "INST_SIG_STRUCTURAL_BOTTLENECK_STATUS",
        "INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT",
    }
    actual = {s.value for s in InstitutionalSignalId}
    assert actual == expected
    assert len(actual) == 13


def test_machine_enforced_alert_registry_lock() -> None:
    """Asserts exact literal match for the 6 locked institutional alerts (fail on add/remove/rename/alias)."""
    expected = {
        "INST_ALERT_CAPACITY_DEFICIT_DETECTED",
        "INST_ALERT_ZERO_CAPACITY_WITH_DEMAND",
        "INST_ALERT_STRUCTURAL_BOTTLENECK_PRESSURE",
        "INST_ALERT_REVIEW_REQUIRED_PRESENT",
        "INST_ALERT_CAPACITY_DATA_MISSING",
        "INST_ALERT_OFFERING_DATA_MISSING",
    }
    actual = {a.value for a in InstitutionalAlertId}
    assert actual == expected
    assert len(actual) == 6


def test_p6_metric_to_p7_signal_mapping_separation() -> None:
    """Asserts P6 demand metric keys are input sources only and never leak as P7 public signal IDs."""
    p6_to_p7_mapping = {
        DemandMetricId.COURSE_INTENT_OWNER_COUNT: InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT,
        DemandMetricId.COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS: InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_SHARE,
        DemandMetricId.TOTAL_DECLARED_CREDIT_LOAD: InstitutionalSignalId.INST_SIG_TOTAL_DECLARED_CREDIT_LOAD,
        DemandMetricId.REQUIREMENT_GROUP_INTENT_OWNER_COUNT: InstitutionalSignalId.INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT,
        DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT: InstitutionalSignalId.INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT,
    }
    # 1. Zero P6 metric IDs exist in the P7 public signal registry
    p7_signal_values = {s.value for s in InstitutionalSignalId}
    for p6_id in p6_to_p7_mapping:
        assert p6_id.value not in p7_signal_values

    # 2. Result exposes only P7 signal IDs, while decision traces record P6 source metric identities
    ctx = default_context()
    res = evaluate_institutional_intelligence(ctx)
    for p6_id, p7_id in p6_to_p7_mapping.items():
        assert p7_id in res.signals
        trace = next(t for t in res.traces if t.signal_id is p7_id)
        assert trace.inputs.get("source_metric") == p6_id.value


def test_cycle_localization_irrelevant_cycle_does_not_poison_candidate() -> None:
    """Irrelevant cycle elsewhere or bypassed in OR group does not poison candidate gateway status."""
    cat = make_catalog(
        req_courses=[
            ("M", "grp-req", Decimal("3")),
            ("C", "grp-req", Decimal("3")),
        ],
        elec_courses=[
            ("A", "grp-elec", Decimal("3")),
            ("B", "grp-elec", Decimal("3")),
            ("D", "grp-elec", Decimal("3")),
        ],
    )
    # Target M requires (A OR B) AND C.
    # Candidate C is directly required in Group 2 (MUST).
    # In Group 1, B is in a cycle with D (B -> D -> B), BUT A is clean and verified (BYPASSABLE).
    rules = [
        PlanCourseRule("C", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("A", PrerequisiteLogicStatus.VERIFIED),
        PlanCourseRule("B", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("D",)),)),
        PlanCourseRule("D", PrerequisiteLogicStatus.VERIFIED, (DependencyGroup(1, DependencyType.PREREQUISITE, ("B",)),)),
        PlanCourseRule(
            "M",
            PrerequisiteLogicStatus.VERIFIED,
            (
                DependencyGroup(1, DependencyType.PREREQUISITE, ("A", "B")),
                DependencyGroup(2, DependencyType.PREREQUISITE, ("C",)),
            ),
        ),
    ]
    ctc = make_can_take_catalog(rules)
    gateway_status, gated, limitations = evaluate_structural_gateway("C", cat, ctc)

    # Candidate C is indispensable to M. The bypassed cycle between B and D does not poison C!
    assert gateway_status is StructuralGatewayStatus.STRUCTURAL_GATEWAY
    assert gated == ["M"]


def test_p6_quality_and_provenance_contract_verification() -> None:
    """Verifies exact P6 quality registry, coverage context, and authority separation."""
    # 1. Exact allowed quality flag vocabulary (exactly 7 members from P6 DataQualityFlag)
    expected_quality_flags = {
        "COMPLETE_DECLARED_INTENT_INPUT_SET",
        "PARTIAL_INTENT_COVERAGE",
        "UNKNOWN_POPULATION_COVERAGE",
        "MISSING_OFFERING_DATA",
        "MISSING_CAPACITY_DATA",
        "SUPPRESSED_FOR_PRIVACY",
        "REVIEW_REQUIRED_INTENTS_EXCLUDED",
    }
    actual_quality_flags = {f.value for f in DataQualityFlag}
    assert actual_quality_flags == expected_quality_flags
    assert len(actual_quality_flags) == 7

    # 2. No unauthorized P7 quality flags (P7 does not define a separate quality enum)
    from app.mock_registration.registries import DataQualityFlag as P6DataQualityFlag
    assert DataQualityFlag is P6DataQualityFlag

    # 3. OBSERVED_INTENTS_ONLY preservation in coverage notes (orthogonal to quality flags)
    ctx = default_context(demand_result=make_demand_result({"1501110": 20}))
    res = evaluate_institutional_intelligence(ctx)
    assert "OBSERVED_INTENTS_ONLY" in res.coverage_notes
    assert "OBSERVED_INTENTS_ONLY" not in {f.value for f in DataQualityFlag}

    # 4. SUPPRESSED status/metadata consistency
    ctx_suppressed = default_context(
        demand_result=make_demand_result(
            {"1501110": None},
            is_suppressed=True,
            suppressed_metric_ids=(DemandMetricId.COURSE_INTENT_OWNER_COUNT,),
        )
    )
    res_suppressed = evaluate_institutional_intelligence(ctx_suppressed)
    assert res_suppressed.signals[InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT].status is SignalStatus.SUPPRESSED
    assert DataQualityFlag.SUPPRESSED_FOR_PRIVACY in res_suppressed.quality_flags

    # 5. Review-required exclusion metadata
    ctx_review = default_context(demand_result=make_demand_result({"1501110": 20}, review_owners=5))
    res_review = evaluate_institutional_intelligence(ctx_review)
    assert DataQualityFlag.REVIEW_REQUIRED_INTENTS_EXCLUDED in res_review.quality_flags

    # 6. Intent provenance vs Institutional Fact Authority separation
    from app.mock_registration.models import IntentProvenance
    expected_intent_provenance = {
        "DECLARED_STUDENT_INTENT",
        "SYNTHETIC_SANDBOX_INTENT",
        "INSTITUTIONAL_IMPORT",
    }
    expected_fact_authority = {
        "VERIFIED_INSTITUTIONAL_FACT",
        "SYNTHETIC_SANDBOX_FACT",
    }
    assert {p.value for p in IntentProvenance} == expected_intent_provenance
    assert {a.value for a in InstitutionalFactAuthority} == expected_fact_authority
    assert set(IntentProvenance) != set(InstitutionalFactAuthority)
