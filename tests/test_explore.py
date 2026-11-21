"""/explore restores the pre-M6 M4/M5 picker unchanged."""
from __future__ import annotations

import hashlib
from pathlib import Path

from pipeline import picker, ranking
from pipeline.markets import MARKETS

ROOT = Path(__file__).resolve().parents[1]
PICKER_HASH = "e291b3c6358237901173080bbb65aed81874030179569971bf13a0d4ef1e4da2"
EXPLORE_HASH = "cb4454bd54a9de9df2767b1744d623328b09ef94298f208d524f4024e3ee360b"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_explore_renders_the_pre_m6_picker_unchanged() -> None:
    page = (ROOT / "web" / "app" / "explore" / "page.tsx").read_text(encoding="utf-8")
    assert "import Picker from '@/components/Picker'" in page
    assert "<Picker" in page
    assert sha(ROOT / "web" / "app" / "explore" / "page.tsx") == EXPLORE_HASH
    assert sha(ROOT / "web" / "components" / "Picker.tsx") == PICKER_HASH


def test_picker_keeps_filters_sorting_show_all_floor_match_view_and_tickets() -> None:
    source = (ROOT / "web" / "components" / "Picker.tsx").read_text(encoding="utf-8")
    for needle in ("sortRows", "Show all", "min === 'any'", "matchParam", "Suggested tickets — past rounds", "slice(0, 10)"):
        assert needle in source


def test_explore_rows_match_the_picker_on_sat_21_nov() -> None:
    document = ranking.load(ROOT / "picks" / "2026-11-21.full.json")
    groups = {market.id: market.group for market in MARKETS}
    pool = picker.pick_rows(document["rows"], "group:Combos", "all", groups, min_fair=1.50)
    top = picker.sort_rows(pool, "pc", "desc")[:10]
    assert len(pool) == 122
    assert len(top) == 10
    assert top[0]["pc"] == max(item["pc"] for item in pool)


def test_top_navigation_has_best_bets_and_explore() -> None:
    header = (ROOT / "web" / "components" / "SiteHeader.tsx").read_text(encoding="utf-8")
    assert "label: 'Best bets'" in header
    assert "label: 'Explore'" in header
