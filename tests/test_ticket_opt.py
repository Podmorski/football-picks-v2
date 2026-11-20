"""Target-payout optimiser: brute-force optimum, target, one leg per match, DP."""
from __future__ import annotations

import itertools

import pytest

from pipeline import ticket_opt


def leg(home, away, probability):
    return {"h": home, "a": away, "m": "BTTS:GG", "pc": probability, "fair": 1.0 / probability}


def brute_force(legs, target, max_legs):
    best = None
    for size in range(1, max_legs + 1):
        for combo in itertools.combinations(legs, size):
            fair = 1.0
            for item in combo:
                fair *= item["fair"]
            if fair >= target and (best is None or fair < best[0]):
                best = (fair, combo)
    return best


def test_optimiser_matches_brute_force() -> None:
    legs = [leg("A", "B", 0.55), leg("C", "D", 0.50), leg("E", "F", 0.45), leg("G", "H", 0.40), leg("I", "J", 0.35)]
    result = ticket_opt.optimise(legs, 3.0, 3, alternatives=1, min_fair=0.0)
    best = brute_force(legs, 3.0, 3)
    assert best is not None
    assert len(result) == 1
    assert result[0]["fair"] == pytest.approx(best[0])
    assert result[0]["fair"] >= 3.0


def test_target_is_respected() -> None:
    legs = [leg("A", "B", 0.55), leg("C", "D", 0.50), leg("E", "F", 0.45), leg("G", "H", 0.40)]
    for target in (2.0, 3.0, 5.0):
        for ticket in ticket_opt.optimise(legs, target, 3, alternatives=3, min_fair=0.0):
            assert ticket["fair"] >= target


def test_one_leg_per_match() -> None:
    legs = [leg("A", "B", 0.55), leg("A", "B", 0.50), leg("C", "D", 0.45)]
    tickets = ticket_opt.optimise(legs, 1.0, 2, alternatives=5, min_fair=0.0)
    for ticket in tickets:
        matches = [(item["h"], item["a"]) for item in ticket["legs"]]
        assert len(matches) == len(set(matches))


def test_dp_matches_enumeration_on_a_small_pool() -> None:
    legs = [leg("A", "B", 0.55), leg("C", "D", 0.50), leg("E", "F", 0.45), leg("G", "H", 0.40), leg("I", "J", 0.35)]
    enumerated = ticket_opt._enumerate(legs, 3.0, 3, 1)
    dynamic = ticket_opt._dp(legs, 3.0, 3, 1)
    assert enumerated and dynamic
    assert dynamic[0]["fair"] == pytest.approx(enumerated[0]["fair"], abs=0.01)


def test_no_ticket_when_target_unreachable() -> None:
    legs = [leg("A", "B", 0.55), leg("C", "D", 0.50)]
    assert ticket_opt.optimise(legs, 100.0, 2, min_fair=0.0) == []
