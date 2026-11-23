"""Forward proposal readiness: activation, eligible round, counts, privacy."""
from __future__ import annotations

import json

from pipeline import forward_proposals, proposed_tickets


def valid_proposal(key: str, band: str = "preferred") -> dict:
    return {
        "type": key, "status": "available", "legs": [],
        "model_ev": -0.1 if key == "around5" else 0.2,
        "construction": {"band": band, "individual_floor_relaxed": key == "around5",
                          "overlap_relaxed": key == "around3", "method": "bounded_dp" if key == "around5" else "exact"},
    }


def test_eligible_round_counts_and_coverage(tmp_path) -> None:
    prices = tmp_path / "prices"; (prices / "rounds").mkdir(parents=True); (prices / "proposals").mkdir()
    (prices / "rounds" / "2026-11-24.json").write_text(json.dumps({
        "round_date": "2026-11-24", "fixtures": [
            {"div": "E0", "home": "A", "away": "B", "prices": {"BTTS:GG": 2.0, "RESULT:1": 1.8}},
            {"div": "E0", "home": "C", "away": "D", "prices": {}},
        ], "started_not_priced": [{"div": "E0"}], "unmatched_fixtures": [{"div": "E0"}, {"div": "E0"}],
    }), encoding="utf-8")
    (prices / "proposals" / "2026-11-24.json").write_text(json.dumps({
        "schema_version": proposed_tickets.SCHEMA_VERSION,
        "proposals": [valid_proposal(key, "outside" if key == "around3" else "preferred") for key in proposed_tickets.TARGETS],
    }), encoding="utf-8")
    web = tmp_path / "web"
    payload = forward_proposals.build(prices, tmp_path / "picks", web)
    assert payload["eligible_round"] == proposed_tickets.PROPOSAL_ACTIVATION_DATE
    assert payload["state"] == "frozen proposals available"
    assert payload["errors"] == []
    assert payload["counts"]["available"] == 3
    assert payload["counts"]["bands"] == {"preferred": 2, "outside": 1}
    assert payload["counts"]["individual_floor_relaxed"] == 1
    assert payload["counts"]["overlap_relaxed"] == 1
    assert payload["counts"]["negative_model_ev"] == 1
    assert payload["price_coverage"] == {
        "snapshot_rounds": 1, "fixtures": 2, "priced_fixtures": 1, "priced_markets": 2,
        "started_not_priced": 1, "unmatched_fixtures": 2,
    }
    assert '"odds"' not in json.dumps(payload).lower()


def test_no_snapshot_is_awaiting_first_eligible_round(tmp_path) -> None:
    payload = forward_proposals.build(None, tmp_path / "picks", tmp_path / "web")
    assert payload["eligible_round"] is None
    assert payload["state"] == "awaiting first eligible published round with fixtures and a usable snapshot"
    assert payload["errors"]
    assert payload["counts"]["tickets"] == 0
