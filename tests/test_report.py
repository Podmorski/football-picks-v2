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
        row("C", "D", "BTTS:GG", 0.90),
    ]
    picks = report.passing_picks(rows)
    assert [(item["h"], item["a"], item["m"]) for item in picks] == [("C", "D", "BTTS:GG")]


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
    assert payload["rounds"]
    cumulative = payload["cumulative"]
    assert cumulative["settled"] >= 0
    assert "strong" not in cumulative and "possible" not in cumulative
