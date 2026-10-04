"""Versioned labels for the existing, closed P7 institutional signal registry."""

from __future__ import annotations

from dataclasses import dataclass

from app.institutional_intelligence.registries import InstitutionalSignalId


METRIC_CATALOG_VERSION = "WC039_METRIC_CATALOG_V1"


@dataclass(frozen=True)
class InstitutionalMetricDefinition:
    metric_id: InstitutionalSignalId
    catalog_version: str
    label_ar: str
    label_en: str
    description_ar: str
    description_en: str
    expected_unit: str
    permitted_scope: str
    source_service: str = "InstitutionalIntelligenceService"
    suppression_sensitive: bool = False
    limitations: tuple[str, ...] = ()


_LABELS = (
    ("الطلب المعلن على المادة", "Declared course demand", "count", True),
    ("حصة المادة من الطلب المعلن", "Declared demand share", "share", True),
    ("إجمالي الساعات المعلنة", "Total declared credit load", "credits", True),
    ("الطلب على مجموعة المتطلبات", "Requirement-group demand", "count", True),
    ("السعة الموردة", "Supplied capacity", "seats", False),
    ("عجز السعة المعلنة", "Declared capacity deficit", "seats", True),
    ("حالة ضغط السعة", "Capacity pressure state", "state", True),
    ("نسبة الطلب إلى السعة", "Demand-to-capacity ratio", "ratio", True),
    ("عدد المتطلبات اللاحقة المباشرة", "Direct downstream prerequisites", "count", False),
    ("عدد التبعيات اللاحقة", "Transitive downstream dependencies", "count", False),
    ("الدور الإلزامي البنيوي", "Structural mandatory role", "role", False),
    ("حالة الاختناق البنيوي", "Structural bottleneck status", "status", False),
    ("عدد أصحاب النية التي تتطلب مراجعة", "Review-required intent owners", "owners", True),
)

METRIC_CATALOG = tuple(
    InstitutionalMetricDefinition(
        metric_id=metric_id,
        catalog_version=METRIC_CATALOG_VERSION,
        label_ar=label_ar,
        label_en=label_en,
        description_ar=f"مؤشر مؤسسي حتمي: {label_ar}؛ ضمن مادة وخطة وفترة محددة.",
        description_en=f"Deterministic institutional signal: {label_en}, for one course, plan and period.",
        expected_unit=unit,
        permitted_scope="AUTHORIZED_UNIVERSITY_PERIOD_PLAN_COURSE",
        suppression_sensitive=sensitive,
        limitations=("OBSERVED_INTENTS_ONLY",) if sensitive else (),
    )
    for metric_id, (label_ar, label_en, unit, sensitive)
    in zip(InstitutionalSignalId, _LABELS, strict=True)
)

METRICS_BY_ID = {definition.metric_id.value: definition for definition in METRIC_CATALOG}
