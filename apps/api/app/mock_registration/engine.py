"""Pure P6.2 orchestration entry points."""

from .aggregation import aggregate_institutional_demand
from .resolution import resolve_current_intents
from .validation import validate_registration_intent

__all__ = [
    "aggregate_institutional_demand",
    "resolve_current_intents",
    "validate_registration_intent",
]
