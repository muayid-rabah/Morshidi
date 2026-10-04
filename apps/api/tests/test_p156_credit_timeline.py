"""Deterministic Jordan-style credit-only projection boundaries."""

from decimal import Decimal
import pytest

from app.degree_path.credit_timeline import AcademicTerm, simulate_credit_timeline


def simulate(load=15, summer=0, *, earned=60, required=132, term=AcademicTerm.FIRST_SEMESTER):
    return simulate_credit_timeline(
        required=Decimal(required), earned=Decimal(earned), regular_load=Decimal(load),
        summer_enabled=summer > 0, summer_load=Decimal(summer),
        start_year=2026, start_term=term,
    )


@pytest.mark.parametrize("load", [12, 15, 18])
def test_regular_load_choices_are_deterministic_and_credit_exact(load):
    result = simulate(load)
    assert result == simulate(load)
    assert sum((row.planned_credits for row in result.terms), Decimal(0)) == 72
    assert result.terms[-1].remaining_after == 0
    assert all(row.term is not AcademicTerm.SUMMER for row in result.terms)
    assert result.summer_count == 0
    assert "cannot guarantee graduation" in result.warnings[0]
    assert "90-credit" in result.warnings[1]


@pytest.mark.parametrize("summer", [3, 9])
def test_summer_bounds_and_term_order(summer):
    result = simulate(15, summer)
    assert [row.term for row in result.terms[:3]] == [
        AcademicTerm.FIRST_SEMESTER, AcademicTerm.SECOND_SEMESTER, AcademicTerm.SUMMER]
    assert all(Decimal(3) <= row.planned_credits <= Decimal(9)
               for row in result.terms if row.term is AcademicTerm.SUMMER)


@pytest.mark.parametrize("summer", [2, 10])
def test_invalid_summer_rejected(summer):
    with pytest.raises(ValueError):
        simulate_credit_timeline(required=Decimal(132), earned=Decimal(60),
            regular_load=Decimal(15), summer_enabled=True, summer_load=Decimal(summer),
            start_year=2026, start_term=AcademicTerm.FIRST_SEMESTER)


def test_partial_final_regular_term_and_too_small_summer_remainder():
    result = simulate(15, 6, earned=119, required=132,
                      term=AcademicTerm.SECOND_SEMESTER)
    assert len(result.terms) == 1 and result.terms[0].planned_credits == 13
    tiny = simulate(12, 6, earned=118, required=132,
                    term=AcademicTerm.SECOND_SEMESTER)
    assert [row.term for row in tiny.terms] == [
        AcademicTerm.SECOND_SEMESTER, AcademicTerm.FIRST_SEMESTER]
    assert tiny.terms[-1].planned_credits == 2


def test_no_summer_requires_zero_and_no_course_feasibility_claim():
    with pytest.raises(ValueError):
        simulate_credit_timeline(required=Decimal(132), earned=Decimal(60),
            regular_load=Decimal(12), summer_enabled=False, summer_load=Decimal(3),
            start_year=2026, start_term=AcademicTerm.FIRST_SEMESTER)
    result = simulate(12, 0)
    assert "course availability" in result.warnings[0]
