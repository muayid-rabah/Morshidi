"""Deterministic credit-only projection; never a course-feasibility decision."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class AcademicTerm(str, Enum):
    FIRST_SEMESTER = "FIRST_SEMESTER"
    SECOND_SEMESTER = "SECOND_SEMESTER"
    SUMMER = "SUMMER"


@dataclass(frozen=True)
class CreditTerm:
    academic_year: int
    term: AcademicTerm
    planned_credits: Decimal
    remaining_after: Decimal


@dataclass(frozen=True)
class CreditTimeline:
    policy_version: str
    total_required_credits: Decimal
    earned_credits: Decimal
    initial_remaining_credits: Decimal
    regular_load: Decimal
    summer_enabled: bool
    summer_load: Decimal
    terms: tuple[CreditTerm, ...]
    regular_semester_count: int
    summer_count: int
    completion_year: int | None
    completion_term: AcademicTerm | None
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]


class ComparisonMode(str, Enum):
    FASTEST = "FASTEST"
    BALANCED = "BALANCED"
    LOWER_LOAD = "LOWER_LOAD"


@dataclass(frozen=True)
class CreditComparisonScenario:
    scenario_id: str
    mode: ComparisonMode
    timeline: CreditTimeline
    total_modeled_terms: int
    workload_indicator: str
    preference_match: bool
    provenance: str = "MODELED_ACADEMIC_CALENDAR"
    difficulty_evidence: str = "NO_FUTURE_COURSE_ALLOCATION"
    confidence: str = "MODELED_CREDIT_ONLY"
    current_workload_risk: int | None = None


@dataclass(frozen=True)
class CreditComparison:
    policy_version: str
    scenarios: tuple[CreditComparisonScenario, ...]
    evaluated_scenarios: int
    limitations: tuple[str, ...]


_TERM_ORDER = (AcademicTerm.FIRST_SEMESTER, AcademicTerm.SECOND_SEMESTER, AcademicTerm.SUMMER)


def compare_credit_timelines(*, required: Decimal, earned: Decimal,
                             start_year: int, start_term: AcademicTerm,
                             preferred_regular_load: Decimal | None = None,
                             preferred_summer_load: Decimal | None = None,
                             preferred_summer_enabled: bool | None = None,
                             graduation_pace: ComparisonMode | None = None,
                             current_workload_risk: int | None = None,
                             difficulty_evidence: str = "NO_FUTURE_COURSE_ALLOCATION") -> CreditComparison:
    """Rank 12 presets plus at most 8 explicit-preference variants."""
    if preferred_regular_load is not None and (not preferred_regular_load.is_finite() or
                                               not 3 <= preferred_regular_load <= 30):
        raise ValueError("Invalid compared regular-load preference")
    if preferred_summer_load is not None and not 3 <= preferred_summer_load <= 9:
        raise ValueError("Invalid compared summer-load preference")
    if preferred_summer_enabled is not None and not isinstance(preferred_summer_enabled, bool):
        raise ValueError("Invalid compared summer participation preference")
    if current_workload_risk is not None and (isinstance(current_workload_risk, bool) or
            not isinstance(current_workload_risk, int) or not 0 <= current_workload_risk <= 100):
        raise ValueError("Invalid current workload evidence")
    if graduation_pace is not None and not isinstance(graduation_pace, ComparisonMode):
        raise ValueError("Invalid graduation pace")
    summer_presets = sorted({Decimal(0), Decimal(3), Decimal(6), Decimal(9)} |
                            ({preferred_summer_load} if preferred_summer_load is not None else set()))
    regular_presets = sorted({Decimal(12), Decimal(15), Decimal(18)} |
                             ({preferred_regular_load} if preferred_regular_load is not None else set()))
    candidates = tuple(simulate_credit_timeline(
        required=required, earned=earned, regular_load=Decimal(regular),
        summer_enabled=summer > 0, summer_load=Decimal(summer),
        start_year=start_year, start_term=start_term,
    ) for regular in regular_presets for summer in summer_presets)

    def modeled_terms(item: CreditTimeline) -> int:
        if not item.terms:
            return 0
        last = item.terms[-1]
        return ((last.academic_year - start_year) * 3 +
                _TERM_ORDER.index(last.term) - _TERM_ORDER.index(start_term) + 1)

    def balance_cost(item: CreditTimeline) -> Decimal:
        # Explicit workload-versus-duration tradeoff, not a course/cognitive forecast.
        regular_excess = max(Decimal(0), item.regular_load - 12)
        caution = 1 + Decimal(current_workload_risk or 0) / 100
        return (Decimal(modeled_terms(item)) * 4 + caution * (
                regular_excess * regular_excess / 3 + item.summer_load * item.summer_load / 12))

    def preference_distance(item: CreditTimeline) -> Decimal:
        return (abs(item.regular_load - preferred_regular_load) if preferred_regular_load is not None else Decimal(0)) + (
            Decimal(10) if preferred_summer_enabled is not None and item.summer_enabled != preferred_summer_enabled else Decimal(0)) + (
            abs(item.summer_load - preferred_summer_load) if preferred_summer_load is not None and preferred_summer_enabled is not False else Decimal(0))

    fastest = min(candidates, key=lambda item: (modeled_terms(item), item.regular_load,
                                                item.summer_load))
    balanced = min(candidates, key=lambda item: (preference_distance(item), balance_cost(item), modeled_terms(item),
                                                 item.regular_load, item.summer_load))
    lower_load = min(candidates, key=lambda item: (item.regular_load, item.summer_load,
                                                   modeled_terms(item)))

    def view(mode: ComparisonMode, item: CreditTimeline) -> CreditComparisonScenario:
        has_preferences = any(value is not None for value in (preferred_regular_load,
            preferred_summer_enabled, preferred_summer_load, graduation_pace))
        matches = (has_preferences and (graduation_pace is None or mode == graduation_pace)
                   and (preferred_regular_load is None or item.regular_load == preferred_regular_load)
                   and (preferred_summer_enabled is None or item.summer_enabled == preferred_summer_enabled)
                   and (preferred_summer_load is None or not item.summer_enabled
                        or item.summer_load == preferred_summer_load))
        indicator = ("HIGH" if item.regular_load >= 18 or item.summer_load >= 9 else
                     "MODERATE" if item.regular_load >= 15 or item.summer_enabled else "LOWER")
        return CreditComparisonScenario(
            f"REGULAR_{format(item.regular_load.normalize(), 'f')}_SUMMER_{format(item.summer_load.normalize(), 'f')}", mode, item,
            modeled_terms(item), indicator, matches, difficulty_evidence=difficulty_evidence,
            current_workload_risk=current_workload_risk)

    return CreditComparison(
        "P15_6_CREDIT_COMPARISON_V1",
        (view(ComparisonMode.FASTEST, fastest), view(ComparisonMode.BALANCED, balanced),
         view(ComparisonMode.LOWER_LOAD, lower_load)), len(candidates),
        ("Credit-only scenarios do not assign future courses; personalized difficulty and cognitive balance cannot be safely projected.",
         "Balanced uses current eligible-course workload evidence only as a caution factor; stated load preferences take precedence in that view.",
         "Modeled First/Second/Summer term sequence and student-supplied start are not an approved institutional calendar.",
         "Prerequisites, availability, capacity, failures and the 90-credit AI Project rule may change completion."),
    )


def simulate_credit_timeline(*, required: Decimal, earned: Decimal, regular_load: Decimal,
                             summer_enabled: bool, summer_load: Decimal,
                             start_year: int, start_term: AcademicTerm) -> CreditTimeline:
    if (any(not isinstance(value, Decimal) or not value.is_finite() for value in
            (required, earned, regular_load, summer_load)) or required < 0 or earned < 0
            or regular_load < 3 or regular_load > 30 or not isinstance(summer_enabled, bool)
            or (summer_enabled and not 3 <= summer_load <= 9)
            or (not summer_enabled and summer_load != 0)
            or not 2000 <= start_year <= 2200 or not isinstance(start_term, AcademicTerm)):
        raise ValueError("Invalid credit-only planning assumption")
    remaining = max(Decimal(0), required - earned)
    initial = remaining
    year, term = start_year, start_term
    entries: list[CreditTerm] = []
    while remaining:
        if term is not AcademicTerm.SUMMER or (summer_enabled and remaining >= 3):
            cap = summer_load if term is AcademicTerm.SUMMER else regular_load
            take = min(remaining, cap)
            remaining -= take
            entries.append(CreditTerm(year, term, take, remaining))
        if term is AcademicTerm.FIRST_SEMESTER:
            term = AcademicTerm.SECOND_SEMESTER
        elif term is AcademicTerm.SECOND_SEMESTER:
            term = AcademicTerm.SUMMER
        else:
            term = AcademicTerm.FIRST_SEMESTER
            year += 1
        if len(entries) > 200:
            raise ValueError("Credit projection exceeded bounded horizon")
    final = entries[-1] if entries else None
    return CreditTimeline(
        "P15_6_CREDIT_TIMELINE_V1", required, earned, initial, regular_load,
        summer_enabled, summer_load, tuple(entries),
        sum(row.term is not AcademicTerm.SUMMER for row in entries),
        sum(row.term is AcademicTerm.SUMMER for row in entries),
        final.academic_year if final else None, final.term if final else None,
        ("Regular load is a planning assumption, not an institutional registration limit.",
         "Starting academic year/term is supplied by the student, not an authoritative calendar."),
        ("Credit-only projection cannot guarantee graduation or course availability.",
         "Prerequisites, offerings, failures, capacity and the 90-credit AI Project rule may change the timeline."),
    )
