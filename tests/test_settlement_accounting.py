"""Phase 1: shared gross returns and round-atomic paper accounting."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import proposed_tickets as proposals
from pipeline import published_reconstructions as reconstructions
from pipeline import settlement


LEGS = [
    {"d": "E0", "h": "A", "a": "B", "m": "M1", "odds": 2.0, "fair": 2.5},
    {"d": "E0", "h": "C", "a": "D", "m": "M2", "odds": 2.5, "fair": 2.0},
]
KEYS = [("E0", "A", "B", "M1"), ("E0", "C", "D", "M2")]


def states(first: str, second: str) -> dict[tuple, str]:
    return {KEYS[0]: first, KEYS[1]: second}


def test_mixed_void_landed_uses_only_landed_prices_everywhere() -> None:
    statuses = states("landed", "void")
    flat = settlement.ticket_outcome(LEGS, statuses, 50.0)
    adaptive = settlement.ticket_outcome(LEGS, statuses, 10.0)
    benchmark = settlement.ticket_outcome(LEGS, statuses, 7.5)
    assert flat["gross_multiplier"] == adaptive["gross_multiplier"] == benchmark["gross_multiplier"] == 2.0
    assert flat["return"] == 100.0
    assert adaptive["return"] == 20.0
    assert benchmark["return"] == 15.0
    # A mixed ticket must never pay the full combined price.
    assert flat["return"] != 50.0 * 5.0


def test_lost_is_zero_and_all_void_returns_the_stake() -> None:
    lost = settlement.ticket_outcome(LEGS, states("landed", "lost"), 10.0)
    assert (lost["status"], lost["return"], lost["profit"], lost["gross_multiplier"]) == ("lost", 0.0, -10.0, 0.0)
    void = settlement.ticket_outcome(LEGS, states("void", "void"), 10.0)
    assert (void["status"], void["return"], void["profit"], void["gross_multiplier"]) == ("void", 10.0, 0.0, 1.0)
    pending = settlement.ticket_outcome(LEGS, states("landed", "pending"), 10.0)
    assert pending["status"] == "pending"
    assert pending["return"] is None and pending["profit"] is None


def test_pending_round_reserves_exposure_without_moving_bankroll() -> None:
    proposals_list = [
        {"type": "best2", "status": "available", "legs": LEGS, "adaptive": {"stake": 10.0}},
        {"type": "around3", "status": "available", "legs": [LEGS[0]], "adaptive": {"stake": 20.0}},
    ]
    statuses = states("landed", "pending")
    accounting = settlement.round_accounting(proposals_list, statuses, lambda item: item["adaptive"]["stake"])
    assert accounting["terminal"] is False
    assert accounting["net"] is None
    assert accounting["exposure"] == 30.0
    replay = settlement.replay_bankroll(
        [{"round_date": "2026-11-24", "proposals": proposals_list}],
        lambda _date: statuses, lambda item: item["adaptive"]["stake"], 1000.0,
    )
    assert replay["bankroll"] == 1000.0
    assert replay["unresolved_exposure"] == 30.0
    assert replay["available"] == 970.0


def test_ticket_order_never_changes_bankroll_or_drawdown() -> None:
    first = {
        "type": "best2", "status": "available", "legs": [LEGS[0]], "adaptive": {"stake": 20.0},
    }
    second = {
        "type": "around3", "status": "available", "legs": [LEGS[1]], "adaptive": {"stake": 10.0},
    }
    statuses = {KEYS[0]: "lost", KEYS[1]: "landed"}
    forward = settlement.replay_bankroll(
        [{"round_date": "2026-11-24", "proposals": [first, second]}],
        lambda _date: statuses, lambda item: item["adaptive"]["stake"], 1000.0,
    )
    reversed_order = settlement.replay_bankroll(
        [{"round_date": "2026-11-24", "proposals": [second, first]}],
        lambda _date: statuses, lambda item: item["adaptive"]["stake"], 1000.0,
    )
    assert forward["bankroll"] == reversed_order["bankroll"] == 995.0
    assert forward["maximum_drawdown"] == reversed_order["maximum_drawdown"] == pytest.approx(0.005)
    assert forward["series"] == reversed_order["series"]


def test_aggregate_flat_and_adaptive_agree_on_mixed_void(tmp_path: Path) -> None:
    prices = tmp_path / "prices"
    picks = tmp_path / "picks"
    (prices / "proposals").mkdir(parents=True)
    picks.mkdir()
    document = {
        "round_date": "2026-11-24",
        "proposals": [{
            "type": "best2", "status": "available", "flat_stake": 50.0,
            "legs": LEGS, "adaptive": {"stake": 10.0},
            "policies": {"mel": {"stake": 10.0}},
        }],
    }
    (prices / "proposals" / "2026-11-24.json").write_text(json.dumps(document), encoding="utf-8")
    (picks / "2026-11-24.json").write_text(json.dumps({
        "date": "2026-11-24",
        "rows": [
            {"d": "E0", "h": "A", "a": "B", "m": "M1", "st": "landed"},
            {"d": "E0", "h": "C", "a": "D", "m": "M2", "st": "void"},
        ],
    }), encoding="utf-8")
    aggregate = proposals.write_aggregate(prices, picks, tmp_path / "web")
    assert aggregate["flat"]["staked"] == 50.0
    assert aggregate["flat"]["returned"] == 100.0
    assert aggregate["mel"]["staked"] == 10.0
    assert aggregate["mel"]["returned"] == 20.0
    assert aggregate["flat"]["net"] == 50.0
    assert aggregate["mel"]["net"] == 10.0


def test_reconstruction_cumulative_has_no_money_or_roi() -> None:
    rounds = [{
        "proposals": [{
            "settlement": {"status": "landed", "source_pending": False, "leg_statuses": []},
        }],
    }]
    cumulative = reconstructions._cumulative(rounds)
    for forbidden in ("staked", "returned", "profit", "roi", "bankroll"):
        assert forbidden not in cumulative
    assert cumulative["tickets"] == 1 and cumulative["landed"] == 1


def test_committed_reconstruction_aggregate_is_counts_only() -> None:
    payload = json.loads((Path(__file__).resolve().parents[1] / "web" / "public" / "data" / "published-reconstructions.json").read_text(encoding="utf-8"))
    for forbidden in ("staked", "returned", "profit", "roi", "bankroll"):
        assert forbidden not in payload["cumulative"]
