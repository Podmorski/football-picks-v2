"""Picker rules: excluded outcomes, probability cap, sample minimums, agreement."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from pipeline.fixtures import Fixture
from pipeline.outcomes import OUTCOMES
from pipeline.picks import EXCLUDED, build_round, confidence_badge

INDEX = {outcome.id: position for position, outcome in enumerate(OUTCOMES)}
SIZE = len(OUTCOMES)


def vector(**overrides: float) -> np.ndarray:
    values = np.full(SIZE, 0.05)
    for outcome_id, value in overrides.items():
        values[INDEX[outcome_id]] = value
    return values


class StubCounts:
    def __init__(self) -> None:
        self.home_hits = np.zeros((3, SIZE))
        self.home_counts = np.array([10.0, 10.0, 0.0])
        self.away_hits = np.zeros((3, SIZE))
        self.away_counts = np.array([10.0, 10.0, 0.0])
        self.league_counts = np.full(SIZE, 500)

    def league_rates(self) -> np.ndarray:
        return np.full(SIZE, 0.35)


class StubPredictor:
    def __init__(self, full, counts=None, odds=None, n_home=None, n_away=None) -> None:
        self.full = full
        self.counts_p = counts if counts is not None else full
        self.odds_p = odds if odds is not None else full
        self.n_home = np.full(full.shape[0], 12.0) if n_home is None else np.asarray(n_home, dtype=float)
        self.n_away = np.full(full.shape[0], 13.0) if n_away is None else np.asarray(n_away, dtype=float)
        self.counts = StubCounts()
        self.team_index = {"A": 0, "B": 1}
        self.unknown_index = 2
        self.cutoff = dt.date(2026, 11, 18)
        self.trained_matches = 1000

    def probabilities(self, home, away, odds):
        return {
            "base": self.full,
            "counts": self.counts_p,
            "goals": self.odds_p,
            "odds": self.odds_p,
            "full": self.full,
            "n_home": self.n_home,
            "n_away": self.n_away,
        }


def fixtures(count: int = 1) -> list[Fixture]:
    return [
        Fixture(
            div="E2",
            date=dt.date(2026, 11, 21),
            time="15:00",
            home="A" if count == 1 else f"Home{index}",
            away="B" if count == 1 else f"Away{index}",
            odds={},
        )
        for index in range(count)
    ]


def test_never_picks_plain_home_or_away_win() -> None:
    full = np.vstack([vector(ft_1=0.62, ft_2=0.61, tg_3plus=0.44)])
    document = build_round(StubPredictor(full), fixtures(1), {"E2": "League One"}, dt.date(2026, 11, 21))
    picked = {pick["outcome"] for pick in document["picks"]}
    assert picked == {"tg_3plus"}
    assert not (picked & EXCLUDED)


def test_probability_cap_is_respected() -> None:
    full = np.vstack([vector(tg_3plus=0.70, ft_x=0.60)])
    document = build_round(StubPredictor(full), fixtures(1), {"E2": "League One"}, dt.date(2026, 11, 21))
    assert [pick["outcome"] for pick in document["picks"]] == ["ft_x"]


def test_nothing_picked_above_the_cap() -> None:
    full = np.full((1, SIZE), 0.9)
    document = build_round(StubPredictor(full), fixtures(1), {"E2": "League One"}, dt.date(2026, 11, 21))
    assert document["picks"] == []


def test_minimum_samples_are_enforced() -> None:
    full = np.vstack([vector(tg_3plus=0.55)])
    document = build_round(
        StubPredictor(full, n_home=[5.0]), fixtures(1), {"E2": "League One"}, dt.date(2026, 11, 21)
    )
    assert document["picks"] == []


def test_engines_must_agree() -> None:
    full = np.vstack([vector(tg_3plus=0.55)])
    counts = np.full_like(full, 0.90)  # every outcome disagrees by >= 0.10
    odds = full
    document = build_round(
        StubPredictor(full, counts=counts, odds=odds), fixtures(1), {"E2": "League One"}, dt.date(2026, 11, 21)
    )
    assert document["picks"] == []


def test_one_pick_per_match_and_top_n_cap() -> None:
    rows = [vector(tg_3plus=0.60), vector(tg_3plus=0.50), vector(tg_3plus=0.45)]
    full = np.vstack(rows)
    document = build_round(StubPredictor(full), fixtures(3), {"E2": "League One"}, dt.date(2026, 11, 21), config={"top_n": 2})
    assert len(document["picks"]) == 2
    pairs = [(pick["home"], pick["away"]) for pick in document["picks"]]
    assert len(pairs) == len(set(pairs))
    assert document["picks"][0]["probability"] >= document["picks"][1]["probability"]


def test_fair_odds_are_the_inverse_probability() -> None:
    full = np.vstack([vector(tg_3plus=0.40)])
    document = build_round(StubPredictor(full), fixtures(1), {"E2": "League One"}, dt.date(2026, 11, 21))
    pick = document["picks"][0]
    assert pick["fair_odds"] == pytest.approx(1 / 0.40, abs=0.01)
    assert pick["play"] == "3+ goals in the match"


def test_confidence_badge_thresholds() -> None:
    good_bin = {"bin": "55-60", "shown": 0.575, "n": 500, "landed": 0.58}
    assert confidence_badge(25, 0.02, good_bin, 100) == "High"
    assert confidence_badge(10, 0.02, good_bin, 100) == "Low"
    assert confidence_badge(25, 0.15, good_bin, 100) == "Low"
    assert confidence_badge(15, 0.06, None, 100) == "Medium"
