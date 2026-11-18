"""Leakage tests: no future data and no closing odds may influence a prediction."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from pipeline.model import live
from pipeline.model.goals_engine import extract_targets
from pipeline.parse import Match


def make_match(day: int, home: str, away: str, fthg: int, ftag: int, hthg: int, htag: int, odds=None) -> Match:
    return Match(
        season="2024-25",
        date=dt.date(2024, 8, 1) + dt.timedelta(days=day),
        home=home,
        away=away,
        fthg=fthg,
        ftag=ftag,
        hthg=hthg,
        htag=htag,
        odds=odds or {},
    )


def synthetic_matches(seed: int = 7) -> list[Match]:
    rng = np.random.default_rng(seed)
    teams = ["A", "B", "C", "D", "E", "F", "G", "H"]
    matches = []
    for day in range(0, 200, 3):
        for index in range(0, len(teams), 2):
            home = teams[index]
            away = teams[index + 1]
            fthg = int(rng.integers(0, 4))
            ftag = int(rng.integers(0, 4))
            matches.append(make_match(day, home, away, fthg, ftag, fthg // 2, ftag // 2))
    return matches


def predict(matches: list[Match], cutoff: dt.date, odds=None):
    predictor = live.build_predictor(matches, cutoff, half_life=365.0, k=10.0)
    return predictor.probabilities(["A"], ["B"], [odds or {}])["full"][0]


def test_prediction_ignores_matches_from_the_fixture_date_onwards() -> None:
    matches = synthetic_matches()
    cutoff = dt.date(2024, 8, 1) + dt.timedelta(days=120)

    base = predict(matches, cutoff)

    truncated = [match for match in matches if match.date < cutoff]
    assert predict(truncated, cutoff) == pytest.approx(base, abs=0.0)

    altered = [
        match if match.date < cutoff else make_match((match.date - dt.date(2024, 8, 1)).days, match.home, match.away, 6, 0, 3, 0)
        for match in matches
    ]
    assert predict(altered, cutoff) == pytest.approx(base, abs=0.0)


def test_closing_odds_columns_are_never_read() -> None:
    prematch = {"PSH": 2.1, "PSD": 3.4, "PSA": 3.6, "P>2.5": 1.9, "P<2.5": 1.9}
    closing = {"PSC>2.5": 1.1, "PSC<2.5": 9.9, "PSCH": 1.2, "PSCD": 9.0, "PSCA": 15.0}

    targets_plain = extract_targets(prematch)
    targets_with_closing = extract_targets({**prematch, **closing})
    assert targets_plain == targets_with_closing

    matches = synthetic_matches()
    cutoff = dt.date(2024, 8, 1) + dt.timedelta(days=150)
    assert predict(matches, cutoff, prematch) == pytest.approx(predict(matches, cutoff, {**prematch, **closing}), abs=0.0)


def test_training_window_excludes_the_cutoff_day_itself() -> None:
    matches = synthetic_matches()
    cutoff = dt.date(2024, 8, 1) + dt.timedelta(days=90)
    predictor = live.build_predictor(matches, cutoff, half_life=365.0, k=10.0)
    expected = sum(1 for match in matches if match.date < cutoff)
    assert predictor.trained_matches == expected


def test_power_demargin_removes_the_margin() -> None:
    from pipeline.model.goals_engine import power_demargin

    probabilities = power_demargin([1 / 2.1, 1 / 3.4, 1 / 3.6])
    assert probabilities.sum() == pytest.approx(1.0, abs=1e-9)
    assert probabilities[0] > probabilities[1]
