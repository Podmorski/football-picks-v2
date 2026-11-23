"""Phase 3: MEL-v1 mandatory exposure, scenarios and diagnostic policies."""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest

from pipeline import bankroll


DI = 1.0
TICKETS = [
    {"type": "best2", "status": "available", "pc": 0.60, "odds": 2.0},
    {"type": "around3", "status": "available", "pc": 0.40, "odds": 3.0},
    {"type": "around5", "status": "available", "pc": 0.30, "odds": 5.0},
]


def proposal(kind: str, legs: list[dict], probability: float, odds: float) -> dict:
    return {
        "type": kind, "status": "available", "legs": legs,
        "combined_probability": probability, "combined_odds": odds,
        "model_ev": probability * odds - 1.0,
    }


def leg(home: str, market: str, pc: float, odds: float) -> dict:
    return {"d": "E0", "h": home, "a": "X", "m": market, "pc": pc, "odds": odds, "q": pc}


def state(available: float = 1000.0, drawdown: float = 0.0) -> dict:
    total = bankroll.mel_total_stake(available, drawdown)
    return {"available": available, "drawdown": drawdown, "mel_total_stake": total}


def test_mel_stake_is_two_one_point_one_two_five_and_zero_point_two_five_percent() -> None:
    assert bankroll.mel_total_stake(1000.0, 0.0) == pytest.approx(20.0)
    assert bankroll.mel_total_stake(1000.0, 0.10) == pytest.approx(11.25)
    assert bankroll.mel_total_stake(1000.0, 0.20) == pytest.approx(2.5)
    assert bankroll.mel_total_stake(1000.0, 0.35) == pytest.approx(2.5)
    assert bankroll.mel_total_stake(0.0, 0.0) == 0.0


def test_shared_leg_scenarios_reuse_one_outcome_and_sum_to_one() -> None:
    shared = leg("A", "M1", 0.5, 2.0)
    first = proposal("best2", [shared, leg("C", "M2", 0.5, 2.0)], 0.25, 4.0)
    second = proposal("around3", [shared, leg("D", "M3", 0.5, 2.0)], 0.25, 4.0)
    outcomes, meta = bankroll.scenarios([first, second])
    assert meta["unique_legs"] == 3
    assert len(outcomes) == 8
    assert sum(item["probability"] for item in outcomes) == pytest.approx(1.0)
    # shared loses, both other legs win -> both tickets lose simultaneously.
    target = next(item for item in outcomes if item["net"] == [-1.0, -1.0])
    assert target["probability"] == pytest.approx(0.5 * 0.5 * 0.5)


def test_mel_allocates_total_cap_and_respects_half_the_total_per_ticket() -> None:
    first = proposal("best2", [leg("A", "M1", 0.6, 2.0), leg("B", "M2", 0.6, 2.0)], 0.36, 4.0)
    second = proposal("around3", [leg("C", "M1", 0.4, 3.0), leg("D", "M2", 0.4, 3.0)], 0.16, 9.0)
    third = proposal("around5", [leg("E", "M1", 0.3, 5.0), leg("F", "M2", 0.3, 5.0)], 0.09, 25.0)
    outcomes, _meta = bankroll.scenarios([first, second, third])
    allocation = bankroll.allocate([first, second, third], state(), outcomes)
    stakes = allocation["stakes"]
    assert sum(stakes) == pytest.approx(20.0, abs=1e-6)
    assert all(value <= 10.0 + 1e-9 for value in stakes)
    assert allocation["solver"]["status"] == "ok"
    assert allocation["stress"]["status"] == "ok"


def test_negative_ev_still_gets_mandatory_exposure_with_a_warning() -> None:
    first = proposal("best2", [leg("A", "M1", 0.9, 1.01), leg("B", "M2", 0.9, 1.01)], 0.81, 1.0201)
    outcomes, _meta = bankroll.scenarios([first])
    allocation = bankroll.allocate([first], state(), outcomes)
    assert allocation["mandatory_exposure"] is True
    assert allocation["negative_ev"] is True
    assert "mandatory exposure" in allocation["message"]
    assert allocation["stakes"][0] == pytest.approx(20.0)


def test_zero_available_bankroll_produces_no_new_stake() -> None:
    first = proposal("best2", [leg("A", "M1", 0.6, 2.0), leg("B", "M2", 0.6, 2.0)], 0.36, 4.0)
    outcomes, _meta = bankroll.scenarios([first])
    allocation = bankroll.allocate([first], state(available=0.0), outcomes)
    assert allocation["stakes"] == [0.0]
    assert allocation["solver"]["status"] == "zero"
    total, stakes, meta = bankroll.no_forced_kelly([first], state(available=0.0), outcomes)
    assert (total, stakes, meta["status"]) == (0.0, [0.0], "zero")


