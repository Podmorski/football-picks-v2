"""Return at Mozzart price on a known sequence."""
from __future__ import annotations

from pipeline.mozzart import vetted_record


def row(home, away, market, pc, p, status):
    return {
        "d": "E0", "h": home, "a": away, "m": market, "pc": pc, "p": p,
        "lr": 0.40, "ln": 5000, "hr": 0.50, "hn": 20, "ar": 0.45, "an": 20, "st": status,
    }


def test_return_at_mozzart_price_known_sequence() -> None:
    rounds = [{
        "date": "2026-11-21", "kind": "round",
        "rows": [
            row("A", "B", "BTTS:GG", 0.60, 0.45, "landed"),
            row("C", "D", "RESULT:1", 0.55, 0.45, "lost"),
            row("E", "F", "BTTS:GG", 0.60, 0.45, "landed"),
        ],
    }]
    snapshots = [{
        "round_date": "2026-11-21",
        "fixtures": [
            {"div": "E0", "home": "A", "away": "B", "prices": {"BTTS:GG": 2.0}},
            {"div": "E0", "home": "C", "away": "D", "prices": {"RESULT:1": 3.0}},
            {"div": "E0", "home": "E", "away": "F", "prices": {"BTTS:GG": 1.0}},
        ],
    }]
    out = vetted_record.aggregate(rounds, snapshots)
    all_scope = out["cumulative"]["all"]
    assert all_scope["n"] == 3
    assert all_scope["landed"] == round(2 / 3, 4)
    # +1.0 (2.0 landed), -1.0 (3.0 lost), 0.0 (1.0 landed) -> mean 0.0
    assert all_scope["return"] == 0.0
    # The 1.0 price is below fair, so it is not in the value scopes.
    assert out["cumulative"]["passing_value"]["n"] == 2
    assert out["cumulative"]["any_value"]["n"] == 2
    assert out["rounds"][0]["date"] == "2026-11-21"


def test_round_date_price_isolation() -> None:
    rounds = [
        {"date": "2026-11-21", "kind": "round", "rows": [row("A", "B", "BTTS:GG", 0.60, 0.45, "landed")]},
        {"date": "2026-11-22", "kind": "round", "rows": [row("A", "B", "BTTS:GG", 0.60, 0.45, "lost")]},
    ]
    snapshots = [
        {"round_date": "2026-11-21", "fixtures": [{"div": "E0", "home": "A", "away": "B", "prices": {"BTTS:GG": 2.0}}]},
        {"round_date": "2026-11-22", "fixtures": [{"div": "E0", "home": "A", "away": "B", "prices": {"BTTS:GG": 3.0}}]},
    ]
    out = vetted_record.aggregate(rounds, snapshots)
    by_date = {item["date"]: item for item in out["rounds"]}
    assert by_date["2026-11-21"]["all"]["n"] == 1
    assert by_date["2026-11-21"]["all"]["return"] == 1.0
    assert by_date["2026-11-22"]["all"]["n"] == 1
    assert by_date["2026-11-22"]["all"]["return"] == -1.0
    assert out["cumulative"]["all"]["n"] == 2
    assert out["cumulative"]["all"]["return"] == 0.0
