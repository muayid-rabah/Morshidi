"""Bounded, deterministic, credit-only strategy comparison."""

from decimal import Decimal

import pytest

from app.degree_path.credit_timeline import (AcademicTerm, ComparisonMode,
                                             compare_credit_timelines)


def compare(**changes):
    params = dict(required=Decimal(132), earned=Decimal(60), start_year=2026,
                  start_term=AcademicTerm.FIRST_SEMESTER)
    params.update(changes)
    return compare_credit_timelines(**params)


def test_three_distinct_named_views_are_deterministic_and_bounded():
    result = compare()
    assert result == compare()
    assert result.evaluated_scenarios == 12
    assert tuple(row.mode for row in result.scenarios) == tuple(ComparisonMode)
    assert all(row.timeline.initial_remaining_credits == 72 for row in result.scenarios)
    assert all(row.provenance == "MODELED_ACADEMIC_CALENDAR" for row in result.scenarios)
    assert all(row.difficulty_evidence == "NO_FUTURE_COURSE_ALLOCATION" for row in result.scenarios)
    assert any("Prerequisites" in note for note in result.limitations)


def test_fastest_and_lower_load_priorities_are_explicit_not_universal_best():
    fastest, balanced, lower = compare().scenarios
    assert fastest.total_modeled_terms <= balanced.total_modeled_terms
    assert fastest.total_modeled_terms <= lower.total_modeled_terms
    assert lower.timeline.regular_load == 12
    assert lower.timeline.summer_load == 0
    assert balanced.mode is ComparisonMode.BALANCED
    assert balanced.timeline.regular_load in (12, 15, 18)


def test_preference_match_and_summer_arithmetic():
    result = compare(preferred_regular_load=Decimal(15), preferred_summer_enabled=True,
                     preferred_summer_load=Decimal(6))
    assert result.scenarios[1].preference_match
    for row in result.scenarios:
        assert row.preference_match == (row.timeline.regular_load == 15
                                        and row.timeline.summer_load == 6)
        assert row.timeline.summer_load == 0 or 3 <= row.timeline.summer_load <= 9


def test_absent_preferences_never_claim_a_match_and_current_difficulty_only_informs_balance():
    assert not any(row.preference_match for row in compare().scenarios)
    cautious = compare(current_workload_risk=95, difficulty_evidence="CURRENT_ELIGIBLE_COURSES_ONLY")
    assert cautious.scenarios[1].timeline.regular_load <= compare().scenarios[1].timeline.regular_load
    assert cautious.scenarios[0].timeline == compare().scenarios[0].timeline
    assert cautious == compare(current_workload_risk=95, difficulty_evidence="CURRENT_ELIGIBLE_COURSES_ONLY")


def test_custom_summer_preference_remains_bounded_and_pace_match_is_not_universal_best():
    result = compare(preferred_regular_load=Decimal(15), preferred_summer_enabled=True,
                     preferred_summer_load=Decimal(4), graduation_pace=ComparisonMode.BALANCED)
    assert result.evaluated_scenarios == 15
    assert result.scenarios[1].timeline.summer_load == 4
    assert result.scenarios[1].preference_match
    assert not result.scenarios[0].preference_match


@pytest.mark.parametrize("invalid", [Decimal(2), Decimal(10)])
def test_invalid_summer_preference_is_rejected(invalid):
    with pytest.raises(ValueError):
        compare(preferred_summer_load=invalid)


@pytest.mark.parametrize("regular", [12, 15, 18])
@pytest.mark.parametrize("summer", [0, 3, 9])
def test_presets_are_valid_credit_timelines(regular, summer):
    from app.degree_path.credit_timeline import simulate_credit_timeline
    timeline = simulate_credit_timeline(
        required=Decimal(132), earned=Decimal(60), regular_load=Decimal(regular),
        summer_enabled=summer > 0, summer_load=Decimal(summer),
        start_year=2026, start_term=AcademicTerm.FIRST_SEMESTER)
    assert sum(term.planned_credits for term in timeline.terms) == 72
