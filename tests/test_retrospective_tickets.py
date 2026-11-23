"""Retrospective model-fair tickets: optimisation, immutability and settlement."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import retrospective_tickets as retrospective
from pipeline.proposed_tickets import choose_target

ROOT = Path(__file__).resolve().parents[1]


def row(home: str, away: str, market: str, pc: float, status: str = "pending") -> dict:
    return {
        "d": "E0", "k": "15:00", "h": home, "a": away, "m": market,
        "p": pc, "pc": pc, "st": status,
    }


def document(rows: list[dict], date: str = "2026-11-14") -> dict:
    return {"date": date, "kind": "example", "rows": rows}


def test_retrospective_pool_is_inclusive_one_per_match_and_hides_correct_score() -> None:
    doc = document([
        row("A", "B", "BTTS:GG", 0.58),
        row("A", "B", "RESULT:1", 0.70),
        row("C", "D", "CORRECT_SCORE:2:1", 0.99),
        row("C", "D", "GOAL_RANGE_FT:1+", 0.80),
        row("E", "F", "RESULT:X", 0.57),
    ])
    pool = retrospective.eligible_pool(doc)
    assert [(leg["h"], leg["m"], leg["pc"]) for leg in pool] == [
        ("C", "GOAL_RANGE_FT:1+", 0.80),
        ("A", "RESULT:1", 0.70),
    ]


def test_fair_target_uses_fair_odds_and_maximises_probability() -> None:
    pool = [
        {"d": "E0", "h": "A", "a": "B", "k": "15:00", "m": "A", "pc": 0.90, "fair": 1.80},
        {"d": "E0", "h": "C", "a": "D", "k": "15:00", "m": "B", "pc": 0.90, "fair": 1.70},
        {"d": "E0", "h": "E", "a": "F", "k": "15:00", "m": "C", "pc": 0.80, "fair": 1.50},
    ]
    legs, reason = choose_target(pool, 3.0, 2.70, 3.30, price_key="fair")
    assert legs and reason == ""
    assert [leg["h"] for leg in legs] == ["A", "C"]
    assert pytest.approx(3.06) == legs[0]["fair"] * legs[1]["fair"]
    assert pytest.approx(0.81) == legs[0]["pc"] * legs[1]["pc"]


def test_generation_settlement_preserves_legs_and_updates_status(tmp_path: Path) -> None:
    picks = tmp_path / "picks"
    picks.mkdir()
    rows = [row("A", "B", "GOAL_RANGE_FT:1+", 0.90), row("C", "D", "GOAL_RANGE_FT:1+", 0.80)]
    (picks / "2026-11-14.json").write_text(json.dumps(document(rows)), encoding="utf-8")
    payload = retrospective.generate_payload(picks)
    round_doc = payload["rounds"][0]
    original_legs = json.dumps([proposal["legs"] for proposal in round_doc["proposals"]], sort_keys=True)
    assert round_doc["proposals"][0]["settlement"]["status"] == "pending"
    assert round_doc["proposals"][0]["settlement"]["source_pending"] is True

    settled_rows = [
        row("A", "B", "GOAL_RANGE_FT:1+", 0.90, "landed"),
        row("C", "D", "GOAL_RANGE_FT:1+", 0.80, "landed"),
    ]
    (picks / "2026-11-14.full.json").write_text(json.dumps(document(settled_rows)), encoding="utf-8")
    updated = retrospective.settle_payload(payload, picks)
    assert json.dumps([proposal["legs"] for proposal in updated["rounds"][0]["proposals"]], sort_keys=True) == original_legs
    assert updated["rounds"][0]["proposals"][0]["settlement"]["status"] == "landed"
    assert updated["rounds"][0]["proposals"][0]["settlement"]["source_pending"] is False


def test_void_pending_and_lost_paper_rules() -> None:
    proposal = {
        "status": "available", "flat_stake": 50.0,
        "legs": [
            {"d": "E0", "h": "A", "a": "B", "m": "A", "fair": 2.0},
            {"d": "E0", "h": "C", "a": "D", "m": "B", "fair": 2.5},
        ],
    }
    cases = [
        (["landed", "landed"], "landed", 250.0, 200.0),
        (["lost", "landed"], "lost", 0.0, -50.0),
        (["pending", "landed"], "pending", None, None),
        (["void", "void"], "void", 50.0, 0.0),
        (["void", "landed"], "landed", 125.0, 75.0),
    ]
    for states, want_status, want_return, want_profit in cases:
        item = {**proposal, "legs": [dict(leg) for leg in proposal["legs"]]}
        statuses = {retrospective._leg_key(leg): state for leg, state in zip(item["legs"], states)}
        retrospective._settle(item, statuses)
        assert item["settlement"]["status"] == want_status
        assert item["settlement"]["return"] == want_return
        assert item["settlement"]["profit"] == want_profit


def test_committed_retrospective_file_has_three_rounds_and_no_prices() -> None:
    payload = json.loads((ROOT / "web" / "public" / "data" / "retrospective-tickets.json").read_text(encoding="utf-8"))
    assert payload["definition_version"] == "retrospective-model-fair-v1"
    assert [row["round_date"] for row in payload["rounds"]] == list(retrospective.DATES)
    assert all(row["disclaimer"] == retrospective.DISCLAIMER for row in payload["rounds"])
    assert all(row["fair_odds_note"] == retrospective.FAIR_NOTE for row in payload["rounds"])
    for round_doc in payload["rounds"]:
        assert len(round_doc["proposals"]) == 3
        for proposal in round_doc["proposals"]:
            assert proposal["status"] in ("available", "unavailable")
            if proposal["status"] == "unavailable":
                assert proposal["reason"]
            else:
                assert 2 <= len(proposal["legs"]) <= 5
                assert all(leg["pc"] >= 0.58 for leg in proposal["legs"])
                assert not any(leg["m"].startswith("CORRECT_SCORE:") for leg in proposal["legs"])
    text = json.dumps(payload).lower()
    for forbidden in ('"odds"', '"prices"', '"price"', '"adaptive"', '"snapshot_identity"', '"mozzart"'):
        assert forbidden not in text
