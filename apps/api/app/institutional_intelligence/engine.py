"""Pure-domain Institutional Intelligence evaluation engine."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.mock_registration.models import DemandAggregationResult, DemandMetricId, DemandStatus
from app.mock_registration.registries import DataQualityFlag

from .alerts import evaluate_institutional_alerts
from .capacity import evaluate_capacity_metrics
from .models import (
    CapacityFact,
    InstitutionalDecisionTrace,
    InstitutionalIntelligenceInput,
    InstitutionalIntelligenceResult,
    InstitutionalSignalResult,
    OfferingFact,
    SignalProvenance,
)
from .registries import (
    CapacityPressureState,
    InstitutionalAlertId,
    InstitutionalScopeType,
    InstitutionalSignalId,
    PlannedOfferingStatus,
    SignalStatus,
    StructuralGatewayStatus,
)
from .structure import (
    evaluate_mandatory_role,
    evaluate_structural_gateway,
    get_direct_downstream_courses,
    get_transitive_downstream_courses,
)
from .trace import build_decision_trace


def evaluate_institutional_intelligence(
    inputs: InstitutionalIntelligenceInput,
) -> InstitutionalIntelligenceResult:
    """Evaluates all 13 institutional signals and 6 alerts strictly in the pure domain.

    Zero I/O, zero database queries, zero network calls, zero clock/UUID calls,
    zero raw student data ingestion.
    """
    # -------------------------------------------------------------------------
    # 1. Input Safety & Tenant Isolation Validation
    # -------------------------------------------------------------------------
    univ_id = inputs.university_id
    period_key = inputs.target_period_key
    course_code = inputs.course_code

    # Resolve offering fact
    offering_fact = inputs.offering_fact
    if offering_fact is None and inputs.all_offering_facts:
        matching_offerings = [
            f
            for f in inputs.all_offering_facts
            if f.course_code == course_code and f.period_key == period_key
        ]
        if len(matching_offerings) > 1:
            # Check for conflict
            statuses = {f.status for f in matching_offerings}
            if len(statuses) > 1:
                raise ValueError(f"Conflicting offering facts found for course {course_code}")
            offering_fact = matching_offerings[0]
        elif matching_offerings:
            offering_fact = matching_offerings[0]

    if offering_fact is not None:
        if offering_fact.university_id != univ_id:
            raise ValueError(
                f"Tenant mismatch: offering fact university_id ({offering_fact.university_id}) "
                f"does not match input university_id ({univ_id})"
            )
        if offering_fact.period_key != period_key:
            raise ValueError(
                f"Period mismatch: offering fact period ({offering_fact.period_key}) "
                f"does not match input target_period ({period_key})"
            )
        if offering_fact.course_code != course_code:
            raise ValueError(
                f"Course mismatch: offering fact course ({offering_fact.course_code}) "
                f"does not match input course ({course_code})"
            )

    # Resolve capacity fact
    capacity_fact = inputs.capacity_fact
    if capacity_fact is None and inputs.all_capacity_facts:
        matching_capacities = [
            f
            for f in inputs.all_capacity_facts
            if f.course_code == course_code and f.period_key == period_key
        ]
        if inputs.study_plan_id is not None:
            plan_specific = [f for f in matching_capacities if f.study_plan_id == inputs.study_plan_id]
            if plan_specific:
                matching_capacities = plan_specific

        if len(matching_capacities) > 1:
            caps = {f.capacity for f in matching_capacities}
            if len(caps) > 1:
                raise ValueError(f"Conflicting capacity facts found for course {course_code}")
            capacity_fact = matching_capacities[0]
        elif matching_capacities:
            capacity_fact = matching_capacities[0]

    if capacity_fact is not None:
        if capacity_fact.university_id != univ_id:
            raise ValueError(
                f"Tenant mismatch: capacity fact university_id ({capacity_fact.university_id}) "
                f"does not match input university_id ({univ_id})"
            )
        if capacity_fact.period_key != period_key:
            raise ValueError(
                f"Period mismatch: capacity fact period ({capacity_fact.period_key}) "
                f"does not match input target_period ({period_key})"
            )
        if capacity_fact.course_code != course_code:
            raise ValueError(
                f"Course mismatch: capacity fact course ({capacity_fact.course_code}) "
                f"does not match input course ({course_code})"
            )

    # Validate demand result tenant & period if provided
    demand_res = inputs.demand_result
    if demand_res is not None:
        if demand_res.aggregation_scope.university_id != univ_id:
            raise ValueError(
                f"Tenant mismatch: demand result university_id ({demand_res.aggregation_scope.university_id}) "
                f"does not match input university_id ({univ_id})"
            )
        if demand_res.target_period.period_key != period_key:
            raise ValueError(
                f"Period mismatch: demand result period ({demand_res.target_period.period_key}) "
                f"does not match input target_period ({period_key})"
            )

    # -------------------------------------------------------------------------
    # 2. Extract Demand Metrics (P6 Demand Reuse)
    # -------------------------------------------------------------------------
    # 1. Declared Demand Count
    demand_count: int | None = None
    demand_status = SignalStatus.INSUFFICIENT_DATA
    demand_flags: list[DataQualityFlag] = []

    # 2. Declared Demand Share
    demand_share: Decimal | None = None
    demand_share_status = SignalStatus.INSUFFICIENT_DATA

    # 3. Total Declared Credit Load
    total_credit_load: Decimal | None = None
    credit_load_status = SignalStatus.INSUFFICIENT_DATA

    # 4. Requirement Group Demand Count
    req_group_demand: int | None = None
    req_group_status = SignalStatus.INSUFFICIENT_DATA

    # 13. Review-Required Intent Owner Count
    review_req_count: int | None = None
    review_req_status = SignalStatus.INSUFFICIENT_DATA

    coverage_notes: list[str] = []

    if demand_res is not None:
        coverage_notes.append("OBSERVED_INTENTS_ONLY")
        demand_flags.extend(demand_res.quality_flags)

        # Check whole-result or metric-level suppression
        is_whole_suppressed = demand_res.status is DemandStatus.SUPPRESSED

        # Find metric: COURSE_INTENT_OWNER_COUNT
        m_course = next(
            (
                m
                for m in demand_res.metrics
                if m.metric_id is DemandMetricId.COURSE_INTENT_OWNER_COUNT
                and m.course_code == course_code
            ),
            None,
        )

        if (
            is_whole_suppressed
            or DemandMetricId.COURSE_INTENT_OWNER_COUNT in demand_res.suppressed_metric_ids
            or (m_course is not None and m_course.value is None and is_whole_suppressed)
        ):
            demand_status = SignalStatus.SUPPRESSED
            demand_count = None
        elif m_course is not None and m_course.value is not None:
            demand_status = SignalStatus.AVAILABLE
            demand_count = int(m_course.value)
        else:
            demand_status = SignalStatus.INSUFFICIENT_DATA
            demand_count = None

        # Find metric: COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS
        m_share = next(
            (
                m
                for m in demand_res.metrics
                if m.metric_id is DemandMetricId.COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS
                and m.course_code == course_code
            ),
            None,
        )
        if (
            is_whole_suppressed
            or DemandMetricId.COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS in demand_res.suppressed_metric_ids
            or demand_status is SignalStatus.SUPPRESSED
        ):
            demand_share_status = SignalStatus.SUPPRESSED
            demand_share = None
        elif m_share is not None and m_share.value is not None:
            demand_share_status = SignalStatus.AVAILABLE
            demand_share = Decimal(str(m_share.value))
        elif demand_res.coverage.valid_active_intent_owner_count == 0:
            demand_share_status = SignalStatus.NOT_APPLICABLE
            demand_share = None
        else:
            demand_share_status = SignalStatus.INSUFFICIENT_DATA
            demand_share = None

        # Find metric: TOTAL_DECLARED_CREDIT_LOAD
        m_cred = next(
            (m for m in demand_res.metrics if m.metric_id is DemandMetricId.TOTAL_DECLARED_CREDIT_LOAD),
            None,
        )
        if (
            is_whole_suppressed
            or DemandMetricId.TOTAL_DECLARED_CREDIT_LOAD in demand_res.suppressed_metric_ids
        ):
            credit_load_status = SignalStatus.SUPPRESSED
            total_credit_load = None
        elif m_cred is not None and m_cred.value is not None:
            credit_load_status = SignalStatus.AVAILABLE
            total_credit_load = Decimal(str(m_cred.value))
        else:
            credit_load_status = SignalStatus.INSUFFICIENT_DATA
            total_credit_load = None

        # Find metric: REQUIREMENT_GROUP_INTENT_OWNER_COUNT
        # Locate requirement group for candidate course
        plan_course = next(
            (c for c in inputs.catalog.plan_courses if c.course_code == course_code),
            None,
        )
        req_group_id = plan_course.requirement_group_id if plan_course else None

        m_group = next(
            (
                m
                for m in demand_res.metrics
                if m.metric_id is DemandMetricId.REQUIREMENT_GROUP_INTENT_OWNER_COUNT
                and (m.requirement_group_id == req_group_id if req_group_id else True)
            ),
            None,
        )
        if (
            is_whole_suppressed
            or DemandMetricId.REQUIREMENT_GROUP_INTENT_OWNER_COUNT in demand_res.suppressed_metric_ids
        ):
            req_group_status = SignalStatus.SUPPRESSED
            req_group_demand = None
        elif m_group is not None and m_group.value is not None:
            req_group_status = SignalStatus.AVAILABLE
            req_group_demand = int(m_group.value)
        else:
            req_group_status = SignalStatus.INSUFFICIENT_DATA
            req_group_demand = None

        # Find metric: REVIEW_REQUIRED_INTENT_OWNER_COUNT
        m_review = next(
            (
                m
                for m in demand_res.metrics
                if m.metric_id is DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT
            ),
            None,
        )
        if (
            is_whole_suppressed
            or DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT in demand_res.suppressed_metric_ids
        ):
            review_req_status = SignalStatus.SUPPRESSED
            review_req_count = None
        elif m_review is not None and m_review.value is not None:
            review_req_status = SignalStatus.AVAILABLE
            review_req_count = int(m_review.value)
        else:
            review_req_status = SignalStatus.INSUFFICIENT_DATA
            review_req_count = None

    # -------------------------------------------------------------------------
    # 3. Capacity Metrics & State Machine
    # -------------------------------------------------------------------------
    (
        cap_res,
        deficit_res,
        pressure_res,
        ratio_res,
        cap_quality_flags,
    ) = evaluate_capacity_metrics(
        demand_count=demand_count,
        demand_status=demand_status,
        offering_fact=offering_fact,
        capacity_fact=capacity_fact,
    )

    all_quality_flags = tuple(sorted(set(demand_flags + list(cap_quality_flags)), key=lambda x: x.value))

    # -------------------------------------------------------------------------
    # 4. Prerequisite Structural Analysis (Catalog Facts: Immune to Suppression)
    # -------------------------------------------------------------------------
    # 9. Direct downstream count
    direct_downstream = get_direct_downstream_courses(course_code, inputs.can_take_catalog)
    direct_count = len(direct_downstream)

    # 10. Transitive downstream count
    transitive_downstream = get_transitive_downstream_courses(course_code, inputs.can_take_catalog)
    transitive_count = len(transitive_downstream)

    # 11. Structural mandatory role
    mandatory_role = evaluate_mandatory_role(course_code, inputs.catalog)

    # 12. Structural gateway status
    gateway_status, gated_targets, structural_limitations = evaluate_structural_gateway(
        course_code,
        inputs.catalog,
        inputs.can_take_catalog,
    )
    gateway_signal_status = (
        SignalStatus.REVIEW_REQUIRED
        if gateway_status is StructuralGatewayStatus.REVIEW_REQUIRED
        else SignalStatus.AVAILABLE
    )

    # -------------------------------------------------------------------------
    # 5. Alert Evaluation
    # -------------------------------------------------------------------------
    alerts = evaluate_institutional_alerts(
        demand_count=demand_count,
        demand_status=demand_status,
        capacity_fact=capacity_fact,
        offering_fact=offering_fact,
        deficit=deficit_res[1],
        deficit_status=deficit_res[0],
        pressure_state=pressure_res[1],
        gateway_status=gateway_status,
        review_required_count=review_req_count,
        review_required_status=review_req_status,
    )

    # Count data quality alerts
    dq_alert_count = sum(1 for a in alerts if a.category == "DATA_HYGIENE" and a.emitted)

    # -------------------------------------------------------------------------
    # 6. Build Stably Ordered Signal Results
    # -------------------------------------------------------------------------
    base_trace = (
        inputs.deterministic_trace_id
        if inputs.deterministic_trace_id is not None
        else f"{univ_id}:{period_key}:{course_code}"
    )
    base_trace = inputs.deterministic_trace_id
    signals: dict[InstitutionalSignalId, InstitutionalSignalResult] = {}
    traces: list[InstitutionalDecisionTrace] = []

    def _add_signal(
        sig_id: InstitutionalSignalId,
        status: SignalStatus,
        val: Any,
        unit: str,
        rule_id: str,
        trace_inputs: dict[str, Any],
        limitations: tuple[str, ...] = (),
    ) -> None:
        derived_trace_id = (
            f"{base_trace}:{sig_id.value}" if base_trace is not None else None
        )
        sig_result = InstitutionalSignalResult(
            signal_id=sig_id,
            status=status,
            value=val,
            unit=unit,
            quality_flags=all_quality_flags,
            trace_id=derived_trace_id,
        )
        signals[sig_id] = sig_result
        traces.append(
            build_decision_trace(
                base_trace_id=base_trace,
                signal_id=sig_id,
                rule_id=rule_id,
                inputs=trace_inputs,
                status=status,
                value=val,
                limitations=limitations,
            )
        )

    # 1. INST_SIG_DECLARED_DEMAND_COUNT
    _add_signal(
        InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_COUNT,
        demand_status,
        demand_count,
        "count",
        "P6_DEMAND_REUSE_COURSE_INTENT_OWNERS",
        {
            "source_metric": DemandMetricId.COURSE_INTENT_OWNER_COUNT.value,
            "course_code": course_code,
            "target_period": period_key,
        },
    )

    # 2. INST_SIG_DECLARED_DEMAND_SHARE
    _add_signal(
        InstitutionalSignalId.INST_SIG_DECLARED_DEMAND_SHARE,
        demand_share_status,
        demand_share,
        "share",
        "DEMAND_SHARE_CALCULATION",
        {
            "source_metric": DemandMetricId.COURSE_INTENT_SHARE_OF_VALID_INTENT_OWNERS.value,
            "course_code": course_code,
            "demand": demand_count,
        },
    )

    # 3. INST_SIG_TOTAL_DECLARED_CREDIT_LOAD
    _add_signal(
        InstitutionalSignalId.INST_SIG_TOTAL_DECLARED_CREDIT_LOAD,
        credit_load_status,
        total_credit_load,
        "credits",
        "TOTAL_CREDIT_LOAD_CALCULATION",
        {
            "source_metric": DemandMetricId.TOTAL_DECLARED_CREDIT_LOAD.value,
            "target_period": period_key,
        },
    )

    # 4. INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT
    _add_signal(
        InstitutionalSignalId.INST_SIG_REQUIREMENT_GROUP_DEMAND_COUNT,
        req_group_status,
        req_group_demand,
        "count",
        "REQUIREMENT_GROUP_DEMAND_CALCULATION",
        {
            "source_metric": DemandMetricId.REQUIREMENT_GROUP_INTENT_OWNER_COUNT.value,
            "course_code": course_code,
        },
    )

    # 5. INST_SIG_SUPPLIED_CAPACITY_COUNT
    _add_signal(
        InstitutionalSignalId.INST_SIG_SUPPLIED_CAPACITY_COUNT,
        cap_res[0],
        cap_res[1],
        "seats",
        "SUPPLIED_CAPACITY_FACT_RESOLUTION",
        {
            "course_code": course_code,
            "period_key": period_key,
            "offering_status": offering_fact.status.value if offering_fact else "UNAVAILABLE",
        },
    )

    # 6. INST_SIG_DECLARED_CAPACITY_DEFICIT
    _add_signal(
        InstitutionalSignalId.INST_SIG_DECLARED_CAPACITY_DEFICIT,
        deficit_res[0],
        deficit_res[1],
        "seats",
        "ARITHMETIC_CAPACITY_DEFICIT",
        {"demand": demand_count, "capacity": cap_res[1]},
    )

    # 7. INST_SIG_CAPACITY_PRESSURE_STATE
    _add_signal(
        InstitutionalSignalId.INST_SIG_CAPACITY_PRESSURE_STATE,
        pressure_res[0],
        pressure_res[1].value if pressure_res[1] else None,
        "state",
        "DETERMINISTIC_CAPACITY_PRESSURE_STATE_MACHINE",
        {"deficit": deficit_res[1], "demand_status": demand_status.value},
    )

    # 8. INST_SIG_DEMAND_TO_CAPACITY_RATIO
    _add_signal(
        InstitutionalSignalId.INST_SIG_DEMAND_TO_CAPACITY_RATIO,
        ratio_res[0],
        ratio_res[1],
        "ratio",
        "DEMAND_TO_CAPACITY_RATIO_CALCULATION",
        {"demand": demand_count, "capacity": cap_res[1]},
    )

    # 9. INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT
    _add_signal(
        InstitutionalSignalId.INST_SIG_DIRECT_DOWNSTREAM_PREREQUISITE_COUNT,
        SignalStatus.AVAILABLE,
        direct_count,
        "count",
        "DIRECT_PREREQUISITE_GRAPH_TRAVERSAL",
        {"candidate": course_code, "direct_downstream": direct_downstream},
    )

    # 10. INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT
    _add_signal(
        InstitutionalSignalId.INST_SIG_TRANSITIVE_DOWNSTREAM_DEPENDENCY_COUNT,
        SignalStatus.AVAILABLE,
        transitive_count,
        "count",
        "TRANSITIVE_CYCLE_SAFE_PREREQUISITE_TRAVERSAL",
        {"candidate": course_code, "transitive_downstream": transitive_downstream},
    )

    # 11. INST_SIG_STRUCTURAL_MANDATORY_ROLE
    if mandatory_role is None:
        role_status = SignalStatus.NOT_APPLICABLE
        role_val = None
    else:
        role_status = SignalStatus.AVAILABLE
        role_val = mandatory_role.value

    _add_signal(
        InstitutionalSignalId.INST_SIG_STRUCTURAL_MANDATORY_ROLE,
        role_status,
        role_val,
        "role",
        "STUDY_PLAN_REQUIREMENT_GROUP_ROLE_DERIVATION",
        {"course_code": course_code, "role": role_val},
    )

    # 12. INST_SIG_STRUCTURAL_BOTTLENECK_STATUS
    _add_signal(
        InstitutionalSignalId.INST_SIG_STRUCTURAL_BOTTLENECK_STATUS,
        gateway_signal_status,
        gateway_status.value,
        "status",
        "SOUND_BOOLEAN_AND_OR_NECESSITY_CLASSIFICATION",
        {
            "candidate": course_code,
            "transitive_downstream_count": transitive_count,
            "gated_mandatory_targets": gated_targets,
        },
        limitations=tuple(structural_limitations),
    )

    # 13. INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT
    _add_signal(
        InstitutionalSignalId.INST_SIG_REVIEW_REQUIRED_INTENT_OWNER_COUNT,
        review_req_status,
        review_req_count,
        "owners",
        "P6_DISTINCT_CURRENT_REVIEW_REQUIRED_INTENT_OWNERS",
        {
            "source_metric": DemandMetricId.REVIEW_REQUIRED_INTENT_OWNER_COUNT.value,
            "period_key": period_key,
        },
    )

    # -------------------------------------------------------------------------
    # 7. Provenance & Final Result Assembly
    # -------------------------------------------------------------------------
    provenance = SignalProvenance(
        university_id=univ_id,
        target_period_key=period_key,
        scope_type=InstitutionalScopeType.COURSE_SCOPE,
        scope_id=course_code,
        catalog_version=inputs.catalog.study_plan.study_plan_id,
        prerequisite_version=inputs.can_take_catalog.study_plan_id,
        demand_source_version=demand_res.contract_version if demand_res else "1.0",
        policy_version=inputs.policy_version,
        computed_at=inputs.computed_at,
    )

    return InstitutionalIntelligenceResult(
        contract_version=inputs.policy_version,
        university_id=univ_id,
        target_period_key=period_key,
        course_code=course_code,
        study_plan_id=inputs.study_plan_id,
        provenance=provenance,
        signals=signals,
        alerts=alerts,
        traces=tuple(traces),
        quality_flags=all_quality_flags,
        coverage_notes=tuple(sorted(set(coverage_notes))),
    )
