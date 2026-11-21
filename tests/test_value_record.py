"""Value tracking: min play, price gate, one-per-match and flat-stake maths."""
from __future__ import annotations

import pytest

from pathlib import Path

from pipeline import vetting
from pipeline.mozzart import value_record

ROOT = Path(__file__).resolve().parents[1]


def test_web_value_contract_is_t3_t4_t6_only() -> None:
    source = (ROOT / "web" / "lib" / "vetted.ts").read_text(encoding="utf-8")
    assert "const VALUE_CHECKS = ['t3', 't4', 't6'] as const;" in source
    start = source.index("export function selectValue")
    end = source.index("\n}", start) + 2
    block = source[start:end]
    assert "VALUE_CHECKS.every" in block
    assert "t1" not in block


def test_min_play_is_ceil_two_decimals() -> None:
    assert value_record.min_play(0.50) == pytest.approx(2.10)
    assert value_record.min_play(0.60) == pytest.approx(1.75)
    assert value_record.min_play(0.79) == pytest.approx(1.33)


def row(
    market: str = "BTTS:GG", price: float = 2.20, status: str = "landed",
    home_rate: float = 0.50, lr: float = 0.40, model: float = 0.45,
    probability: float = 0.50, away_rate: float = 0.45,
) -> dict:
    return {
        "d": "E0", "h": "A", "a": "B", "m": market, "p": model, "pc": probability,
        "lr": lr, "ln": 5000, "hr": home_rate, "hn": 20, "ar": away_rate, "an": 20, "st": status,
    }


def snapshot(prices: dict[str, float], date: str = "2026-11-21") -> list[dict]:
    return [{"round_date": date, "fixtures": [{"div": "E0", "home": "A", "away": "B", "prices": prices}]}]


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


def test_t1_false_is_included_by_value_tracking() -> None:
    # p=50%, usual=45%: the lift gate (t1) is false, but t3/t4/t6 pass.
    candidate = row(lr=0.45)
    _, checks = vetting.type_evaluate(value_record._candidate(candidate, 2.20))
    by_id = {check["id"]: check["passed"] for check in checks}
    assert by_id["t1"] is False
    assert by_id["t3"] and by_id["t4"] and by_id["t6"]
    payload = value_record.build(
        [{"date": "2026-11-21", "label": "Sat 21 Nov", "rows": [candidate]}],
        snapshot({"BTTS:GG": 2.20}),
    )
    assert payload["cumulative"]["bets"] == 1
    assert payload["cumulative"]["profit"] == pytest.approx(1.2)


def test_each_required_team_or_agreement_check_excludes() -> None:
    cases = [
        (row(home_rate=0.30), 2.20),  # t3 team records
        (row(model=0.70), 2.20),  # t4 agreement
        (row(probability=0.15, model=0.10, lr=0.10, home_rate=0.12, away_rate=0.11), 7.20),  # t6 fair
    ]
    for candidate, price in cases:
        payload = value_record.build(
            [{"date": "2026-11-21", "label": "Sat 21 Nov", "rows": [candidate]}],
            snapshot({"BTTS:GG": price}),
        )
        assert payload["cumulative"]["bets"] == 0


def test_below_min_play_and_fair_cap_are_excluded() -> None:
    below = value_record.build(
        [{"date": "2026-11-21", "label": "Sat 21 Nov", "rows": [row()]}],
        snapshot({"BTTS:GG": 2.09}),
    )
    assert below["cumulative"]["bets"] == 0
    longshot = row(probability=0.15, model=0.10, lr=0.10, home_rate=0.12, away_rate=0.11)
    fair_cap = value_record.build(
        [{"date": "2026-11-21", "label": "Sat 21 Nov", "rows": [longshot]}],
        snapshot({"BTTS:GG": 7.20}),
    )
    assert fair_cap["cumulative"]["bets"] == 0


def test_pending_void_and_unpriced_rows_are_excluded() -> None:
    rounds = [{
        "date": "2026-11-21", "label": "Sat 21 Nov",
        "rows": [row(status="pending"), row(status="void"), row(status="landed")],
    }]
    priced = value_record.build(rounds, snapshot({"BTTS:GG": 2.20}))
    assert priced["cumulative"]["bets"] == 1
    assert priced["cumulative"]["landed"] == 1
    unpriced = value_record.build(rounds, snapshot({"BTTS:NG": 2.50}))
    assert unpriced["cumulative"]["bets"] == 0


def test_value_bets_are_sorted_by_edge() -> None:
    rows = [row(), {**row(), "h": "C", "a": "D"}]
    snapshots = [{
        "round_date": "2026-11-21",
        "fixtures": [
            {"div": "E0", "home": "A", "away": "B", "prices": {"BTTS:GG": 2.20}},
            {"div": "E0", "home": "C", "away": "D", "prices": {"BTTS:GG": 2.50}},
        ],
    }]
    bets = value_record._value_bets(
        [{"date": "2026-11-21", "label": "Sat 21 Nov", "rows": rows}], snapshots
    )["2026-11-21"]
    assert [bet["odds"] for bet in bets] == [2.50, 2.20]
    assert bets[0]["edge"] > bets[1]["edge"]


def test_round_date_price_isolation() -> None:
    rounds = [
        {"date": "2026-11-21", "label": "Sat 21 Nov", "rows": [row(status="landed")]},
        {"date": "2026-11-22", "label": "Sun 22 Nov", "rows": [row(status="lost")]},
    ]
    snapshots = snapshot({"BTTS:GG": 2.20}, "2026-11-21") + snapshot({"BTTS:GG": 2.50}, "2026-11-22")
    payload = value_record.build(rounds, snapshots)
    by_date = {item["date"]: item["summary"] for item in payload["rounds"]}
    assert by_date["2026-11-21"]["profit"] == pytest.approx(1.2)
    assert by_date["2026-11-21"]["needed"] == pytest.approx(1 / 2.2, abs=1e-4)
    assert by_date["2026-11-22"]["profit"] == pytest.approx(-1.0)
    assert by_date["2026-11-22"]["needed"] == pytest.approx(1 / 2.5, abs=1e-4)
    assert payload["cumulative"]["profit"] == pytest.approx(0.2)
    assert payload["cumulative"]["needed"] == pytest.approx(1 / 2.2 + 1 / 2.5, abs=1e-4)
    assert payload["profit_series"][-1]["profit"] == pytest.approx(0.2)
