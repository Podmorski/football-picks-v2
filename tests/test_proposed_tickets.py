"""ticket-construction-v3, frozen proposals, paper settlement and policy."""
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


def menu(rows: list[dict], fixtures: list[dict]) -> list[dict]:
    return proposals.eligible_pool(document(rows), snapshot(fixtures))


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
    pool = proposals.eligible_pool(doc, snap)
    assert {(leg["h"], leg["m"], leg["pc"]) for leg in pool} == {
        ("A", "BTTS:GG", 0.30), ("A", "RESULT:X", 0.45),
    }


def test_high_probability_maximises_pc_and_never_forces_three_legs() -> None:
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
    best2 = by_type(build(rows, fixtures), "best2")
    assert best2["label"] == "High-probability"
    assert best2["status"] == "available"
    assert len(best2["legs"]) == 2
    assert {(leg["h"], leg["m"]) for leg in best2["legs"]} == {("A", "F1B"), ("E", "F3A")}
    assert best2["combined_probability"] == pytest.approx(0.9 * 0.85)
    assert best2["combined_odds"] == pytest.approx(1.92)
    assert best2["construction"]["band"] == "no_band"
    assert best2["construction"]["band_message"] == "no combined-odds target"
    assert best2["construction"]["individual_price_tier"] == "preferred"


def test_around3_allows_one_to_three_legs_and_hits_the_band() -> None:
    rows = [row("M", "A", "B", 0.55), row("M", "C", "D", 0.75), row("M", "E", "F", 0.75)]
    fixtures = [fixture("A", "B", {"M": 3.00}), fixture("C", "D", {"M": 1.50}), fixture("E", "F", {"M": 2.00})]
    around3 = ticket_construction._build_one(menu(rows, fixtures), "around3")
    assert around3["status"] == "available"
    assert len(around3["legs"]) == 2
    assert {(leg["h"], leg["m"]) for leg in around3["legs"]} == {("C", "M"), ("E", "M")}
    assert around3["combined_odds"] == pytest.approx(3.00)
    assert around3["combined_probability"] == pytest.approx(0.5625)
    assert around3["construction"]["band"] == "preferred"


def test_around3_can_use_a_single_leg() -> None:
    rows = [row("M", "A", "B", 0.40)]
    fixtures = [fixture("A", "B", {"M": 3.00})]
    around3 = ticket_construction._build_one(menu(rows, fixtures), "around3")
    assert around3["status"] == "available"
    assert len(around3["legs"]) == 1
    assert around3["construction"]["band"] == "preferred"


def test_five_ten_combo_requires_three_to_five_legs_and_hits_the_band() -> None:
    rows = [
        row("M", "A", "B", 0.70), row("M", "C", "D", 0.70),
        row("M", "E", "F", 0.70), row("M", "G", "H", 0.70),
    ]
    fixtures = [
        fixture("A", "B", {"M": 1.70}), fixture("C", "D", {"M": 1.80}),
        fixture("E", "F", {"M": 1.70}), fixture("G", "H", {"M": 1.50}),
    ]
    combo = ticket_construction._build_one(menu(rows, fixtures), "around5")
    assert combo["label"] == "5–10 combo"
    assert combo["status"] == "available"
    assert len(combo["legs"]) == 3
    assert 5.00 <= combo["combined_odds"] <= 10.00
    assert combo["combined_odds"] == pytest.approx(1.70 * 1.80 * 1.70)
    assert combo["construction"]["band"] == "preferred"


def test_five_ten_combo_is_unavailable_with_only_two_fixtures() -> None:
    rows = [row("M", "A", "B", 0.70), row("M", "C", "D", 0.70)]
    fixtures = [fixture("A", "B", {"M": 2.50}), fixture("C", "D", {"M": 2.50})]
    combo = ticket_construction._build_one(menu(rows, fixtures), "around5")
    assert combo["status"] == "unavailable"
    assert combo["reason"] == "unavailable — fewer than three distinct eligible priced fixtures"
    assert combo["legs"] == []


def test_individual_price_tiers_are_visible_and_minimal() -> None:
    rows = [row("M", "A", "B", 0.90), row("M", "C", "D", 0.90)]
    preferred = by_type(build(rows, [fixture("A", "B", {"M": 1.25}), fixture("C", "D", {"M": 1.30})]), "best2")
    assert preferred["construction"]["individual_price_tier"] == "preferred"
    assert preferred["construction"]["individual_floor_relaxed"] is False

    relaxed = by_type(build(rows, [fixture("A", "B", {"M": 1.15}), fixture("C", "D", {"M": 1.30})]), "best2")
    assert relaxed["construction"]["individual_price_tier"] == "relaxed_1_10"
    assert relaxed["construction"]["individual_floor_message"] == "preferred individual-odds floor relaxed to 1.10"

    lowest = by_type(build(rows, [fixture("A", "B", {"M": 1.05}), fixture("C", "D", {"M": 1.30})]), "best2")
    assert lowest["construction"]["individual_price_tier"] == "relaxed_below_1_10"
    assert lowest["construction"]["individual_floor_message"] == (
        "individual-odds preference relaxed below 1.10; lowest available prices used"
    )


