"""Forward validation: whole-round resampling, replay, power and safety."""
from __future__ import annotations

import json

from pipeline import forward_validation, ranking


def leg(home: str, away: str, market: str = "BTTS:GG") -> dict:
    return {"d": "E0", "h": home, "a": away, "m": market, "pc": 0.6, "fair": 1.6667, "odds": 2.0}


def proposal(key: str, legs: list[dict], flat: float, mel: float) -> dict:
    return {
        "type": key, "status": "available", "legs": legs,
        "combined_probability": 0.36, "combined_odds": 4.0, "model_ev": 0.44,
        "flat_stake": flat, "policies": {"flat": {"stake": flat}, "mel": {"stake": mel}},
        "construction": {"band": "preferred", "individual_floor_relaxed": False,
                          "overlap_relaxed": False, "method": "exact"},
    }


def write_picks(picks, date: str, statuses: dict[tuple, str]) -> None:
    rows = []
    for (home, away, market), status in statuses.items():
        rows.append({
            "d": "E0", "k": "15:00", "h": home, "a": away, "m": market,
            "p": 0.6, "pc": 0.6, "pl": 0.6, "pp": 0.6, "lr": 0.5, "ln": 100,
            "hr": 0.5, "hn": 10, "ar": 0.5, "an": 10, "c": "Medium", "s": 0.1,
            "st": status, "ht": "1-0", "ft": "2-1",
        })
    ranking.publish({"date": date, "label": date, "weekday": "Sunday", "kind": "round", "rows": rows}, picks, picks)


def test_whole_round_metrics_and_no_prices_in_output(tmp_path) -> None:
    picks = tmp_path / "picks"; picks.mkdir()
    prices = tmp_path / "prices"; (prices / "proposals").mkdir(parents=True)
    first = [leg("A", "B"), leg("C", "D")]
    second = [leg("E", "F"), leg("G", "H")]
    write_picks(picks, "2026-11-21", {("A", "B", "BTTS:GG"): "landed", ("C", "D", "BTTS:GG"): "landed"})
    write_picks(picks, "2026-11-22", {("E", "F", "BTTS:GG"): "lost", ("G", "H", "BTTS:GG"): "lost"})
    (prices / "proposals" / "2026-11-21.json").write_text(json.dumps({
        "schema_version": 3, "round_date": "2026-11-21", "proposals": [proposal("best2", first, 50.0, 20.0)],
    }), encoding="utf-8")
    (prices / "proposals" / "2026-11-22.json").write_text(json.dumps({
        "schema_version": 3, "round_date": "2026-11-22", "proposals": [proposal("best2", second, 50.0, 20.0)],
    }), encoding="utf-8")

    payload = forward_validation.build(prices, picks)
    assert payload["counts"] == {
        "rounds": 2, "terminal_rounds": 2, "tickets": 2, "void": 0, "pending": 0,
        "void_frequency": 0.0, "pending_frequency": 0.0, "legacy_rounds": 0,
    }
    assert payload["construction_version"] == "ticket-construction-v3"
    assert payload["evaluation_id"] == "ticket-construction-v3+mel-v1"
    assert payload["primary"]["flat"]["staked"] == 100.0
    assert payload["primary"]["flat"]["net"] == 100.0
    assert payload["primary"]["flat"]["roi"] == 1.0
    assert payload["primary"]["mel"]["staked"] == 40.0
    assert payload["primary"]["mel"]["net"] == 40.0
    assert payload["primary"]["mel"]["bootstrap"]["rounds"] == 2
    text = json.dumps(payload).lower()
    assert '"odds"' not in text and '"price"' not in text and '"prices"' not in text
    assert payload["state"] in ("accumulating", "positive evidence")
    assert payload["notes"]


def test_empty_store_is_honest(tmp_path) -> None:
    picks = tmp_path / "picks"; picks.mkdir()
    payload = forward_validation.build(tmp_path / "none", picks)
    assert payload["state"] == "no settled playable rounds"
    assert payload["power"]["n_star"] is None
    assert "fewer than two" in payload["power"]["reason"]
    assert payload["safety"]["identity_failure"] is False
    assert payload["construction_version"] == "ticket-construction-v3"


def test_v2_rounds_are_excluded_from_the_v3_validation(tmp_path) -> None:
    picks = tmp_path / "picks"; picks.mkdir()
    prices = tmp_path / "prices"; (prices / "proposals").mkdir(parents=True)
    write_picks(picks, "2026-11-21", {("A", "B", "BTTS:GG"): "landed", ("C", "D", "BTTS:GG"): "landed"})
    (prices / "proposals" / "2026-11-21.json").write_text(json.dumps({
        "schema_version": 2, "round_date": "2026-11-21",
        "proposals": [proposal("best2", [leg("A", "B"), leg("C", "D")], 50.0, 20.0)],
    }), encoding="utf-8")
    payload = forward_validation.build(prices, picks)
    assert payload["counts"]["rounds"] == 0
    assert payload["counts"]["legacy_rounds"] == 1
    assert payload["primary"]["flat"]["staked"] == 0.0
    assert payload["state"] == "no settled playable rounds"
