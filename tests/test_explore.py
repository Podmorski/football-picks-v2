"""/explore keeps the M4/M5 picker (Mozzart labels removed from the main list)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pipeline import picker, ranking, vetting
from pipeline.markets import MARKET_BY_ID, MARKETS

ROOT = Path(__file__).resolve().parents[1]
PICKER_HASH = "efcd2e483c765082ba5afc3fb09b89beba31d79bdbfbd63cb2541cedc8bbd7c4"
EXPLORE_HASH = "52667740f4cb0b427adf47751a8f88fc1571fb7d52aefe28cdc2bdf7939dd487"


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
    """Legacy /rounds tally: pc >= 58%, fair >= 1.20, best per match."""
    full = ROOT / "picks" / f"{iso}.full.json"
    compact = ROOT / "picks" / f"{iso}.json"
    document = ranking.load(full if full.exists() else compact)
    best: dict[tuple[str, str, str], tuple[float, str]] = {}
    for row in document["rows"]:
        if row["m"].startswith("CORRECT_SCORE:"):
            continue
        pc = float(row.get("pc", row["p"]))
        fair = 1 / max(pc, 1e-4)
        if pc < 0.58 or fair < 1.20:
            continue
        key = (row["d"], row["h"], row["a"])
        if key not in best or pc > best[key][0]:
            best[key] = (pc, row["st"])
    settled = [status for _, status in best.values() if status in ("landed", "lost")]
    return len(best), len(settled), sum(1 for status in settled if status == "landed")


def test_rounds_tally_matches_the_best_bets_default_rows() -> None:
    # 21 Nov results have now arrived: 120 of 122 settled, 97 landed.
    assert default_vetted_tally("2026-11-21") == (122, 120, 97)
    # The 14 Nov example is settled under the same rule: 36 of 46 landed.
    assert default_vetted_tally("2026-11-14") == (48, 46, 36)


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
    assert "ANY_RULE" in shared
    assert "selectPassing" in shared


def test_mozzart_labels_are_off_the_main_lists() -> None:
    vetted = (ROOT / "web" / "components" / "VettedList.tsx").read_text(encoding="utf-8")
    picker_source = (ROOT / "web" / "components" / "Picker.tsx").read_text(encoding="utf-8")
    assert "Only where Mozzart pays at least fair" not in vetted
    assert "Mozzart ≥ fair" not in vetted
    assert "Only where Mozzart pays more than fair" not in picker_source
    assert "Mozzart vs fair" not in picker_source


TYPE_GROUPS = ("Combos", "HT/FT", "Goals", "BTTS", "Half-time", "Team goals", "Result & double chance")


def _type_passes(row: dict) -> bool:
    pc = row.get("pc", row["p"])
    fair = 1 / max(pc, 1e-4)
    candidate = vetting.Candidate(
        probability=pc, model_probability=row["p"], league_rate=row["lr"], league_n=row["ln"],
        home_rate=row["hr"], home_n=row["hn"], away_rate=row["ar"], away_n=row["an"],
        fair_odds=fair,
    )
    return vetting.type_evaluate(candidate)[0]


def type_rows(iso: str = "2026-11-21") -> tuple[dict, list[dict]]:
    document = ranking.load(ROOT / "picks" / f"{iso}.full.json")
    rows = [
        row for row in document["rows"]
        if not row["m"].startswith("CORRECT_SCORE:") and _type_passes(row)
    ]
    return document, rows


def test_htft_rows_pass_type_rule() -> None:
    _, rows = type_rows()
    assert any(MARKET_BY_ID[row["m"]].group == "HT/FT" for row in rows)


def test_type_group_counts_match_one_per_match_rows() -> None:
    _, rows = type_rows()
    counts = {
        group: len({(row["d"], row["h"], row["a"]) for row in rows if MARKET_BY_ID[row["m"]].group == group})
        for group in TYPE_GROUPS
    }
    assert counts == {
        "Combos": 51, "HT/FT": 55, "Goals": 20, "BTTS": 14,
        "Half-time": 53, "Team goals": 64, "Result & double chance": 51,
    }
    # A group list shows one row per match (highest probability), so its length
    # equals the dropdown count.
    for group in TYPE_GROUPS:
        selected: dict[tuple[str, str, str], float] = {}
        for row in rows:
            if MARKET_BY_ID[row["m"]].group != group:
                continue
            key = (row["d"], row["h"], row["a"])
            probability = row.get("pc", row["p"])
            if key not in selected or probability > selected[key]:
                selected[key] = probability
        assert len(selected) == counts[group]


def test_zero_count_group_has_closest_candidates() -> None:
    document, _ = type_rows()
    rows = [
        row for row in document["rows"]
        if row["d"] == "E0" and MARKET_BY_ID[row["m"]].group == "BTTS"
        and not row["m"].startswith("CORRECT_SCORE:")
    ]
    assert rows
    failing = []
    for row in rows:
        pc = row.get("pc", row["p"])
        candidate = vetting.Candidate(
            probability=pc, model_probability=row["p"], league_rate=row["lr"], league_n=row["ln"],
            home_rate=row["hr"], home_n=row["hn"], away_rate=row["ar"], away_n=row["an"],
            fair_odds=1 / max(pc, 1e-4),
        )
        passed, checks = vetting.type_evaluate(candidate)
        failed = [check for check in checks if not check["passed"]]
        if not passed and failed:
            failing.append(((row["h"], row["a"]), failed))
    # The empty state can name the failed check and value for at least 3 matches.
    assert len({key for key, _ in failing}) >= 3


def test_correct_score_is_hidden_from_the_picker_ui() -> None:
    vetted = (ROOT / "web" / "components" / "VettedList.tsx").read_text(encoding="utf-8")
    picker_source = (ROOT / "web" / "components" / "Picker.tsx").read_text(encoding="utf-8")
    for source in (vetted, picker_source):
        assert "'Correct score'" not in source
        assert "isHiddenMarketId" in source
    shared = (ROOT / "web" / "lib" / "vetted.ts").read_text(encoding="utf-8")
    assert "CORRECT_SCORE:" in shared
    markets = json.loads((ROOT / "web" / "public" / "data" / "markets.json").read_text(encoding="utf-8"))
    assert any(market["group"] == "Correct score" for market in markets["markets"])


def test_best_bets_uses_the_daily_best_contract_not_legacy_rules() -> None:
    vetted = (ROOT / "web" / "components" / "VettedList.tsx").read_text(encoding="utf-8")
    assert "selectDaily" in vetted
    assert "selectGroupRows" in vetted
    assert "selectMarketRows" in vetted
    assert "BEST_BETS_MIN_PC" not in vetted
    assert "selectType" not in vetted
    assert "selectPassing" not in vetted
    assert "typeCounts" not in vetted
    assert "counts.groups.get(group)?.size" in vetted
    assert "counts.markets.get(market.id)?.size" in vetted
    daily = (ROOT / "web" / "lib" / "dailyBest.ts").read_text(encoding="utf-8")
    assert "export const DAILY_LIMIT = 12;" in daily
    assert "export function selectDaily" in daily
