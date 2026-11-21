"""Value tracking: min play, price gate, one-per-match and flat-stake maths."""
from __future__ import annotations

import pytest

from pipeline.mozzart import value_record


def test_min_play_is_ceil_two_decimals() -> None:
    assert value_record.min_play(0.50) == pytest.approx(2.10)
    assert value_record.min_play(0.60) == pytest.approx(1.75)
    assert value_record.min_play(0.79) == pytest.approx(1.33)


def row(market: str = "BTTS:GG", price: float = 2.20, status: str = "landed", home_rate: float = 0.50) -> dict:
    return {
        "d": "E0", "h": "A", "a": "B", "m": market, "p": 0.45, "pc": 0.50,
        "lr": 0.40, "ln": 5000, "hr": home_rate, "hn": 20, "ar": 0.45, "an": 20, "st": status,
    }


def snapshot(prices: dict[str, float]) -> list[dict]:
    return [{"round_date": "2026-11-21", "fixtures": [{"div": "E0", "home": "A", "away": "B", "prices": prices}]}]


def test_tracking_maths_on_a_known_sequence() -> None:
    bets = [
        {"date": "d1", "landed": True, "profit": 1.0, "needed": 0.5},
        {"date": "d1", "landed": False, "profit": -1.0, "needed": 1 / 3},
        {"date": "d2", "landed": True, "profit": 3.0, "needed": 0.25},
    ]
    summary = value_record._summary(bets)
    assert summary["bets"] == 3
    assert summary["landed"] == 2
    assert summary["needed"] == pytest.approx(1.0833, abs=1e-4)
    assert summary["profit"] == pytest.approx(3.0)
    assert summary["return"] == pytest.approx(1.0)
    low, high = summary["ci"]
    assert low <= 1.0 <= high


def test_value_only_when_price_reaches_min_play() -> None:
    rounds = [{"date": "2026-11-21", "label": "Sat 21 Nov", "rows": [row()]}]
    below = value_record.build(rounds, snapshot({"BTTS:GG": 2.09}))
    assert below["cumulative"]["bets"] == 0
    at = value_record.build(rounds, snapshot({"BTTS:GG": 2.10}))
    assert at["cumulative"]["bets"] == 1


def test_one_value_bet_per_match_by_highest_edge() -> None:
    rows = [row("BTTS:GG", 2.20), row("BTTS:NG", 2.50)]
    rounds = [{"date": "2026-11-21", "label": "Sat 21 Nov", "rows": rows}]
    payload = value_record.build(rounds, snapshot({"BTTS:GG": 2.20, "BTTS:NG": 2.50}))
    assert payload["cumulative"]["bets"] == 1
    assert payload["cumulative"]["landed"] == 1
    assert payload["cumulative"]["needed"] == pytest.approx(0.4)
    assert payload["cumulative"]["profit"] == pytest.approx(1.5)
    assert payload["groups"]["BTTS"]["bets"] == 1
    assert payload["bands"]["2-3"]["bets"] == 1
    assert payload["rounds"][0]["date"] == "2026-11-21"


def test_pending_rows_and_thin_records_are_excluded() -> None:
    rounds = [{
        "date": "2026-11-21", "label": "Sat 21 Nov",
        "rows": [row(status="pending"), row(home_rate=0.30)],
    }]
    payload = value_record.build(rounds, snapshot({"BTTS:GG": 2.20}))
    assert payload["cumulative"]["bets"] == 0
