"""Public pure-domain surface for Mock Registration and Institutional Demand V1."""

from .aggregation import aggregate_institutional_demand
from .fingerprint import calculate_intent_fingerprint
from .models import *  # noqa: F403
from .registries import DataQualityFlag, DemandMetricId, ReasonCode
from .resolution import current_intent_key, resolve_current_intents
from .validation import validate_registration_intent

__all__ = [
    "aggregate_institutional_demand",
    "calculate_intent_fingerprint",
    "current_intent_key",
    "resolve_current_intents",
    "validate_registration_intent",
    "DataQualityFlag",
    "DemandMetricId",
    "ReasonCode",
]
