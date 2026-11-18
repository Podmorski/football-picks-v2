"""Goal grid consistency: groups sum correctly and combos match brute force."""
from __future__ import annotations

import math

import numpy as np
import pytest

from pipeline.model.grid import N_HALF, outcome_probabilities
from pipeline.outcomes import OUTCOMES, OUTCOMES_BY_ID

INDEX = {outcome.id: position for position, outcome in enumerate(OUTCOMES)}


def probability(probabilities: np.ndarray, outcome_id: str) -> float:
    return float(probabilities[INDEX[outcome_id]])


@pytest.mark.parametrize("lambdas", [(1.4, 1.1), (0.6, 0.5), (2.2, 1.9), (1.0, 2.4)])
def test_everything_sums_to_one(lambdas: tuple[float, float]) -> None:
    lh, la = lambdas
    probabilities = outcome_probabilities(lh * 0.45, la * 0.42, lh * 0.55, la * 0.58, rho=0.0)
    assert (probabilities >= 0).all()
    assert (probabilities <= 1).all()
    # Outcomes overlap by design; the mutually exclusive FT-result trio must still sum to 1.
    assert sum(probability(probabilities, f"ft_{code}") for code in ("1", "x", "2")) == pytest.approx(1.0, abs=1e-9)


def test_partitioning_groups_sum_to_one() -> None:
    probabilities = outcome_probabilities(0.6, 0.5, 0.8, 0.7, rho=-0.05)

    assert sum(probability(probabilities, f"ft_{code}") for code in ("1", "x", "2")) == pytest.approx(1.0, abs=1e-9)
    assert sum(probability(probabilities, f"ht_{code}") for code in ("1", "x", "2")) == pytest.approx(1.0, abs=1e-9)
    assert sum(probability(probabilities, f"htft_{h}{f}") for h in "1x2" for f in "1x2") == pytest.approx(1.0, abs=1e-9)
    assert probability(probabilities, "btts_yes") + probability(probabilities, "btts_no") == pytest.approx(1.0, abs=1e-9)
    assert probability(probabilities, "odd") + probability(probabilities, "even") == pytest.approx(1.0, abs=1e-9)
    assert probability(probabilities, "mg_1h") + probability(probabilities, "mg_eq") + probability(probabilities, "mg_2h") == pytest.approx(1.0, abs=1e-9)
    assert probability(probabilities, "ou_o25") + probability(probabilities, "ou_u25") == pytest.approx(1.0, abs=1e-9)
    assert probability(probabilities, "ou_o15") + probability(probabilities, "ou_u15") == pytest.approx(1.0, abs=1e-9)

    # The registry's goal buckets stop at 6, so the 7+ tail is deliberately excluded.
    buckets = sum(probability(probabilities, oid) for oid in ("tg_0_1", "tg_2_3", "tg_4_6"))
    assert 0.95 < buckets <= 1.0


def test_double_chance_is_the_union_of_results() -> None:
    probabilities = outcome_probabilities(0.9, 0.8, 1.1, 0.9, rho=-0.05)
    one = probability(probabilities, "ft_1")
    draw = probability(probabilities, "ft_x")
    two = probability(probabilities, "ft_2")
    assert probability(probabilities, "dc_1x") == pytest.approx(one + draw, abs=1e-9)
    assert probability(probabilities, "dc_x2") == pytest.approx(draw + two, abs=1e-9)
    assert probability(probabilities, "dc_12") == pytest.approx(one + two, abs=1e-9)


def test_combos_match_brute_force() -> None:
    lh1, la1, lh2, la2 = 0.62, 0.45, 0.85, 0.72
    probabilities = outcome_probabilities(lh1, la1, lh2, la2, rho=0.0)

    def pmf(lam: float) -> list[float]:
        return [math.exp(-lam) * lam ** k / math.factorial(k) for k in range(N_HALF)]

    first = pmf(lh1)
    second = pmf(lh2)
    away_first = pmf(la1)
    away_second = pmf(la2)

    truth = {outcome.id: 0.0 for outcome in OUTCOMES}
    total_mass = 0.0
    for h1 in range(N_HALF):
        for a1 in range(N_HALF):
            for h2 in range(N_HALF):
                for a2 in range(N_HALF):
                    mass = first[h1] * away_first[a1] * second[h2] * away_second[a2]
                    total_mass += mass
                    fthg, ftag = h1 + h2, a1 + a2
                    for outcome in OUTCOMES:
                        if outcome.fn(fthg, ftag, h1, a1):
                            truth[outcome.id] += mass

    for outcome in OUTCOMES:
        assert probability(probabilities, outcome.id) == pytest.approx(truth[outcome.id] / total_mass, abs=1e-9), outcome.id


def test_goal_increase_raises_three_plus() -> None:
    low = outcome_probabilities(0.35, 0.3, 0.4, 0.35, rho=0.0)
    high = outcome_probabilities(0.95, 0.9, 1.1, 1.0, rho=0.0)
    assert probability(high, "tg_3plus") > probability(low, "tg_3plus")
    assert probability(high, "ou_u15") < probability(low, "ou_u15")


def test_outcome_registry_order_is_stable() -> None:
    assert OUTCOMES_BY_ID["c10"].id == "c10"
    assert len(OUTCOMES) == 62