def test_fewer_than_thirty_residual_dates_uses_minus_five_points() -> None:
    rng = random.Random(1)
    assert bankroll.cohort_shift([0.01] * 29, rng) == -0.05
    assert bankroll.cohort_shift([], rng) == -0.05


def test_residuals_use_only_rounds_before_the_proposal(tmp_path: Path) -> None:
    picks = tmp_path / "picks"
    picks.mkdir()
    for day in range(1, 3):
        date = f"2026-11-{day:02d}"
        rows = [
            {"d": "E0", "h": "A", "a": "B", "m": "BTTS:GG", "pc": 0.6, "st": "landed"},
            {"d": "E0", "h": "C", "a": "D", "m": "BTTS:GG", "pc": 0.6, "st": "lost"},
        ]
        (picks / f"{date}.json").write_text(json.dumps({"date": date, "rows": rows}), encoding="utf-8")
    future = "2026-11-03"
    rows = [{"d": "E0", "h": "E", "a": "F", "m": "BTTS:GG", "pc": 0.6, "st": "lost"}]
    (picks / f"{future}.json").write_text(json.dumps({"date": future, "rows": rows}), encoding="utf-8")
    residuals = bankroll.residual_dates(picks, "2026-11-03")
    assert set(residuals) == {("BTTS", "60-70")}
    assert len(residuals[("BTTS", "60-70")]) == 2
    assert math.isclose(residuals[("BTTS", "60-70")][0], -0.1)


def test_no_forced_kelly_can_return_zero_on_negative_robust_edge() -> None:
    first = proposal("best2", [leg("A", "M1", 0.9, 1.01), leg("B", "M2", 0.9, 1.01)], 0.81, 1.0201)
    outcomes, _meta = bankroll.scenarios([first])
    total, stakes, meta = bankroll.no_forced_kelly([first], state(), outcomes)
    assert total == 0.0
    assert stakes == [0.0]
    assert meta["message"] == "no positive robust edge"


def test_all_policies_share_tickets_and_round_atomic_settlement(tmp_path: Path) -> None:
    from pipeline import proposed_tickets as proposals

    prices = tmp_path / "prices"
    picks = tmp_path / "picks"
    (prices / "proposals").mkdir(parents=True)
    picks.mkdir()
    policies = {
        name: {"stake": stake}
        for name, stake in (("mel", 10.0), ("fixed_fractional", 100.0), ("no_forced_kelly", 4.0),
                            ("probability_weighted", 10.0), ("minimum_variance", 10.0),
                            ("martingale_capped", 1.0), ("martingale_uncapped", 1.0))
    }
    first = {
        "type": "best2", "status": "available", "flat_stake": 50.0, "policies": policies,
        "legs": [leg("A", "M1", 0.6, 2.0)],
    }
    second = {
        "type": "around3", "status": "available", "flat_stake": 30.0, "policies": policies,
        "legs": [leg("C", "M2", 0.5, 2.0)],
    }
    third = {"type": "around5", "status": "unavailable", "flat_stake": 0.0, "policies": {"mel": {"stake": 0.0}}, "legs": []}
    document = {"schema_version": 3, "round_date": "2026-11-24", "proposals": [first, second, third]}
    (prices / "proposals" / "2026-11-24.json").write_text(json.dumps(document), encoding="utf-8")
    (picks / "2026-11-24.json").write_text(json.dumps({
        "date": "2026-11-24",
        "rows": [
            {"d": "E0", "h": "A", "a": "X", "m": "M1", "st": "landed"},
            {"d": "E0", "h": "C", "a": "X", "m": "M2", "st": "pending"},
        ],
    }), encoding="utf-8")
    record = proposals.aggregate_records(prices, picks)
    assert record["policy_version"] == "mel-v1"
    # One ticket is still pending, so the whole round is reserved and bankroll is unchanged.
    assert record["mel"]["bankroll"] == 1000.0
    assert record["mel"]["unresolved_exposure"] == 20.0
    assert record["flat"]["staked"] == 0.0
    assert record["mel"]["staked"] == 0.0
    assert set(record["benchmarks"]) == {
        "fixed_fractional", "no_forced_kelly", "probability_weighted",
        "minimum_variance", "martingale_capped", "martingale_uncapped",
    }
    assert all(record["benchmarks"][key]["staked"] == 0.0 for key in record["benchmarks"])


def test_minimum_variance_handles_duplicate_tickets_without_pseudoinverse() -> None:
    first = proposal("best2", [leg("A", "M1", 0.6, 2.0), leg("B", "M2", 0.6, 2.0)], 0.36, 4.0)
    duplicate = proposal("around3", [leg("A", "M1", 0.6, 2.0), leg("B", "M2", 0.6, 2.0)], 0.36, 4.0)
    outcomes, _meta = bankroll.scenarios([first, duplicate])
    stakes, meta = bankroll.minimum_variance([first, duplicate], state(), outcomes)
    assert sum(stakes) == pytest.approx(20.0, abs=1e-6)
    assert meta["status"] == "ok"
