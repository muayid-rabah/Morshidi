"""Pure-domain Institutional Intelligence Package (Phase P7.2).

Closed 13-signal registry, closed 6-alert registry, capacity pressure state machine,
sound transitive AND/OR necessity analysis, and deterministic privacy-preserving signals.
"""

from __future__ import annotations

from .alerts import evaluate_institutional_alerts
from .capacity import evaluate_capacity_metrics
from .engine import evaluate_institutional_intelligence
from .models import (
    CapacityFact,
    InstitutionalAlertResult,
    InstitutionalDecisionTrace,
    InstitutionalIntelligenceInput,
    InstitutionalIntelligenceResult,
    InstitutionalPrivacyConfiguration,
    InstitutionalSignalResult,
    OfferingFact,
    SignalProvenance,
)
from .registries import (
    AlertSideEffect,
    CapacityPressureState,
    InstitutionalAlertId,
    InstitutionalFactAuthority,
    InstitutionalScopeType,
    InstitutionalSignalId,
    PlannedOfferingStatus,
    SignalStatus,
    StructuralGatewayStatus,
    StructuralMandatoryRole,
    INSTITUTIONAL_ALERT_REGISTRY,
    INSTITUTIONAL_SIGNAL_REGISTRY,
)
from .structure import (
    evaluate_mandatory_role,
    evaluate_structural_gateway,
    get_direct_downstream_courses,
    get_individually_mandatory_courses,
    get_transitive_downstream_courses,
    is_course_individually_mandatory,
)
from .trace import build_decision_trace

__all__ = [
    # Engine
    "evaluate_institutional_intelligence",
    "evaluate_capacity_metrics",
    "evaluate_structural_gateway",
    "evaluate_institutional_alerts",
    "build_decision_trace",
    # Registries & Enums
    "InstitutionalSignalId",
    "InstitutionalAlertId",
    "SignalStatus",
    "CapacityPressureState",
    "StructuralGatewayStatus",
    "StructuralMandatoryRole",
    "PlannedOfferingStatus",
    "AlertSideEffect",
    "InstitutionalFactAuthority",
    "InstitutionalScopeType",
    "INSTITUTIONAL_SIGNAL_REGISTRY",
    "INSTITUTIONAL_ALERT_REGISTRY",
    # Models
    "OfferingFact",
    "CapacityFact",
    "InstitutionalSignalResult",
    "InstitutionalAlertResult",
    "InstitutionalDecisionTrace",
    "SignalProvenance",
    "InstitutionalPrivacyConfiguration",
    "InstitutionalIntelligenceInput",
    "InstitutionalIntelligenceResult",
    # Structural functions
    "get_direct_downstream_courses",
    "get_transitive_downstream_courses",
    "get_individually_mandatory_courses",
    "is_course_individually_mandatory",
    "evaluate_mandatory_role",
]
