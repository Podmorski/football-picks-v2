"""Outcome registry checked against hand-made scorelines."""
from __future__ import annotations

import datetime as dt

import pytest

from pipeline.outcomes import OUTCOMES, OUTCOMES_BY_ID, evaluate, result
from pipeline.parse import Match


def hits(fthg: int, ftag: int, hthg: int | None, htag: int | None) -> set[str]:
    return {outcome.id for outcome in OUTCOMES if outcome.fn(fthg, ftag, hthg, htag)}


CASES = [
    (
        "goalless draw",
        (0, 0, 0, 0),
        {
            "ft_x", "ht_x", "htft_xx", "dc_1x", "dc_x2", "tg_0_1",
            "ou_u15", "ou_u25", "ou_u35", "btts_no", "even", "mg_eq",
        },
    ),
    (
        "1-0, goalless first half",
        (1, 0, 0, 0),
        {
            "ft_1", "ht_x", "htft_x1", "dc_1x", "dc_12", "tg_0_1", "tg_1plus",
            "ou_u15", "ou_u25", "ou_u35", "btts_no", "odd", "mg_2h",
            "h2_1plus", "home_1plus",
        },
    ),
    (
        "2-2, 1-1 at half-time",
        (2, 2, 1, 1),
        {
            "ft_x", "ht_x", "htft_xx", "dc_1x", "dc_x2",
            "tg_4_6", "tg_1plus", "tg_2plus", "tg_3plus", "tg_4plus",
            "ou_o15", "ou_o25", "ou_o35", "btts_yes", "btts_1h", "even", "mg_eq",
            "h1_1plus", "h1_2plus", "h2_1plus", "h2_2plus",
            "home_1plus", "home_2plus", "away_1plus", "away_2plus",
            "home_1h_1plus", "away_1h_1plus", "home_both_halves", "away_both_halves",
            "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9", "c10",
        },
    ),
    (
        "half-time lead reversed",
        (1, 2, 1, 0),
        {
            "ft_2", "ht_1", "htft_12", "dc_x2", "dc_12",
            "tg_1plus", "tg_2plus", "tg_3plus", "tg_2_3",
            "ou_o15", "ou_o25", "ou_u35", "btts_yes", "odd", "mg_2h",
            "h1_1plus", "h2_1plus", "h2_2plus",
            "home_1plus", "away_1plus", "away_2plus", "home_1h_1plus",
            "c2", "c4", "c6", "c7", "c8", "c10",
        },
    ),
    (
        "two goals in the first half only",
        (2, 1, 2, 0),
        {
            "ft_1", "ht_1", "htft_11", "dc_1x", "dc_12",
            "tg_1plus", "tg_2plus", "tg_3plus", "tg_2_3",
            "ou_o15", "ou_o25", "ou_u35", "btts_yes", "odd", "mg_1h",
            "h1_1plus", "h1_2plus", "h2_1plus",
            "home_1plus", "home_2plus", "away_1plus", "home_1h_1plus",
            "c1", "c3", "c4", "c5", "c7", "c10",
        },
    ),
    (
        "3-3, 1-1 at half-time",
        (3, 3, 1, 1),
        {
            "ft_x", "ht_x", "htft_xx", "dc_1x", "dc_x2",
            "tg_4_6", "tg_1plus", "tg_2plus", "tg_3plus", "tg_4plus", "tg_5plus",
            "ou_o15", "ou_o25", "ou_o35", "btts_yes", "btts_1h", "even", "mg_2h",
            "h1_1plus", "h1_2plus", "h2_1plus", "h2_2plus",
            "home_1plus", "home_2plus", "away_1plus", "away_2plus",
            "home_1h_1plus", "away_1h_1plus", "home_both_halves", "away_both_halves",
            "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9", "c10",
        },
    ),
]


@pytest.mark.parametrize("name,score,expected", CASES, ids=[case[0] for case in CASES])
def test_scorelines(name: str, score: tuple, expected: set[str]) -> None:
    assert hits(*score) == expected


def test_registry_is_complete_and_unique() -> None:
    assert len(OUTCOMES) == 62
    assert len({outcome.id for outcome in OUTCOMES}) == len(OUTCOMES)
    groups = {outcome.group for outcome in OUTCOMES}
    assert groups == {
        "FT result", "HT result", "HT/FT", "Double chance", "Total goals",
        "Over/Under", "BTTS", "Odd/Even", "More goals", "Half goals",
        "Team goals", "Combos",
    }


def test_combo_count() -> None:
    combos = [outcome for outcome in OUTCOMES if outcome.group == "Combos"]
    assert [outcome.id for outcome in combos] == [f"c{index}" for index in range(1, 11)]


def test_result_helper() -> None:
    assert result(2, 1) == "1"
    assert result(1, 1) == "X"
    assert result(0, 3) == "2"


def test_ht_outcomes_need_half_time_data() -> None:
    match = Match(
        season="2024-25",
        date=dt.date(2024, 8, 10),
        home="A",
        away="B",
        fthg=2,
        ftag=2,
        hthg=None,
        htag=None,
    )
    assert evaluate(OUTCOMES_BY_ID["ht_x"], match) is None
    assert evaluate(OUTCOMES_BY_ID["btts_1h"], match) is None
    assert evaluate(OUTCOMES_BY_ID["c2"], match) is None
    # FT-based outcomes still count the row.
    assert evaluate(OUTCOMES_BY_ID["ft_x"], match) is True
    assert evaluate(OUTCOMES_BY_ID["btts_yes"], match) is True
    assert evaluate(OUTCOMES_BY_ID["tg_3plus"], match) is True
