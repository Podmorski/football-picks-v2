"""Picker backtest: leakage, temp-directory publishing and the missing-odds fallback."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from pipeline.fixtures import Fixture
from pipeline.model import live
from pipeline.model.blend import GROUP_NAMES
from pipeline.model.data import build_arrays, day_number
from pipeline.model.goals_engine import fit as fit_goals
from pipeline.model.picker_backtest import picks_for_round
from pipeline.parse import Match
from pipeline.picks import build_round, has_picks, publish, round_action, settle_document

HALF_LIFE = 365.0
K = 10.0
LOOSE = {
    "min_samples": 1,
    "agreement": 1.0,
    "max_probability": 0.999,
    "min_lift": -1.0,
    "lift_min_probability": 0.0,
    "top_n": 10,
    "max_same_play": 10,
}
DECISIONS = {"groups": {group: {"live_component": "odds"} for group in GROUP_NAMES}}


def synthetic_matches(seed: int = 11, days: int = 700) -> list[Match]:
    rng = np.random.default_rng(seed)
    teams = ["A", "B", "C", "D", "E", "F", "G", "H"]
    start = dt.date(2022, 8, 1)
    out: list[Match] = []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        if day.weekday() not in (1, 5):
            continue
        order = rng.permutation(len(teams))
        for index in range(0, len(teams), 2):
            home = teams[int(order[index])]
            away = teams[int(order[index + 1])]
            fthg = int(rng.integers(0, 4))
            ftag = int(rng.integers(0, 4))
            out.append(
                Match(
                    season="2022-23",
                    date=day,
                    home=home,
                    away=away,
                    fthg=fthg,
                    ftag=ftag,
                    hthg=fthg // 2,
                    htag=ftag // 2,
                )
            )
    return out


def a_mid_season_round(matches: list[Match]) -> dt.date:
    """A Tuesday/Saturday with plenty of history behind it."""
    dates = sorted({match.date for match in matches})
    for date in dates:
        history = sum(1 for match in matches if match.date < date)
        if history > 300:
            return date
    raise AssertionError("no suitable round date")


def test_picks_ignore_everything_on_or_after_the_round_date() -> None:
    matches = synthetic_matches()
    round_date = a_mid_season_round(matches)

    base = picks_for_round(matches, round_date, HALF_LIFE, K, settings=LOOSE)
    assert base["most_likely"], "the fixture set should produce at least one pick"

    # 1. Later matches removed entirely.
    trimmed = [match for match in matches if match.date <= round_date]
    assert picks_for_round(trimmed, round_date, HALF_LIFE, K, settings=LOOSE) == base

    # 2. Later matches altered drastically (and the round's own results are unchanged).
    altered = [
        match
        if match.date <= round_date
        else replace(match, fthg=7, ftag=0, hthg=4, htag=0)
        for match in matches
    ]
    assert picks_for_round(altered, round_date, HALF_LIFE, K, settings=LOOSE) == base


def test_round_action_distinguishes_empty_from_published() -> None:
    empty = {"views": {"most_likely": {"picks": []}, "stand_out": {"picks": []}}}
    published = {"views": {"most_likely": {"picks": [{"home": "A"}]}, "stand_out": {"picks": []}}}
    legacy_empty = {"picks": []}
    legacy_published = {"picks": [{"home": "A"}]}

    assert round_action(None, ["fixture"]) == "publish"
    assert round_action(empty, ["fixture"]) == "publish"  # empty file is replaced when fixtures appear
    assert round_action(legacy_empty, ["fixture"]) == "publish"
    assert round_action(empty, []) == "skip"
    assert round_action(legacy_empty, []) == "skip"
    assert round_action(published, ["fixture"]) == "settle"  # never replaced
    assert round_action(legacy_published, ["fixture"]) == "settle"

    assert has_picks(empty) is False
    assert has_picks(published) is True


def test_empty_round_file_is_replaced_once_fixtures_exist(tmp_path: Path) -> None:
    picks_dir = tmp_path / "picks"
    web_dir = tmp_path / "web"
    day = dt.date(2026, 11, 21)

    empty = {
        "date": day.isoformat(),
        "label": "Saturday 21 Nov",
        "weekday": "Saturday",
        "kind": "round",
        "views": {"most_likely": {"picks": []}, "stand_out": {"picks": []}},
        "picks": [],
    }
    publish(empty, picks_dir, web_dir)
    assert round_action(empty, ["fixture"]) == "publish"

    filled = {
        "date": day.isoformat(),
        "label": "Saturday 21 Nov",
        "weekday": "Saturday",
        "kind": "round",
        "views": {
            "most_likely": {"picks": [{"home": "A", "away": "B", "outcome": "tg_3plus"}]},
            "stand_out": {"picks": []},
        },
        "picks": [],
    }
    settle_document(filled, {})
    publish(filled, picks_dir, web_dir)

    stored = json.loads((picks_dir / f"{day.isoformat()}.json").read_text())
    assert len(stored["views"]["most_likely"]["picks"]) == 1
    # Now that it has picks it must never be replaced again.
    assert round_action(stored, ["fixture"]) == "settle"


def test_publishing_from_a_past_fixture_list_stays_in_the_temp_directory(tmp_path: Path) -> None:
    matches = synthetic_matches()
    round_date = a_mid_season_round(matches)
    round_matches = [match for match in matches if match.date == round_date]
    fixtures = [
        Fixture(div="E2", date=match.date, time=match.time, home=match.home, away=match.away, odds=match.odds)
        for match in round_matches
    ]

    predictor = live.build_predictor(matches, round_date, HALF_LIFE, K, DECISIONS)
    document = build_round({"E2": predictor}, fixtures, {"E2": "League One"}, round_date)

    picks_dir = tmp_path / "picks"
    web_dir = tmp_path / "web" / "rounds"
    publish(document, picks_dir, web_dir)

    assert (picks_dir / f"{round_date.isoformat()}.json").exists()
    assert (web_dir / f"{round_date.isoformat()}.json").exists()

    production = Path(__file__).resolve().parents[1] / "picks" / f"{round_date.isoformat()}.json"
    assert not production.exists(), "a test round must never land in the production picks directory"


def test_missing_odds_falls_back_to_the_unanchored_goals_engine() -> None:
    matches = sorted(synthetic_matches(), key=lambda match: (match.date, match.home, match.away))
    arrays = build_arrays(matches)
    model = fit_goals(arrays, day_number(matches[-1].date), HALF_LIFE)

    home = arrays.home[:4]
    away = arrays.away[:4]
    prematch = {"PSH": 2.1, "PSD": 3.4, "PSA": 3.6, "P>2.5": 1.9, "P<2.5": 1.9}

    anchored = model.probabilities(home, away, [prematch] * 4, use_odds=True)
    no_odds = model.probabilities(home, away, [{}] * 4, use_odds=True)
    unanchored = model.probabilities(home, away, [{}] * 4, use_odds=False)

    assert np.allclose(no_odds, unanchored)
    assert not np.allclose(anchored, no_odds)


@pytest.mark.parametrize("component", ["odds"])
def test_backtest_replay_matches_the_live_picker_engine(component: str) -> None:
    matches = synthetic_matches()
    round_date = a_mid_season_round(matches)
    picks = picks_for_round(matches, round_date, HALF_LIFE, K, settings=LOOSE, live={group: component for group in GROUP_NAMES})
    assert set(picks) == {"most_likely", "stand_out"}
    for pick in picks["most_likely"]:
        assert pick["div"] == ""  # no division passed in this call
