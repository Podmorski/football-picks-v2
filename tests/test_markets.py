"""Market settlement on hand-made scores, and grid probabilities vs brute force."""
from __future__ import annotations

import math

import numpy as np
import pytest

from pipeline.markets import MARKETS, MARKET_BY_ID, catalogue_yaml, probabilities, settle
from pipeline.model.grid import N_HALF, joint_vector


def s(market_id: str, fthg: int, ftag: int, hthg, htag):
    market = MARKET_BY_ID[market_id]
    return settle(market, fthg, ftag, hthg, htag)


def test_registry_is_unique_and_documented() -> None:
    assert len(MARKETS) == 178
    assert len({market.id for market in MARKETS}) == len(MARKETS)
    yaml_text = catalogue_yaml()
    assert yaml_text.count("  - id: ") == len(MARKETS)
    assert "not_settleable:" in yaml_text


# 2-1, half-time 1-0 (second half 1-1)
CASES = [
    ("RESULT:1", True),
    ("RESULT:X", False),
    ("DOUBLE_CHANCE:1X", True),
    ("DOUBLE_CHANCE:X2", False),
    ("HALF_RESULT:I1", True),
    ("HALF_RESULT:IX", False),
    ("SECOND_HALF_RESULT:IIX", True),
    ("SECOND_HALF_RESULT:II1", False),
    ("HTFT:1-1", True),
    ("HTFT:1-X", False),
    ("HTFT_DC:1X-12", True),
    ("BTTS:GG", True),
    ("BTTS_1H:IGG", False),
    ("BTTS_2H:IIGG", True),
    ("PARITY:NEPAR", True),
    ("GOAL_RANGE_FT:3", True),
    ("GOAL_RANGE_FT:2-3", True),
    ("GOAL_RANGE_FT:4+", False),
    ("GOAL_RANGE_1H:I1", True),
    ("GOAL_RANGE_2H:II2", True),
    ("GOAL_RANGE_2H:II1", False),
    ("TEAM_GOALS:I1 2+", True),
    ("TEAM_GOALS:I1 1+", True),
    ("TEAM_GOALS:I2 0", False),
    ("TEAM_GOALS_HALF:I2 0", True),  # away scored 0 before half-time
    ("HALF_GOAL_COMBOS:I1+&II1+", True),
    ("MORE_GOALS_HALF:I=II", False),  # halves are 1 and 2 goals
    ("MORE_GOALS_HALF:I<II", True),
    ("WIN_BOTH_HALVES:DP 1", False),  # home drew the second half 1-1
    ("WIN_TO_NIL:SP 1", False),
    ("MARGIN:HP 1", False),
    ("CORRECT_SCORE:2:1", True),
    ("CORRECT_SCORE:1:1", False),
    ("RESULT_AND_GOALS:1&3+", True),
    ("DC_AND_GOALS:1X&3+", True),
    ("HTFT_AND_GOALS:1-1&3+", True),
    ("HTFT_COMBO:1-1&gg", True),
]


@pytest.mark.parametrize("market_id,expected", CASES)
def test_settlement_on_a_2_1_with_1_0_at_half_time(market_id: str, expected: bool) -> None:
    assert s(market_id, 2, 1, 1, 0) is expected


def test_settlement_needs_half_time_where_the_market_does() -> None:
    assert s("HTFT:1-1", 2, 1, None, None) is None
    assert s("BTTS_1H:IGG", 2, 1, None, None) is None
    assert s("RESULT:1", 2, 1, None, None) is True
    assert s("GOAL_RANGE_FT:3", 2, 1, None, None) is True


def test_zero_zero() -> None:
    assert s("RESULT:X", 0, 0, 0, 0) is True
    assert s("BTTS:NG", 0, 0, 0, 0) is True
    assert s("GOAL_RANGE_FT:0-1", 0, 0, 0, 0) is True
    assert s("HTFT:X-X", 0, 0, 0, 0) is True
    assert s("MORE_GOALS_HALF:I=II", 0, 0, 0, 0) is True
    assert s("CORRECT_SCORE:0:0", 0, 0, 0, 0) is True
    assert s("WIN_TO_NIL:SP 1", 0, 0, 0, 0) is False


def test_grid_probabilities_match_brute_force() -> None:
    lh1, la1, lh2, la2 = 0.55, 0.42, 0.78, 0.66
    joint = joint_vector(lh1, la1, lh2, la2, rho=0.0)
    model_p = probabilities(joint)

    def pmf(lam: float) -> list[float]:
        return [math.exp(-lam) * lam ** k / math.factorial(k) for k in range(N_HALF)]

    first = pmf(lh1)
    away_first = pmf(la1)
    second = pmf(lh2)
    away_second = pmf(la2)

    truth = {market.id: 0.0 for market in MARKETS}
    total = 0.0
    for h1 in range(N_HALF):
        for a1 in range(N_HALF):
            for h2 in range(N_HALF):
                for a2 in range(N_HALF):
                    mass = first[h1] * away_first[a1] * second[h2] * away_second[a2]
                    total += mass
                    fthg, ftag = h1 + h2, a1 + a2
                    for position, market in enumerate(MARKETS):
                        if market.settle(fthg, ftag, h1, a1):
                            truth[market.id] += mass

    for position, market in enumerate(MARKETS):
        assert model_p[position] == pytest.approx(truth[market.id] / total, abs=1e-6), market.id


def test_mutually_exclusive_families_sum_to_one() -> None:
    joint = joint_vector(0.6, 0.5, 0.7, 0.6, rho=-0.05)
    probs = probabilities(joint)
    index = {market.id: position for position, market in enumerate(MARKETS)}

    assert sum(probs[index[f"RESULT:{c}"]] for c in "1X2") == pytest.approx(1.0, abs=1e-9)
    assert sum(probs[index[f"HTFT:{a}-{b}"]] for a in "1X2" for b in "1X2") == pytest.approx(1.0, abs=1e-9)
    assert probs[index["BTTS:GG"]] + probs[index["BTTS:NG"]] == pytest.approx(1.0, abs=1e-9)
    assert sum(probs[index[f"MORE_GOALS_HALF:{c}"]] for c in ("I>II", "I=II", "I<II")) == pytest.approx(1.0, abs=1e-9)
