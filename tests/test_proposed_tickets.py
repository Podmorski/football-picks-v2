"""Frozen proposals, target selection, paper settlement and bankroll policy."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import proposed_tickets as proposals


DATE = "2026-11-24"


def row(market: str, home: str, away: str, pc: float) -> dict:
    return {"d": "E0", "k": "20:00", "h": home, "a": away, "m": market, "p": pc, "pc": pc}


def document(rows: list[dict]) -> dict:
    return {"date": DATE, "rows": rows}


def snapshot(fixtures: list[dict], fetched_at: str = "2026-11-24T13:00:00+00:00") -> dict:
    return {"round_date": DATE, "fetched_at": fetched_at, "fixtures": fixtures, "started_not_priced": []}


def fixture(home: str, away: str, prices: dict) -> dict:
    return {"div": "E0", "home": home, "away": away, "kickoff": "20:00", "prices": prices}


def test_58_is_inclusive_correct_score_missing_price_and_started_are_excluded() -> None:
    doc = document([
        row("BTTS:GG", "A", "B", 0.58),
        row("CORRECT_SCORE:2:1", "C", "D", 0.99),
        row("RESULT:1", "E", "F", 0.80),
    ])
    snap = snapshot([
        fixture("A", "B", {"BTTS:GG": 2.0}),
        fixture("C", "D", {"CORRECT_SCORE:2:1": 10.0}),
        fixture("E", "F", {"RESULT:1": 2.0}),
        fixture("G", "H", {"BTTS:NG": 2.0}),
    ])
    snap["started_not_priced"] = [{"div": "E0", "home": "E", "away": "F"}]
    pool = proposals.eligible_pool(doc, snap)
    assert {(leg["h"], leg["a"], leg["m"], leg["pc"]) for leg in pool} == {("A", "B", "BTTS:GG", 0.58)}


def test_one_highest_probability_leg_per_match() -> None:
    doc = document([
        row("BTTS:GG", "A", "B", 0.61), row("RESULT:1", "A", "B", 0.64),
        row("BTTS:GG", "C", "D", 0.70),
    ])
    snap = snapshot([
        fixture("A", "B", {"BTTS:GG": 1.8, "RESULT:1": 1.7}),
        fixture("C", "D", {"BTTS:GG": 1.6}),
    ])
    pool = proposals.eligible_pool(doc, snap)
    assert len(pool) == 2
    assert pool[0]["h"] == "C" and pool[0]["pc"] == 0.70
    assert pool[1]["m"] == "RESULT:1"


def pool() -> list[dict]:
    return [
        {"d": "E0", "h": "A", "a": "B", "k": "20:00", "m": "A", "pc": 0.90, "fair": 1.1111, "odds": 1.80},
        {"d": "E0", "h": "C", "a": "D", "k": "20:00", "m": "B", "pc": 0.90, "fair": 1.1111, "odds": 1.70},
        {"d": "E0", "h": "E", "a": "F", "k": "20:00", "m": "C", "pc": 0.80, "fair": 1.25, "odds": 1.50},
        {"d": "E0", "h": "G", "a": "H", "k": "20:00", "m": "D", "pc": 0.70, "fair": 1.4286, "odds": 2.00},
    ]


def test_two_best_and_target_band_maximise_probability() -> None:
    legs = pool()
    doc = document([{**leg, "p": leg["pc"]} for leg in legs])
    snap = snapshot([fixture(leg["h"], leg["a"], {leg["m"]: leg["odds"]}) for leg in legs])
    payload = proposals.build_proposals(doc, snap)
    assert payload["proposals"][0]["type"] == "best2"
    assert [leg["h"] for leg in payload["proposals"][0]["legs"]] == ["A", "C"]
    assert payload["proposals"][0]["combined_odds"] == pytest.approx(3.06)
    assert payload["proposals"][0]["combined_probability"] == pytest.approx(0.81)
    around3 = payload["proposals"][1]
    assert around3["status"] == "available"
    assert around3["combined_odds"] == pytest.approx(3.06)
    assert around3["combined_probability"] == pytest.approx(0.81)
    around5 = payload["proposals"][2]
    assert around5["status"] == "available"
    assert 4.50 <= around5["combined_odds"] <= 5.50
    assert around5["combined_odds"] == pytest.approx(4.59)
    assert around5["combined_probability"] == pytest.approx(0.648)


def test_no_band_uses_closest_without_threshold_relaxation_or_filler() -> None:
    target_pool = [
        {"d": "E0", "h": "A", "a": "B", "k": "20:00", "m": "A", "pc": 0.70, "fair": 1.4286, "odds": 1.20},
        {"d": "E0", "h": "C", "a": "D", "k": "20:00", "m": "B", "pc": 0.70, "fair": 1.4286, "odds": 1.25},
        {"d": "E0", "h": "E", "a": "F", "k": "20:00", "m": "C", "pc": 0.70, "fair": 1.4286, "odds": 1.30},
    ]
    legs, reason = proposals.choose_target(target_pool, 3.0, 2.70, 3.30)
    assert legs and len(legs) <= 3
    assert "closest actual odds" in reason
    assert all(leg["pc"] >= 0.58 for leg in legs)
    _none, unavailable = proposals.choose_target(target_pool[:1], 3.0, 2.70, 3.30)
    assert _none is None
    assert unavailable == "fewer than 2 eligible legs"


def test_frozen_file_is_immutable_after_later_snapshot(tmp_path: Path) -> None:
    doc = document([{**leg, "p": leg["pc"]} for leg in pool()])
    first = snapshot([fixture(leg["h"], leg["a"], {leg["m"]: leg["odds"]}) for leg in pool()])
    prices = tmp_path / "prices"
    picks = tmp_path / "picks"
    picks.mkdir()
    created = proposals.ensure_proposals(DATE, doc, first, prices, picks)
    path = prices / "proposals" / f"{DATE}.json"
    before = path.read_bytes()
    changed = snapshot([fixture(leg["h"], leg["a"], {leg["m"]: leg["odds"] + 1}) for leg in pool()], "2026-11-24T17:00:00+00:00")
    again = proposals.ensure_proposals(DATE, doc, changed, prices, picks)
    assert again == created
    assert path.read_bytes() == before


def test_paper_settlement_semantics() -> None:
    proposal = {
        "legs": [
            {"d": "E0", "h": "A", "a": "B", "m": "A", "odds": 2.0},
            {"d": "E0", "h": "C", "a": "D", "m": "B", "odds": 2.5},
        ],
        "combined_odds": 5.0,
        "adaptive": {"stake": 10.0},
    }
    base = {("E0", "A", "B", "A"): "landed", ("E0", "C", "D", "B"): "landed"}
    assert proposals.ticket_result(proposal, base) == {"status": "landed", "stake": 10.0, "return": 50.0, "profit": 40.0}
    assert proposals.ticket_result(proposal, {**base, ("E0", "C", "D", "B"): "lost"})["status"] == "lost"
    assert proposals.ticket_result(proposal, {**base, ("E0", "C", "D", "B"): "pending"})["status"] == "pending"
    assert proposals.ticket_result(proposal, {("E0", "A", "B", "A"): "void", ("E0", "C", "D", "B"): "void"}) == {"status": "void", "stake": 10.0, "return": 10.0, "profit": 0.0}
    mixed = proposals.ticket_result(proposal, {("E0", "A", "B", "A"): "landed", ("E0", "C", "D", "B"): "void"})
    assert mixed["return"] == 20.0


def test_adaptive_zero_edge_quarter_kelly_caps_and_drawdown() -> None:
    def ticket(kind: str, probability: float, odds: float) -> dict:
        return {"type": kind, "status": "available", "combined_probability": probability, "combined_odds": odds}
    state = {"available": 1000.0, "drawdown": 0.0}
    zero = [ticket("best2", 0.5, 1.8)]
    proposals._adaptive_allocations(zero, state)
    assert zero[0]["adaptive"]["stake"] == 0.0
    assert zero[0]["adaptive"]["reason"] == "edge <= 0"

    one = [ticket("best2", 0.5, 3.0)]
    proposals._adaptive_allocations(one, state)
    assert one[0]["adaptive"]["kelly_full"] == pytest.approx(0.25)
    assert one[0]["adaptive"]["kelly_quarter"] == pytest.approx(0.0625)
    assert one[0]["adaptive"]["stake"] == pytest.approx(10.0)

    capped = [ticket("best2", 0.5, 3.0), ticket("around3", 0.5, 3.0), ticket("around5", 0.5, 3.0)]
    proposals._adaptive_allocations(capped, state)
    assert sum(item["adaptive"]["stake"] for item in capped) == pytest.approx(20.0, abs=1e-3)
    assert all(item["adaptive"]["stake"] == pytest.approx(20.0 / 3.0, abs=1e-3) for item in capped)

    halved = [ticket("best2", 0.5, 3.0)]
    proposals._adaptive_allocations(halved, {"available": 1000.0, "drawdown": 0.10})
    assert halved[0]["adaptive"]["stake"] == pytest.approx(5.0)

    stopped = [ticket("best2", 0.5, 3.0)]
    proposals._adaptive_allocations(stopped, {"available": 1000.0, "drawdown": 0.20})
    assert stopped[0]["adaptive"]["stake"] == 0.0


def test_replay_uses_only_prior_settled_information(tmp_path: Path) -> None:
    prices = tmp_path / "prices"
    picks = tmp_path / "picks"
    proposals_dir = prices / "proposals"
    proposals_dir.mkdir(parents=True)
    picks.mkdir()
    older = {
        "round_date": "2026-11-20", "proposals": [{
            "type": "best2", "status": "available", "combined_odds": 2.0,
            "legs": [{"d": "E0", "h": "A", "a": "B", "m": "A", "odds": 2.0}],
            "adaptive": {"stake": 10.0},
        }],
    }
    future = {
        "round_date": DATE, "proposals": [{
            "type": "best2", "status": "available", "combined_odds": 10.0,
            "legs": [{"d": "E0", "h": "X", "a": "Y", "m": "A", "odds": 10.0}],
            "adaptive": {"stake": 999.0},
        }],
    }
    (proposals_dir / "2026-11-20.json").write_text(json.dumps(older), encoding="utf-8")
    (proposals_dir / f"{DATE}.json").write_text(json.dumps(future), encoding="utf-8")
    (picks / "2026-11-20.json").write_text(json.dumps({
        "date": "2026-11-20", "rows": [{"d": "E0", "h": "A", "a": "B", "m": "A", "st": "landed"}],
    }), encoding="utf-8")
    state = proposals.replay_adaptive(prices, picks, DATE)
    assert state["bankroll"] == 1010.0
    assert state["available"] == 1010.0
    assert state["drawdown"] == 0.0


def test_public_aggregate_contains_no_actual_prices(tmp_path: Path) -> None:
    prices = tmp_path / "prices"
    picks = tmp_path / "picks"
    (prices / "proposals").mkdir(parents=True)
    picks.mkdir()
    proposal = {
        "round_date": "2026-11-20",
        "proposals": [{
            "type": "best2", "label": "2 best games", "status": "available", "flat_stake": 50.0,
            "combined_probability": 0.5, "combined_odds": 4.0,
            "legs": [{"d": "E0", "h": "A", "a": "B", "m": "A", "pc": 0.5, "odds": 4.0}],
            "adaptive": {"stake": 10.0},
        }],
    }
    (prices / "proposals" / "2026-11-20.json").write_text(json.dumps(proposal), encoding="utf-8")
    (picks / "2026-11-20.json").write_text(json.dumps({
        "date": "2026-11-20", "rows": [{"d": "E0", "h": "A", "a": "B", "m": "A", "st": "landed"}],
    }), encoding="utf-8")
    web = tmp_path / "web"
    aggregate = proposals.write_aggregate(prices, picks, web)
    assert aggregate["flat"]["staked"] == 50.0
    assert aggregate["flat"]["returned"] == 200.0
    assert aggregate["adaptive"]["bankroll"] == 1030.0
    text = (web / "proposed-tickets-record.json").read_text(encoding="utf-8").lower()
    assert "\"odds\"" not in text
    assert "\"prices\"" not in text
    assert "\"combined_odds\"" not in text
    assert "not a profit guarantee" in text


def test_readiness_requires_valid_proposals_only_after_activation(tmp_path: Path) -> None:
    prices = tmp_path / "prices"
    picks = tmp_path / "picks"
    (prices / "rounds").mkdir(parents=True)
    picks.mkdir()
    pre = {"round_date": "2026-11-22", "fetched_at": "2026-11-22T12:00:00+00:00", "fixtures": [{"div": "E0"}], "started_not_priced": []}
    active = {"round_date": "2026-11-24", "fetched_at": "2026-11-24T13:00:00+00:00", "fixtures": [{"div": "E0"}], "started_not_priced": []}
    empty = {"round_date": "2026-11-25", "fetched_at": "2026-11-25T13:00:00+00:00", "fixtures": [], "started_not_priced": []}
    for snap in (pre, active, empty):
        (prices / "rounds" / f"{snap['round_date']}.json").write_text(json.dumps(snap), encoding="utf-8")
    assert proposals.missing_required_proposals(prices) == ["2026-11-24"]
    with pytest.raises(proposals.ProposalReadinessError, match="2026-11-24"):
        proposals.validate_required_proposals(prices)

    proposal = {
        "schema_version": 1, "round_date": "2026-11-24",
        "proposals": [
            {"type": "best2", "status": "unavailable", "reason": "fewer than 2 eligible legs"},
            {"type": "around3", "status": "unavailable", "reason": "fewer than 2 eligible legs"},
            {"type": "around5", "status": "unavailable", "reason": "fewer than 2 eligible legs"},
        ],
    }
    (prices / "proposals").mkdir()
    (prices / "proposals" / "2026-11-24.json").write_text(json.dumps(proposal), encoding="utf-8")
    assert proposals.missing_required_proposals(prices) == []
    proposals.validate_required_proposals(prices)


def test_aggregate_cli_fails_for_required_missing_proposal(tmp_path: Path) -> None:
    prices = tmp_path / "prices"
    (prices / "rounds").mkdir(parents=True)
    snap = {"round_date": "2026-11-24", "fetched_at": "2026-11-24T13:00:00+00:00", "fixtures": [{"div": "E0"}], "started_not_priced": []}
    (prices / "rounds" / "2026-11-24.json").write_text(json.dumps(snap), encoding="utf-8")
    code = proposals.main([
        "aggregate", "--prices-dir", str(prices), "--picks-dir", str(tmp_path / "picks"),
        "--web-dir", str(tmp_path / "web"),
    ])
    assert code == 2


def test_no_retrospective_generation_api() -> None:
    assert not hasattr(proposals, "backfill")
    assert not hasattr(proposals, "generate_history")
