"""/explore keeps the M4/M5 picker (Mozzart labels removed from the main list)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pipeline import picker, ranking, vetting
from pipeline.markets import MARKETS

ROOT = Path(__file__).resolve().parents[1]
PICKER_HASH = "37ebd7407794e18f0c31510f8f3ea1086cca1973c218050cc64b76119b3f03e8"
EXPLORE_HASH = "cb4454bd54a9de9df2767b1744d623328b09ef94298f208d524f4024e3ee360b"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_explore_renders_the_picker() -> None:
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


def default_vetted_tally(iso: str) -> tuple[int, int, int]:
    """Mirror the Best bets default filters (DEFAULT_RULE, fair >= 1.70, best per match)."""
    full = ROOT / "picks" / f"{iso}.full.json"
    compact = ROOT / "picks" / f"{iso}.json"
    document = ranking.load(full if full.exists() else compact)
    best: dict[tuple[str, str], tuple[float, str]] = {}
    for row in document["rows"]:
        pc = row.get("pc", row["p"])
        fair = 1 / max(pc, 1e-4)
        candidate = vetting.Candidate(
            probability=pc, model_probability=row["p"], league_rate=row["lr"], league_n=row["ln"],
            home_rate=row["hr"], home_n=row["hn"], away_rate=row["ar"], away_n=row["an"],
            fair_odds=fair, counts_probability=row["lr"],
        )
        passed, _ = vetting.evaluate(candidate, vetting.DEFAULT_RULE)
        if not passed or fair < 1.70:
            continue
        key = (row["h"], row["a"])
        if key not in best or pc > best[key][0]:
            best[key] = (pc, row["st"])
    settled = [status for _, status in best.values() if status in ("landed", "lost")]
    return len(best), len(settled), sum(1 for status in settled if status == "landed")


def test_rounds_tally_matches_the_best_bets_default_rows() -> None:
    # 21 Nov has no results yet: every row is pending, so no landed/lost tally.
    assert default_vetted_tally("2026-11-21") == (54, 0, 0)
    # The 14 Nov example is settled under the same rule: 8 of 21 landed.
    assert default_vetted_tally("2026-11-14") == (21, 21, 8)


def test_rounds_index_has_one_entry_per_date() -> None:
    index = json.loads((ROOT / "web" / "public" / "data" / "rounds" / "index.json").read_text(encoding="utf-8"))
    dates = [row["date"] for row in index["rounds"]]
    assert len(dates) == len(set(dates))
    assert set(dates) >= {"2026-11-14", "2026-11-21", "2026-11-22"}


def test_rounds_tally_shares_the_page_selection() -> None:
    source = (ROOT / "web" / "app" / "rounds" / "page.tsx").read_text(encoding="utf-8")
    assert "roundTally" in source
    assert "readRankRoundComplete" in source
    assert "defaultPicks" not in source
    assert "Results pending" in source
    shared = (ROOT / "web" / "lib" / "vetted.ts").read_text(encoding="utf-8")
    assert "DEFAULT_RULE" in shared
    assert "selectPassing" in shared


def test_mozzart_labels_are_off_the_main_lists() -> None:
    vetted = (ROOT / "web" / "components" / "VettedList.tsx").read_text(encoding="utf-8")
    picker_source = (ROOT / "web" / "components" / "Picker.tsx").read_text(encoding="utf-8")
    assert "Only where Mozzart pays at least fair" not in vetted
    assert "Mozzart ≥ fair" not in vetted
    assert "Only where Mozzart pays more than fair" not in picker_source
    assert "Mozzart vs fair" not in picker_source