def test_a_preferred_price_combination_is_not_replaced_by_a_cheaper_leg() -> None:
    rows = [row("M1", "A", "B", 0.90), row("M2", "A", "B", 0.90), row("M", "C", "D", 0.90)]
    fixtures = [fixture("A", "B", {"M1": 1.30, "M2": 1.15}), fixture("C", "D", {"M": 1.30})]
    best2 = by_type(build(rows, fixtures), "best2")
    assert best2["construction"]["individual_price_tier"] == "preferred"
    assert all(leg["odds"] == pytest.approx(1.30) for leg in best2["legs"])
    assert {leg["m"] for leg in best2["legs"]} == {"M1", "M"}


def test_a_cheap_fixture_cannot_supply_more_than_one_ticket_market() -> None:
    rows = [row("M", "A", "B", 0.90), row("M", "C", "D", 0.90)]
    fixtures = [fixture("A", "B", {"M": 1.02}), fixture("C", "D", {"M": 1.40})]
    best2 = by_type(build(rows, fixtures), "best2")
    assert best2["construction"]["individual_price_tier"] == "relaxed_below_1_10"


def test_fallback_ladder_is_explicit_and_deterministic() -> None:
    rows = [row("M", "A", "B", 0.60), row("M", "C", "D", 0.60), row("M", "E", "F", 0.60)]
    fixtures = [fixture("A", "B", {"M": 1.20}), fixture("C", "D", {"M": 1.20}), fixture("E", "F", {"M": 1.20})]
    combo = ticket_construction._build_one(menu(rows, fixtures), "around5")
    assert combo["status"] == "available"
    assert combo["combined_odds"] == pytest.approx(1.728)
    assert combo["construction"]["band"] == "below_floor"
    assert combo["construction"]["band_message"] == "below meaningful payout floor; highest available payout"
    assert combo["construction"]["achieved_odds"] == pytest.approx(1.728)


def test_outside_band_fallback_uses_the_nearest_boundary_above_the_floor() -> None:
    rows = [row("M", "A", "B", 0.70), row("M", "C", "D", 0.70)]
    fixtures = [fixture("A", "B", {"M": 2.20}), fixture("C", "D", {"M": 2.20})]
    around3 = ticket_construction._build_one(menu(rows, fixtures), "around3")
    assert around3["combined_odds"] == pytest.approx(2.20)
    assert around3["construction"]["band"] == "outside"
    assert around3["construction"]["band_message"] == "outside preferred band"


def test_fewer_than_the_required_fixtures_is_unavailable_without_filler() -> None:
    payload = build([row("M", "A", "B", 0.70)], [fixture("A", "B", {"M": 2.0})])
    best2 = by_type(payload, "best2")
    assert best2["status"] == "unavailable"
    assert best2["reason"] == "unavailable — fewer than two distinct eligible priced fixtures"
    assert best2["flat_stake"] == 0.0
    around3 = by_type(payload, "around3")
    assert around3["status"] == "available"
    assert around3["flat_stake"] == 30.0
    around5 = by_type(payload, "around5")
    assert around5["status"] == "unavailable"
    assert around5["reason"] == "unavailable — fewer than three distinct eligible priced fixtures"
    assert around5["flat_stake"] == 0.0


def test_enough_fixtures_never_produces_a_zero_proposal_round() -> None:
    rows = [row("M", "A", "B", 0.70), row("M", "C", "D", 0.70), row("M", "E", "F", 0.70)]
    fixtures = [fixture("A", "B", {"M": 1.20}), fixture("C", "D", {"M": 1.20}), fixture("E", "F", {"M": 1.20})]
    payload = build(rows, fixtures)
    assert [item["status"] for item in payload["proposals"]] == ["available"] * 3
    assert all(item["flat_stake"] > 0 for item in payload["proposals"])


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
        assert all(leg["odds"] > 1.0 for leg in proposal["legs"])


def test_overlap_prefers_disjoint_then_exact_shared_legs() -> None:
    rows = [row("M", "A", "B", 0.40), row("M", "C", "D", 0.40)]
    fixtures = [fixture("A", "B", {"M": 2.50}), fixture("C", "D", {"M": 2.50})]
    payload = build(rows, fixtures)
    assert by_type(payload, "best2")["construction"]["overlap_relaxed"] is False
    around3 = by_type(payload, "around3")
    assert around3["construction"]["overlap_relaxed"] is True
    assert around3["construction"]["overlap_level"] == "shared_leg"
    assert around3["construction"]["overlap_message"] == "cross-ticket overlap relaxation"
    assert payload["policy"]["mel"]["supported"] is True


