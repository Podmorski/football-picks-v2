"""Frozen proposals, ticket-construction-v2, paper settlement and policy."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import proposed_tickets as proposals
from pipeline import ticket_construction

DATE = "2026-11-24"


def row(market: str, home: str, away: str, pc: float, div: str = "E0") -> dict:
    return {"d": div, "k": "20:00", "h": home, "a": away, "m": market, "p": pc, "pc": pc}


def document(rows: list[dict]) -> dict:
    return {"date": DATE, "rows": rows}


def snapshot(fixtures: list[dict], fetched_at: str = "2026-11-24T13:00:00+00:00") -> dict:
    return {"round_date": DATE, "fetched_at": fetched_at, "fixtures": fixtures, "started_not_priced": []}


def fixture(home: str, away: str, prices: dict, div: str = "E0") -> dict:
    return {"div": div, "home": home, "away": away, "kickoff": "20:00", "prices": prices}


def build(rows: list[dict], fixtures: list[dict]) -> dict:
    return proposals.build_proposals(document(rows), snapshot(fixtures))


def by_type(payload: dict, key: str) -> dict:
    return next(item for item in payload["proposals"] if item["type"] == key)


def test_full_menu_keeps_every_priced_market_and_has_no_58_gate() -> None:
    doc = document([
        row("BTTS:GG", "A", "B", 0.30), row("RESULT:X", "A", "B", 0.45),
        row("CORRECT_SCORE:2:1", "C", "D", 0.99), row("BTTS:GG", "E", "F", 0.80),
        row("RESULT:1", "G", "H", 0.70),
    ])
    snap = snapshot([
        fixture("A", "B", {"BTTS:GG": 2.0, "RESULT:X": 3.0}),
        fixture("C", "D", {"CORRECT_SCORE:2:1": 10.0}),
        fixture("E", "F", {"BTTS:GG": 2.0}),
        fixture("G", "H", {}),
    ])
    snap["started_not_priced"] = [{"div": "E0", "home": "E", "away": "F"}]
    menu = proposals.eligible_pool(doc, snap)
    assert {(leg["h"], leg["m"], leg["pc"]) for leg in menu} == {
        ("A", "BTTS:GG", 0.30), ("A", "RESULT:X", 0.45),
    }


def test_banded_best2_uses_actual_prices_and_highest_pc_in_band() -> None:
    rows = [
        row("F1A", "A", "B", 0.80), row("F1B", "A", "B", 0.90),
        row("F2A", "C", "D", 0.75), row("F2B", "C", "D", 0.70),
        row("F3A", "E", "F", 0.85),
    ]
    fixtures = [
        fixture("A", "B", {"F1A": 1.50, "F1B": 1.20}),
        fixture("C", "D", {"F2A": 1.10, "F2B": 1.30}),
        fixture("E", "F", {"F3A": 1.60}),
    ]
    payload = build(rows, fixtures)
    best2 = by_type(payload, "best2")
    assert best2["status"] == "available"
    assert len(best2["legs"]) == 2
    assert best2["combined_odds"] == pytest.approx(1.56)
    assert {leg["m"] for leg in best2["legs"]} == {"F1B", "F2B"}
    assert best2["construction"]["band"] == "preferred"
    assert best2["construction"]["band_message"] == "in preferred band"


def test_short_price_pool_does_not_force_a_1_02_ticket() -> None:
    rows = [row("M", "A", "B", 0.90), row("M", "C", "D", 0.90)]
    fixtures = [fixture("A", "B", {"M": 1.10}), fixture("C", "D", {"M": 1.40})]
    best2 = by_type(build(rows, fixtures), "best2")
    assert best2["status"] == "available"
    assert min(leg["odds"] for leg in best2["legs"]) >= 1.10


def test_a_single_cheap_fixture_does_not_by_itself_force_relaxation() -> None:
    rows = [row("M", "A", "B", 0.90), row("M", "C", "D", 0.90)]
    fixtures = [fixture("A", "B", {"M": 1.02}), fixture("C", "D", {"M": 1.40})]
    best2 = by_type(build(rows, fixtures), "best2")
    assert best2["construction"]["individual_floor_relaxed"] is True
    assert best2["construction"]["individual_floor_message"] == "preferred individual-odds floor relaxed"


def test_fallback_ladder_is_explicit_and_deterministic() -> None:
    rows = [row("M", "A", "B", 0.60), row("M", "C", "D", 0.60), row("M", "E", "F", 0.60)]
    fixtures = [fixture("A", "B", {"M": 1.20}), fixture("C", "D", {"M": 1.20}), fixture("E", "F", {"M": 1.20})]
    menu = proposals.eligible_pool(document(rows), snapshot(fixtures))
    around5 = ticket_construction._build_one(menu, "around5")
    assert around5["status"] == "available"
    assert around5["combined_odds"] == pytest.approx(1.728)
    assert around5["construction"]["band"] == "below_floor"
    assert around5["construction"]["band_message"] == "below meaningful payout floor; highest available payout"
    assert around5["construction"]["achieved_odds"] == pytest.approx(1.728)


def test_outside_band_fallback_minimises_distance_above_the_floor() -> None:
    rows = [row("M", "A", "B", 0.70), row("M", "C", "D", 0.70)]
    fixtures = [fixture("A", "B", {"M": 2.20}), fixture("C", "D", {"M": 2.20})]
    menu = proposals.eligible_pool(document(rows), snapshot(fixtures))
    around3 = ticket_construction._build_one(menu, "around3")
    assert around3["combined_odds"] == pytest.approx(4.84)
    assert around3["construction"]["band"] == "outside"
    assert around3["construction"]["band_message"] == "outside preferred band"


def test_individual_price_relaxation_is_visible_and_not_a_silent_gate() -> None:
    rows = [row("M", "A", "B", 0.70), row("M", "C", "D", 0.70)]
    fixtures = [fixture("A", "B", {"M": 1.05}), fixture("C", "D", {"M": 1.05})]
    best2 = by_type(build(rows, fixtures), "best2")
    assert best2["status"] == "available"
    assert best2["combined_odds"] == pytest.approx(1.1025)
    assert best2["construction"]["individual_floor_relaxed"] is True
    assert best2["construction"]["individual_floor_message"] == "preferred individual-odds floor relaxed"


def test_fewer_than_two_priced_fixtures_is_unavailable_without_filler() -> None:
    payload = build([row("M", "A", "B", 0.70)], [fixture("A", "B", {"M": 2.0})])
    for key in ("best2", "around3", "around5"):
        proposal = by_type(payload, key)
        assert proposal["status"] == "unavailable"
        assert proposal["reason"] == "unavailable — fewer than two distinct priced fixtures"
        assert proposal["legs"] == []


def test_tickets_never_reuse_a_fixture_inside_one_ticket() -> None:
    rows = [row("M1", "A", "B", 0.70), row("M2", "A", "B", 0.60), row("M", "C", "D", 0.70)]
    fixtures = [fixture("A", "B", {"M1": 1.50, "M2": 1.60}), fixture("C", "D", {"M": 2.0})]
    payload = build(rows, fixtures)
    for proposal in payload["proposals"]:
        if proposal["status"] != "available":
            continue
        keys = [(leg["d"], leg["h"], leg["a"]) for leg in proposal["legs"]]
        assert len(keys) == len(set(keys))
        assert not any(leg["m"].startswith("CORRECT_SCORE:") for leg in proposal["legs"])


def test_overlap_relaxation_is_recorded_when_fixtures_are_scarce() -> None:
    rows = [row("M", "A", "B", 0.70), row("M", "C", "D", 0.70)]
    fixtures = [fixture("A", "B", {"M": 1.50}), fixture("C", "D", {"M": 2.00})]
    payload = build(rows, fixtures)
    assert by_type(payload, "best2")["construction"]["overlap_relaxed"] is False
    assert by_type(payload, "around3")["construction"]["overlap_relaxed"] is True


def test_frozen_file_is_immutable_after_later_snapshot(tmp_path: Path) -> None:
    rows = [row("M", "A", "B", 0.70), row("M", "C", "D", 0.70)]
    first = snapshot([fixture("A", "B", {"M": 2.0}), fixture("C", "D", {"M": 2.0})])
    prices = tmp_path / "prices"
    picks = tmp_path / "picks"
    picks.mkdir()
    created = proposals.ensure_proposals(DATE, document(rows), first, prices, picks)
    path = prices / "proposals" / f"{DATE}.json"
    before = path.read_bytes()
    changed = snapshot([fixture("A", "B", {"M": 3.0}), fixture("C", "D", {"M": 3.0})], "2026-11-24T17:00:00+00:00")
    again = proposals.ensure_proposals(DATE, document(rows), changed, prices, picks)
    assert again == created
    assert path.read_bytes() == before
    assert json.loads(path.read_text(encoding="utf-8"))["proposals"][0]["construction"]["policy"] == "ticket-construction-v2"


def test_paper_settlement_semantics() -> None:
    proposal = {
        "legs": [
            {"d": "E0", "h": "A", "a": "B", "m": "A", "odds": 2.0},
            {"d": "E0", "h": "C", "a": "D", "m": "B", "odds": 2.5},
        ],
        "combined_odds": 5.0, "adaptive": {"stake": 10.0},
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
    assert aggregate["mel"]["bankroll"] == 1000.0
    assert aggregate["policy_version"] == "mel-v1"
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
        "schema_version": 2, "round_date": "2026-11-24",
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
