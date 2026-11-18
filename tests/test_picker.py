"""Picker rules for both views: exclusions, cap, sample minimums, agreement, lift, play cap."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from pipeline.fixtures import Fixture
from pipeline.outcomes import OUTCOMES
from pipeline.picks import EXCLUDED, build_round, confidence_badge, select_views

INDEX = {outcome.id: position for position, outcome in enumerate(OUTCOMES)}
SIZE = len(OUTCOMES)
ROUND = dt.date(2026, 11, 21)


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
        self.base = 0.35

    def league_rates(self) -> np.ndarray:
        return np.full(SIZE, self.base)


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


def fixtures(count: int = 1, odds=None) -> list[Fixture]:
    return [
        Fixture(
            div="E2",
            date=ROUND,
            time="15:00",
            home="A" if count == 1 else f"Home{index}",
            away="B" if count == 1 else f"Away{index}",
            odds=odds if odds is not None else {},
        )
        for index in range(count)
    ]


def build(predictor, count: int = 1, config=None, odds=None) -> dict:
    return build_round({"E2": predictor}, fixtures(count, odds), {"E2": "League One"}, ROUND, config=config)


def picks(document: dict, view: str = "most_likely") -> list[dict]:
    return document["views"][view]["picks"]


def test_never_picks_plain_home_or_away_win() -> None:
    document = build(StubPredictor(np.vstack([vector(ft_1=0.62, ft_2=0.61, tg_3plus=0.44)])))
    assert {pick["outcome"] for pick in picks(document)} == {"tg_3plus"}
    assert not ({pick["outcome"] for pick in picks(document)} & EXCLUDED)


def test_probability_cap_is_respected() -> None:
    document = build(StubPredictor(np.vstack([vector(tg_3plus=0.70, ft_x=0.60)])))
    assert [pick["outcome"] for pick in picks(document)] == ["ft_x"]


def test_nothing_picked_above_the_cap() -> None:
    assert picks(build(StubPredictor(np.full((1, SIZE), 0.9)))) == []


def test_minimum_samples_are_enforced() -> None:
    document = build(StubPredictor(np.vstack([vector(tg_3plus=0.55)]), n_home=[5.0]))
    assert picks(document) == []


def test_engines_must_agree() -> None:
    full = np.vstack([vector(tg_3plus=0.55)])
    document = build(StubPredictor(full, counts=np.full_like(full, 0.90)))
    assert picks(document) == []


def test_one_pick_per_match_and_top_n_cap() -> None:
    full = np.vstack([vector(tg_3plus=0.60), vector(tg_3plus=0.50), vector(tg_3plus=0.45)])
    document = build(StubPredictor(full), count=3, config={"top_n": 2})
    chosen = picks(document)
    assert len(chosen) == 2
    pairs = [(pick["home"], pick["away"]) for pick in chosen]
    assert len(pairs) == len(set(pairs))
    assert chosen[0]["probability"] >= chosen[1]["probability"]


def test_max_same_play_per_round() -> None:
    full = np.vstack([vector(tg_3plus=0.60)] * 5)
    document = build(StubPredictor(full), count=5)
    chosen = picks(document)
    assert len(chosen) == 3
    assert {pick["outcome"] for pick in chosen} == {"tg_3plus"}


def test_stand_out_needs_lift_and_band() -> None:
    # League base is 0.35, so lift = p - 0.35.
    full = np.vstack(
        [
            vector(tg_3plus=0.64),  # lift 0.29 - in band
            vector(btts_yes=0.46),  # lift 0.11 - in band
            vector(ht_x=0.44),  # lift 0.09 but below the 0.45 floor
            vector(c1=0.52),  # lift 0.17 - in band
        ]
    )
    document = build(StubPredictor(full), count=4)

    most = picks(document, "most_likely")
    stand = picks(document, "stand_out")
    assert len(most) == 4
    assert {pick["outcome"] for pick in stand} == {"tg_3plus", "btts_yes", "c1"}
    assert stand[0]["outcome"] == "tg_3plus"
    assert stand[0]["lift"] == pytest.approx(0.29, abs=1e-4)
    assert stand[0]["league_base"] == pytest.approx(0.35, abs=1e-6)


def test_stand_out_ranks_by_lift_not_probability() -> None:
    predictor = StubPredictor(np.vstack([vector(ht_x=0.50), vector(btts_yes=0.62)]))
    document = build(predictor, count=2)
    stand = picks(document, "stand_out")
    assert [pick["outcome"] for pick in stand] == ["btts_yes", "ht_x"]  # 0.27 lift before 0.15
    assert stand[0]["lift"] > stand[1]["lift"]


def test_stand_out_excludes_low_lift() -> None:
    full = np.vstack([vector(tg_3plus=0.40)])  # 0.05 lift, below min_lift 0.08
    document = build(StubPredictor(full))
    assert picks(document, "stand_out") == []


def test_fair_odds_are_the_inverse_probability() -> None:
    document = build(StubPredictor(np.vstack([vector(tg_3plus=0.40)])))
    pick = picks(document)[0]
    assert pick["fair_odds"] == pytest.approx(1 / 0.40, abs=0.01)
    assert pick["play"] == "3+ goals in the match"


def test_no_odds_is_flagged_and_caps_the_badge() -> None:
    calibration = {"groups": {"Total goals": {"bins": [{"bin": "60-65", "shown": 0.625, "landed": 0.63, "n": 500}] * 12}}}
    full = np.vstack([vector(tg_3plus=0.60)])
    document = build(StubPredictor(full, n_home=[25.0], n_away=[25.0]), odds={}, config=None)
    pick = picks(document)[0]
    assert pick["no_odds"] is True
    assert pick["confidence"] in {"Medium", "Low"}


def test_confidence_badge_thresholds() -> None:
    good_bin = {"bin": "55-60", "shown": 0.575, "n": 500, "landed": 0.58}
    assert confidence_badge(25, 0.02, good_bin, 100) == "High"
    assert confidence_badge(10, 0.02, good_bin, 100) == "Low"
    assert confidence_badge(25, 0.15, good_bin, 100) == "Low"
    assert confidence_badge(15, 0.06, None, 100) == "Medium"


def test_most_likely_requires_lift_zero_or_better() -> None:
    # League base is 0.35: 0.30 is below the usual rate and must not be published as "most likely".
    full = np.vstack([vector(tg_3plus=0.30, btts_yes=0.36)])
    document = build(StubPredictor(full))
    assert [pick["outcome"] for pick in picks(document)] == ["btts_yes"]


def test_most_likely_falls_back_to_nothing_when_every_play_is_below_base() -> None:
    full = np.vstack([vector(tg_3plus=0.30, btts_yes=0.31)])
    assert picks(build(StubPredictor(full))) == []


def test_both_views_are_stored() -> None:
    document = build(StubPredictor(np.vstack([vector(tg_3plus=0.60, btts_yes=0.50)])))
    assert set(document["views"]) == {"most_likely", "stand_out"}
    assert document["views"]["most_likely"]["label"] == "Most likely"
    assert document["views"]["stand_out"]["label"] == "Stand-out"
    assert document["picks"] == document["views"]["most_likely"]["picks"]
