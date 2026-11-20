"""Round days (Tue/Sat/Sun, never Fri) and the Mozzart budget priority."""
from __future__ import annotations

import datetime as dt

from pipeline.fixtures import ROUND_WEEKDAYS, round_dates_for
from pipeline.mozzart import client

# 2026-11-20 is a Friday.
FRI = dt.date(2026, 11, 20)
SAT = dt.date(2026, 11, 21)
SUN = dt.date(2026, 11, 22)
MON = dt.date(2026, 11, 23)
TUE = dt.date(2026, 11, 24)


def test_round_days_are_tuesday_saturday_sunday() -> None:
    assert TUE.weekday() in ROUND_WEEKDAYS
    assert SAT.weekday() in ROUND_WEEKDAYS
    assert SUN.weekday() in ROUND_WEEKDAYS
    assert FRI.weekday() not in ROUND_WEEKDAYS


def test_friday_run_publishes_both_weekend_rounds() -> None:
    assert round_dates_for(FRI) == [SAT, SUN]


def test_saturday_retries_saturday_and_sunday() -> None:
    assert round_dates_for(SAT) == [SAT, SUN]


def test_sunday_run_only_touches_sunday() -> None:
    assert round_dates_for(SUN) == [SUN]


def test_tuesday_run_only_touches_tuesday() -> None:
    assert round_dates_for(TUE) == [TUE]


def test_monday_settles_the_weekend() -> None:
    assert round_dates_for(MON) == [SAT, SUN]


def test_saturday_is_always_tried() -> None:
    assert client.may_fetch("saturday", 89, 90, SAT, 16)[0] is True
    assert client.may_fetch("saturday", 90, 90, SAT, 16)[0] is False


def test_budget_skips_tuesday_before_sunday() -> None:
    # With 30 requests left, Sunday is still affordable (leaves 16 for Sat 28),
    # but Tuesday is not (it must also leave 8 for Sun 29).
    assert client.may_fetch("sunday", 60, 90, SUN, 8)[0] is True
    assert client.may_fetch("tuesday", 60, 90, TUE, 8)[0] is False


def test_budget_skips_sunday_when_saturday_reserve_is_gone() -> None:
    assert client.may_fetch("sunday", 70, 90, SUN, 8)[0] is False


def test_run_model_uses_the_current_ranking_api() -> None:
    import inspect

    from pipeline import ranking, run_model

    # The teams/upcoming block once called rank_rows(band=...) with a removed name.
    assert "DEFAULT_BAND" not in inspect.getsource(run_model)
    assert "band" not in inspect.signature(ranking.rank_rows).parameters
