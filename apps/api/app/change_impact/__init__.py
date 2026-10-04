"""Analysis-only WC-046 proposed-change evaluator."""

from .engine import evaluate_change_impact
from .models import (
    ChangeDelta, ChangeImpactReport, ChangeType, CourseCreditHoursDelta,
    ImpactStatus, PolicyVersionDelta, PrerequisiteGroupDelta,
    RequirementGroupCreditDelta,
)

__all__ = [
    "ChangeDelta", "ChangeImpactReport", "ChangeType", "CourseCreditHoursDelta",
    "ImpactStatus", "PolicyVersionDelta", "PrerequisiteGroupDelta",
    "RequirementGroupCreditDelta", "evaluate_change_impact",
]
