"""Picker grouping/sorting, ticket maths, and companion-file consistency."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import picker, ranking

GROUPS = {
    "RESULT:1": "Result & double chance",
    "RESULT:X": "Result & double chance",
    "RESULT:2": "Result & double chance",
    "GOAL_RANGE_FT:1+": "Goals",
    "GOAL_RANGE_FT:2+": "Goals",
    "BTTS:GG": "BTTS",
}


def row(home, away, market, pc, p=None, lr=0.4, k="15:00", d="E0"):
    return {"d": d, "h": home, "a": away, "m": market, "pc": pc, "p": p if p is not None else pc, "lr": lr, "k": k}


def test_group_picks_best_per_match() -> None:
    rows = [
        row("A", "B", "GOAL_RANGE_FT:2+", 0.60),
        row("A", "B", "BTTS:GG", 0.55),
        row("A", "B", "GOAL_RANGE_FT:1+", 0.85),
        row("C", "D", "GOAL_RANGE_FT:2+", 0.70),
    ]
    picked = picker.pick_rows(rows, "group:Goals", "all", GROUPS, min_fair=0.0)
    assert len(picked) == 2
    by_match = {(r["h"], r["a"]): r for r in picked}
    assert by_match[("A", "B")]["m"] == "GOAL_RANGE_FT:1+"
    assert by_match[("C", "D")]["m"] == "GOAL_RANGE_FT:2+"


def test_floor_is_applied_before_best_per_match() -> None:
    rows = [row("A", "B", "GOAL_RANGE_FT:1+", 0.85), row("A", "B", "GOAL_RANGE_FT:2+", 0.60)]
    picked = picker.pick_rows(rows, "group:Goals", "all", GROUPS, min_fair=1.50)
    assert len(picked) == 1
    assert picked[0]["m"] == "GOAL_RANGE_FT:2+"


def test_single_market_returns_every_fixture() -> None:
    rows = [row("A", "B", "BTTS:GG", 0.5), row("C", "D", "BTTS:GG", 0.6), row("C", "D", "GOAL_RANGE_FT:2+", 0.4)]
    picked = picker.pick_rows(rows, "market:BTTS:GG")
    assert len(picked) == 2
    assert {r["h"] for r in picked} == {"A", "C"}


def test_any_skips_ft_1_2_but_not_high_probability() -> None:
    rows = [
        row("A", "B", "RESULT:1", 0.90),
        row("A", "B", "GOAL_RANGE_FT:1+", 0.90),
        row("C", "D", "RESULT:2", 0.50),
        row("C", "D", "BTTS:GG", 0.55),
    ]
    picked = picker.pick_rows(rows, "any", "all", GROUPS, min_fair=0.0)
    by_match = {(r["h"], r["a"]): r for r in picked}
    assert by_match[("A", "B")]["m"] == "GOAL_RANGE_FT:1+"
    assert by_match[("C", "D")]["m"] == "BTTS:GG"


def test_any_floor_hides_low_fair() -> None:
    rows = [row("A", "B", "GOAL_RANGE_FT:1+", 0.90), row("A", "B", "BTTS:GG", 0.55)]
    picked = picker.pick_rows(rows, "any", "all", GROUPS, min_fair=1.50)
    assert [r["m"] for r in picked] == ["BTTS:GG"]


def test_below_floor_count_for_single_market() -> None:
    rows = [row("A", "B", "BTTS:GG", 0.90), row("C", "D", "BTTS:GG", 0.50)]
    assert picker.below_floor_count(rows, "market:BTTS:GG", "all", 1.50) == 1


def test_picker_calibration_is_walk_forward() -> None:
    import inspect

    from pipeline.model import picker_backtest

    data = json.loads((Path(__file__).resolve().parents[1] / "web" / "public" / "data" / "picker.json").read_text())
    assert data["season_factors"]["2019-20"] == {}  # no earlier season to fit on
    assert "if earlier >= target" in inspect.getsource(picker_backtest)


def test_top_n_cut() -> None:
    rows = [row("A", "B", "BTTS:GG", 0.50 + index * 0.01) for index in range(12)]
    assert len(picker.top_n(rows, 10)) == 10


def test_match_best_returns_ten_highest_for_that_match() -> None:
    rows = [row("A", "B", f"M{index}", 0.50 + index * 0.01) for index in range(12)]
    rows.append(row("C", "D", "BTTS:GG", 0.90))
    best = picker.match_best(rows, "A", "B", min_fair=0.0, n=10)
    assert len(best) == 10
    assert all(item["h"] == "A" and item["a"] == "B" for item in best)
    assert best[0]["pc"] > best[-1]["pc"]


def test_ticket_status_logic() -> None:
    assert picker.ticket_status(["landed", "lost"]) == "lost"
    assert picker.ticket_status(["landed", "pending"]) == "pending"
    assert picker.ticket_status(["landed", "void"]) == "landed"


def test_picker_has_past_round_tickets_from_round_files() -> None:
    source = (Path(__file__).resolve().parents[1] / "web" / "components" / "Picker.tsx").read_text(encoding="utf-8")
    assert "Suggested tickets — past rounds" in source
    assert "/data/rounds/index.json" in source


def test_no_empty_list_when_fixtures_exist() -> None:
    rows = [row("A", "B", "BTTS:GG", 0.5)]
    assert picker.pick_rows(rows, "group:BTTS", "all", GROUPS)


def test_sort_orders() -> None:
    rows = [row("A", "B", "BTTS:GG", 0.5, k="18:00"), row("C", "D", "BTTS:GG", 0.7, k="12:00")]
    assert picker.sort_rows(rows, "pc", "desc")[0]["h"] == "C"
    assert picker.sort_rows(rows, "kickoff", "asc")[0]["k"] == "12:00"
    assert picker.sort_rows(rows, "fair", "asc")[0]["h"] == "C"


def test_ticket_maths_and_bonus() -> None:
    legs = [
        {"pc": 0.5, "odds": 2.2, "h": "A", "a": "B"},
        {"pc": 0.4, "odds": 3.0, "h": "C", "a": "D"},
    ]
    assert picker.combined_probability(legs) == pytest.approx(0.2)
    assert picker.combined_fair(legs) == pytest.approx(5.0)
    assert picker.combined_mozzart(legs) == pytest.approx(6.6)
    assert picker.ticket_vs_fair(legs, 10) == pytest.approx((6.6 * 1.1) / 5.0 - 1)
    assert picker.payout(10, legs, 10) == pytest.approx(72.6)


def test_incomplete_mozzart_and_same_match() -> None:
    legs = [{"pc": 0.5, "odds": 2.0, "h": "A", "a": "B"}, {"pc": 0.5, "odds": None, "h": "A", "a": "B"}]
    assert picker.combined_mozzart(legs) is None
    assert picker.same_match_warning(legs) is True


def test_companion_files_match_the_published_model_fields() -> None:
    root = Path(__file__).resolve().parents[1]
    model_fields = ("p", "lr", "ln", "hr", "hn", "ar", "an", "st", "ht", "ft")
    for iso in ("2026-11-21", "2026-11-22"):
        companion = ranking.load(root / "picks" / f"{iso}.full.json")
        published = ranking.load(root / "picks" / f"{iso}.json")
        pub = {(r["d"], r["h"], r["a"], r["m"]): r for r in published["rows"]}
        shared = 0
        for row in companion["rows"]:
            target = pub.get((row["d"], row["h"], row["a"], row["m"]))
            if target is None:
                continue
            shared += 1
            assert all(row.get(field) == target.get(field) for field in model_fields)
        assert shared == len(published["rows"])


def test_combo_backtest_uses_only_earlier_matches() -> None:
    import inspect

    from pipeline.model import combo_backtest

    source = inspect.getsource(combo_backtest)
    assert "arrays.dates < day" in source
    assert "arrays.dates <= day" not in source


def test_ticket_storage_never_calls_the_network() -> None:
    source = (Path(__file__).resolve().parents[1] / "web" / "lib" / "ticket.ts").read_text(encoding="utf-8")
    assert "localStorage" in source
    assert "fetch(" not in source
    assert "XMLHttpRequest" not in source
