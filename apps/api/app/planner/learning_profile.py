"""Versioned, deterministic Plan 12 workload estimates; never LLM classified."""

from dataclasses import dataclass

MODEL_VERSION = "MODELED_COURSE_LOAD_PROFILE_V1"
MAX_MEMORIZATION_HEAVY = 2
MEMORIZATION_HEAVY_THRESHOLD = 70

# Exact codes from the supported Plan 12 seed, not name/substring inference.
# Only clearly reading/memorization-oriented curriculum is marked heavy.
_MEMORIZATION_HEAVY_CODES = frozenset({
    "0200104", "0200110", "0200111", "0200113", "0200114",
    "0200122", "0200125", "0200127", "0200130", "0200156",
})
_PRACTICAL_CODES = frozenset({
    "1501111", "1501113", "1506181", "1505367", "1505467", "1505468",
})


@dataclass(frozen=True)
class CourseLearningProfile:
    course_code: str
    memorization_score: int | None
    primary_type: str
    provenance: str
    version: str = MODEL_VERSION

    @property
    def memorization_heavy(self) -> bool:
        return self.memorization_score is not None and self.memorization_score >= MEMORIZATION_HEAVY_THRESHOLD


def resolve_learning_profile(code: str, *, plan_id: str) -> CourseLearningProfile:
    if plan_id != "10000000-0000-0000-0000-000000000005":
        return CourseLearningProfile(code, None, "UNKNOWN", "MODELED_FALLBACK")
    if code in _MEMORIZATION_HEAVY_CODES:
        return CourseLearningProfile(code, 80, "MEMORIZATION", "CURATED_PLAN12_CODE_MAPPING")
    if code in _PRACTICAL_CODES:
        return CourseLearningProfile(code, 10, "LAB_OR_PROJECT", "CURATED_PLAN12_CODE_MAPPING")
    return CourseLearningProfile(code, None, "UNKNOWN", "MODELED_FALLBACK")
