"""Round selection: only Tuesday and Saturday, always in the future / recent past."""
from __future__ import annotations

import datetime as dt

import pytest

from pipeline.fixtures import Fixture, current_or_next_round_date, fixtures_for_date, last_saturday, next_round_date


def make(day: int, month: int = 11, year: int = 2026, div: str = "E2") -> Fixture:
    return Fixture(div=div, date=dt.date(year, month, day), time="15:00", home="A", away="B", odds={})


def test_next_round_is_the_next_tuesday_or_saturday() -> None:
    wednesday = dt.date(2026, 11, 18)
    assert wednesday.weekday() == 2
    assert next_round_date(wednesday) == dt.date(2026, 11, 21)

    saturday = dt.date(2026, 11, 21)
    assert next_round_date(saturday) == dt.date(2026, 11, 24)

    monday = dt.date(2026, 11, 23)
    assert next_round_date(monday) == dt.date(2026, 11, 24)


def test_next_round_is_always_tuesday_or_saturday_and_in_the_future() -> None:
    start = dt.date(2026, 11, 1)
    for offset in range(0, 60):
        today = start + dt.timedelta(days=offset)
        candidate = next_round_date(today)
        assert candidate.weekday() in (1, 5)
        assert candidate > today
        assert (candidate - today).days <= 7


def test_retry_days_target_today() -> None:
    # A Saturday morning retry must target that same Saturday, not the next Tuesday.
    assert current_or_next_round_date(dt.date(2026, 11, 21)) == dt.date(2026, 11, 21)
    assert current_or_next_round_date(dt.date(2026, 11, 24)) == dt.date(2026, 11, 24)
    assert current_or_next_round_date(dt.date(2026, 11, 18)) == dt.date(2026, 11, 21)
    assert current_or_next_round_date(dt.date(2026, 11, 20)) == dt.date(2026, 11, 21)


def test_last_saturday_is_a_past_saturday() -> None:
    assert last_saturday(dt.date(2026, 11, 18)) == dt.date(2026, 11, 14)
    assert last_saturday(dt.date(2026, 11, 21)) == dt.date(2026, 11, 14)
    assert last_saturday(dt.date(2026, 11, 22)) == dt.date(2026, 11, 21)
    assert last_saturday(dt.date(2026, 11, 16)).weekday() == 5


def test_fixtures_for_date_filters_date_and_division() -> None:
    pool = [make(21), make(21, div="E1"), make(22), make(24)]
    selected = fixtures_for_date(pool, dt.date(2026, 11, 21), {"E2"})
    assert len(selected) == 1
    assert selected[0].div == "E2"
    assert fixtures_for_date(pool, dt.date(2026, 11, 21)) == pool[:2]


def test_a_monday_fixture_can_never_be_in_a_round() -> None:
    round_date = next_round_date(dt.date(2026, 11, 18))
    monday = dt.date(2026, 11, 23)
    assert monday.weekday() == 0
    assert fixtures_for_date([make(23)], round_date) == []


@pytest.mark.parametrize("day", [14, 17, 18, 19, 20, 21])
def test_round_dates_are_never_weekdays_other_than_tue_sat(day: int) -> None:
    assert next_round_date(dt.date(2026, 11, day)).weekday() in (1, 5)
