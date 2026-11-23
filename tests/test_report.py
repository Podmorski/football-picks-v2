"""Best bets record for /report."""
from __future__ import annotations

import json
from pathlib import Path

from pipeline import report

ROOT = Path(__file__).resolve().parents[1]


def row(home: str, away: str, market: str, pc: float, status: str = "pending", p: float = 0.45) -> dict:
    return {
        "d": "E0", "h": home, "a": away, "m": market, "p": p, "pc": pc,
        "lr": 0.40, "ln": 5000, "hr": 0.50, "hn": 20, "ar": 0.45, "an": 20, "st": status,
    }


def test_correct_score_and_probability_below_58_are_excluded() -> None:
    rows = [
        row("A", "B", "BTTS:GG", 0.50),
        row("A", "B", "CORRECT_SCORE:1:0", 0.90),
        row("C", "D", "BTTS:GG", 0.80),
    ]
    picks = report.passing_picks(rows)
    assert [(item["h"], item["a"], item["m"]) for item in picks] == [("C", "D", "BTTS:GG")]


def test_any_bet_default_excludes_fair_odds_below_120() -> None:
    rows = [
        row("A", "B", "GOAL_RANGE_FT:1+", 0.95),
        row("C", "D", "GOAL_RANGE_FT:1+", 0.84),
        row("E", "F", "GOAL_RANGE_FT:1+", 0.80),
        row("G", "H", "GOAL_RANGE_FT:1+", 0.58),
    ]
    picks = report.passing_picks(rows)
    assert [(item["h"], item["a"]) for item in picks] == [("E", "F"), ("G", "H")]
    assert report.MIN_FAIR == 1.20


def test_summary_counts_pending_and_is_inclusive_at_58() -> None:
    rows = [
        row("A", "B", "BTTS:GG", 0.58, "landed", p=0.45),
        row("C", "D", "BTTS:GG", 0.60, "lost", p=0.45),
        row("E", "F", "BTTS:GG", 0.59, "pending", p=0.45),
    ]
    stats = report.summarise(rows)
    assert stats["passing"] == 3
    assert stats["settled"] == 2
    assert stats["landed"] == 1
    assert stats["pending"] == 1
    assert stats["lost"] == 1
    assert stats["void"] == 0
    assert stats["passing"] == stats["landed"] + stats["lost"] + stats["void"] + stats["pending"]
    assert stats["expected"] == 1.18
    assert "strong" not in stats and "possible" not in stats


def test_one_pick_per_match_is_the_highest_probability() -> None:
    rows = [row("A", "B", "BTTS:GG", 0.58), row("A", "B", "RESULT:X", 0.60, p=0.45)]
    picks = report.passing_picks(rows)
    assert len(picks) == 1
    assert picks[0]["m"] == "RESULT:X"


def test_report_page_has_the_extended_sections() -> None:
    source = (ROOT / "web" / "app" / "report" / "page.tsx").read_text(encoding="utf-8")
    for needle in (
        "Best bets results", "Record at Mozzart prices", "Price status", "Last updated",
        "readBestBetsRecord", "readMozzartVettedRecord", "readMozzartStatus",
    ):
        assert needle in source


def test_top_nav_has_best_bets_explore_report() -> None:
    header = (ROOT / "web" / "components" / "SiteHeader.tsx").read_text(encoding="utf-8")
    assert "label: 'Best bets'" in header
    assert "label: 'Explore'" in header
    assert "label: 'Report'" in header


def test_committed_best_bets_record_structure() -> None:
    payload = json.loads((ROOT / "web" / "public" / "data" / "best-bets-record.json").read_text(encoding="utf-8"))
    assert payload["min_pc"] == 0.58
    assert payload["min_fair"] == 1.20
    assert payload["rounds"]
    cumulative = payload["cumulative"]
    assert cumulative["settled"] >= 0
    assert cumulative["passing"] == cumulative["landed"] + cumulative["lost"] + cumulative["void"] + cumulative["pending"]
    assert "strong" not in cumulative and "possible" not in cumulative


def test_14_nov_void_and_example_reporting_are_exact() -> None:
    payload = json.loads((ROOT / "web" / "public" / "data" / "best-bets-record.json").read_text(encoding="utf-8"))
    row = next(item for item in payload["rounds"] if item["date"] == "2026-11-14")
    assert (row["passing"], row["settled"], row["landed"], row["lost"], row["void"], row["pending"]) == (48, 46, 36, 10, 2, 0)
    source = (ROOT / "web" / "app" / "report" / "page.tsx").read_text(encoding="utf-8")
    normalized = " ".join(source.split())
    assert "Retrospective example generated after the fixture; not forward performance" in normalized
    assert "36 landed, 10 lost and 2 void" in normalized
    assert "none is GOAL_RANGE_FT:1+" in normalized
    assert "median selected fair odds are approximately 1.218" in normalized
    assert "not evidence of positive expected value or realised bookmaker profit" in normalized