def test_unsupported_same_fixture_dependence_zeroes_mel_exposure() -> None:
    rows = [
        row("M1", "A", "B", 0.90), row("M2", "A", "B", 0.30), row("M1", "C", "D", 0.90),
    ]
    fixtures = [fixture("A", "B", {"M1": 1.20, "M2": 3.00}), fixture("C", "D", {"M1": 1.20})]
    payload = build(rows, fixtures)
    assert payload["policy"]["mel"]["supported"] is False
    assert payload["policy"]["mel"]["reason"] == "unsupported same-fixture dependence"
    assert by_type(payload, "best2")["flat_stake"] == 50.0
    assert by_type(payload, "around3")["flat_stake"] == 30.0
    for proposal in payload["proposals"]:
        if proposal["status"] != "available":
            continue
        assert proposal["mel"]["stake"] == 0.0
        assert proposal["mel"]["message"] == "unsupported same-fixture dependence"
        assert proposal["adaptive"]["stake"] == 0.0


def test_shared_legs_across_all_three_are_relaxed_and_mel_supported() -> None:
    rows = [row("M", "A", "B", 0.70), row("M", "C", "D", 0.70), row("M", "E", "F", 0.50)]
    fixtures = [fixture("A", "B", {"M": 1.50}), fixture("C", "D", {"M": 1.50}), fixture("E", "F", {"M": 3.00})]
    payload = build(rows, fixtures)
    combo = by_type(payload, "around5")
    assert combo["status"] == "available"
    assert len(combo["legs"]) == 3
    assert combo["construction"]["overlap_relaxed"] is True
    assert payload["policy"]["mel"]["supported"] is True
    assert sum(item["mel"]["stake"] for item in payload["proposals"] if item["status"] == "available") == pytest.approx(20.0)
    fixture_sets = [{leg_key for leg_key in [(leg["d"], leg["h"], leg["a"]) for leg in item["legs"]]}
                    for item in payload["proposals"] if item["status"] == "available"]
    assert not (fixture_sets[0] & fixture_sets[1] & fixture_sets[2])


def test_overlap_and_selection_are_deterministic() -> None:
    rows = [row("M", "A", "B", 0.70), row("M", "C", "D", 0.70), row("M", "E", "F", 0.70)]
    fixtures = [fixture("A", "B", {"M": 1.70}), fixture("C", "D", {"M": 1.70}), fixture("E", "F", {"M": 1.70})]
    first = build(rows, fixtures)
    second = build(rows, fixtures)
    assert json.dumps(first["proposals"], sort_keys=True) == json.dumps(second["proposals"], sort_keys=True)


def test_no_58_or_vetting_gate_lets_low_probability_legs_enter() -> None:
    rows = [row("M", "A", "B", 0.10), row("M", "C", "D", 0.12), row("M", "E", "F", 0.15)]
    fixtures = [fixture("A", "B", {"M": 1.80}), fixture("C", "D", {"M": 1.80}), fixture("E", "F", {"M": 1.80})]
    combo = ticket_construction._build_one(menu(rows, fixtures), "around5")
    assert combo["status"] == "available"
    assert len(combo["legs"]) == 3
    assert combo["combined_probability"] == pytest.approx(0.10 * 0.12 * 0.15)


def test_below_meaningful_floor_uses_the_highest_available_payout() -> None:
    rows = [row("M", "A", "B", 0.90)]
    fixtures = [fixture("A", "B", {"M": 1.50})]
    around3 = ticket_construction._build_one(menu(rows, fixtures), "around3")
    assert around3["status"] == "available"
    assert around3["combined_odds"] == pytest.approx(1.50)
    assert around3["construction"]["band"] == "below_floor"
    assert around3["construction"]["band_message"] == "below meaningful payout floor; highest available payout"


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
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 3
    assert payload["construction_version"] == "ticket-construction-v3"
    assert payload["proposals"][0]["construction"]["policy"] == "ticket-construction-v3"


def test_existing_schema_two_file_is_readable_and_never_regenerated(tmp_path: Path) -> None:
    prices = tmp_path / "prices"
    picks = tmp_path / "picks"
    (prices / "proposals").mkdir(parents=True)
    picks.mkdir()
    old = {
        "schema_version": 2, "round_date": DATE,
        "proposals": [
            {"type": key, "status": "unavailable", "reason": "frozen v2"}
            for key in proposals.TARGETS
        ],
    }
    path = prices / "proposals" / f"{DATE}.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    before = path.read_bytes()
    again = proposals.ensure_proposals(
        DATE, document([row("M", "A", "B", 0.70)]),
        snapshot([fixture("A", "B", {"M": 2.0})]), prices, picks,
    )
    assert again["schema_version"] == 2
    assert path.read_bytes() == before
    assert proposals.missing_required_proposals(prices) == []


def test_v2_and_v3_ledgers_are_separate(tmp_path: Path) -> None:
    prices = tmp_path / "prices"
    picks = tmp_path / "picks"
    (prices / "proposals").mkdir(parents=True)
    picks.mkdir()
    v2 = {
        "schema_version": 2, "round_date": "2026-11-20",
        "proposals": [{
            "type": "best2", "status": "available", "flat_stake": 50.0,
            "legs": [{"d": "E0", "h": "A", "a": "B", "m": "M", "pc": 0.7, "odds": 2.0}],
            "adaptive": {"stake": 10.0}, "policies": {"mel": {"stake": 10.0}},
        }],
    }
    v3 = {
        "schema_version": 3, "round_date": "2026-11-21",
        "proposals": [{
            "type": "best2", "status": "available", "flat_stake": 50.0,
            "legs": [{"d": "E0", "h": "C", "a": "D", "m": "M", "pc": 0.7, "odds": 2.0}],
            "adaptive": {"stake": 10.0}, "policies": {"mel": {"stake": 10.0}},
        }],
    }
    (prices / "proposals" / "2026-11-20.json").write_text(json.dumps(v2), encoding="utf-8")
    (prices / "proposals" / "2026-11-21.json").write_text(json.dumps(v3), encoding="utf-8")
    before = (prices / "proposals" / "2026-11-20.json").read_bytes()
    (picks / "2026-11-20.json").write_text(json.dumps({"rows": []}), encoding="utf-8")
    (picks / "2026-11-21.json").write_text(json.dumps({"rows": []}), encoding="utf-8")
    aggregate = proposals.aggregate_records(prices, picks)
    assert aggregate["construction_version"] == "ticket-construction-v3"
    assert aggregate["counts"]["rounds"] == 1
    assert aggregate["counts"]["legacy_rounds"] == 1
    assert aggregate["types"]["best2"]["tickets"] == 1
    assert (prices / "proposals" / "2026-11-20.json").read_bytes() == before
    state = proposals.replay_adaptive(prices, picks, DATE)
    assert state["bankroll"] == 1000.0


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


def test_replay_uses_only_prior_v3_settled_information(tmp_path: Path) -> None:
    prices = tmp_path / "prices"
    picks = tmp_path / "picks"
    proposals_dir = prices / "proposals"
    proposals_dir.mkdir(parents=True)
    picks.mkdir()
    older = {
        "schema_version": 3, "round_date": "2026-11-20", "proposals": [{
            "type": "best2", "status": "available", "combined_odds": 2.0,
            "legs": [{"d": "E0", "h": "A", "a": "B", "m": "A", "odds": 2.0}],
            "adaptive": {"stake": 10.0},
        }],
    }
    legacy = {
        "schema_version": 2, "round_date": "2026-11-19", "proposals": [{
            "type": "best2", "status": "available", "combined_odds": 10.0,
            "legs": [{"d": "E0", "h": "L", "a": "M", "m": "A", "odds": 10.0}],
            "adaptive": {"stake": 500.0},
        }],
    }
    future = {
        "schema_version": 3, "round_date": DATE, "proposals": [{
            "type": "best2", "status": "available", "combined_odds": 10.0,
            "legs": [{"d": "E0", "h": "X", "a": "Y", "m": "A", "odds": 10.0}],
            "adaptive": {"stake": 999.0},
        }],
    }
    (proposals_dir / "2026-11-19.json").write_text(json.dumps(legacy), encoding="utf-8")
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
        "schema_version": 3, "round_date": "2026-11-20",
        "proposals": [{
            "type": "best2", "label": "High-probability", "status": "available", "flat_stake": 50.0,
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
    assert aggregate["construction_version"] == "ticket-construction-v3"
    assert aggregate["evaluation_id"] == "ticket-construction-v3+mel-v1"
    text = (web / "proposed-tickets-record.json").read_text(encoding="utf-8").lower()
    assert "\"odds\"" not in text
    assert "\"prices\"" not in text
    assert "\"combined_odds\"" not in text
    assert "not a profit guarantee" in text


def test_readiness_requires_a_frozen_proposal_only_after_activation(tmp_path: Path) -> None:
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

    frozen = {
        "schema_version": 2, "round_date": "2026-11-24",
        "proposals": [
            {"type": key, "status": "unavailable", "reason": "frozen legacy"}
            for key in proposals.TARGETS
        ],
    }
    (prices / "proposals").mkdir()
    (prices / "proposals" / "2026-11-24.json").write_text(json.dumps(frozen), encoding="utf-8")
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
