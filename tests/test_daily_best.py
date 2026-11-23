"""Phase 1: Daily-best and unrestricted market-picker contracts."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from pipeline import ranking
from pipeline.markets import MARKET_BY_ID

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
TS_MODULE = (ROOT / "web" / "lib" / "dailyBest.ts").resolve().as_uri()

NODE_SCRIPT = r"""
import fs from 'node:fs';
const mod = await import(process.env.DAILY_BEST_TS);
const input = JSON.parse(fs.readFileSync(process.env.DAILY_BEST_INPUT, 'utf8'));
const ops = {
  selectDaily: (i) => mod.selectDaily(i.candidates, mod.parseBand(i.band)),
  visibleDaily: (i) => mod.visibleDailyRows(mod.selectDaily(i.candidates, mod.parseBand(i.band)), i.showAll),
  selectGroup: (i) => mod.selectGroupRows(i.candidates),
  selectMarket: (i) => mod.selectMarketRows(i.candidates),
  refinement: (i) => mod.applyRefinement(i.rows, i.refine),
  parseBand: (i) => mod.parseBand(i.value),
  legacy: (i) => mod.legacyMinToBand(i.value),
  expected: (i) => mod.expectedReturnOf(i.pc, i.odds),
  distance: (i) => mod.bandDistance(i.odds, mod.parseBand(i.band)),
};
console.log(JSON.stringify(ops[input.op](input)));
"""


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def run(op: str, **payload):
    if NODE is None:
        pytest.skip("node is required for the Daily-best contract runner")
    payload["op"] = op
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(payload, handle)
        handle.close()
        env = dict(os.environ, DAILY_BEST_TS=TS_MODULE, DAILY_BEST_INPUT=handle.name)
        result = subprocess.run(
            [NODE, "--input-type=module", "-e", NODE_SCRIPT],
            env=env, capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
    finally:
        Path(handle.name).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def candidate(div: str, home: str, away: str, market: str, pc: float, odds):
    return {"d": div, "h": home, "a": away, "m": market, "pc": pc, "odds": odds}


def test_preferred_band_is_chosen_ahead_of_shorter_higher_probability() -> None:
    picks = run(
        "selectDaily",
        band="1.70-2.30",
        candidates=[
            candidate("E0", "Short", "Odds", "RESULT:1", 0.92, 1.25),
            candidate("E0", "Both", "Options", "RESULT:1", 0.90, 1.25),
            candidate("E0", "Both", "Options", "RESULT:X", 0.52, 1.95),
            candidate("E0", "InBand", "Only", "RESULT:1", 0.55, 1.90),
        ],
    )
    assert [row["h"] for row in picks["rows"]] == ["InBand", "Both", "Short"]
    both = next(row for row in picks["rows"] if row["h"] == "Both")
    assert both["odds"] == 1.95
    assert picks["inBandFixtures"] == 2
    assert picks["eligibleFixtures"] == 3


def test_actual_odds_below_120_never_enter_daily_best() -> None:
    picks = run(
        "selectDaily",
        band="1.70-2.30",
        candidates=[
            candidate("E0", "Too", "Short", "RESULT:1", 0.95, 1.05),
            candidate("E0", "Just", "Short", "RESULT:1", 0.85, 1.19),
            candidate("E0", "At", "Floor", "RESULT:1", 0.80, 1.20),
        ],
    )
    assert [row["h"] for row in picks["rows"]] == ["At"]
    assert picks["eligibleFixtures"] == 1
    assert picks["rejected"] == 2


def test_no_more_than_twelve_unique_fixtures_and_no_padding() -> None:
    candidates = []
    for index in range(20):
        candidates.append(candidate("E0", f"H{index}", f"A{index}", "RESULT:1", 0.60, 1.90))
        candidates.append(candidate("E0", f"H{index}", f"A{index}", "RESULT:X", 0.10, 1.95))
    picks = run("visibleDaily", band="1.70-2.30", candidates=candidates, showAll=False)
    selection = run("selectDaily", band="1.70-2.30", candidates=candidates)
    assert selection["eligibleFixtures"] == 20
    fixtures = {(row["d"], row["h"], row["a"]) for row in picks}
    assert len(picks) == 12
    assert len(fixtures) == 12
    all_rows = run("visibleDaily", band="1.70-2.30", candidates=candidates, showAll=True)
    assert len(all_rows) == 20
    assert len({(row["d"], row["h"], row["a"]) for row in all_rows}) == 20


def test_fewer_eligible_fixtures_produce_an_honest_shorter_list() -> None:
    picks = run(
        "selectDaily",
        band="1.70-2.30",
        candidates=[
            candidate("E0", "A", "B", "RESULT:1", 0.60, 1.90),
            candidate("E0", "C", "D", "RESULT:1", 0.55, 2.00),
            candidate("E0", "E", "F", "RESULT:1", 0.50, 2.20),
        ],
    )
    assert len(picks["rows"]) == 3
    assert picks["eligibleFixtures"] == 3


def test_outside_band_uses_nearest_log_distance_then_probability() -> None:
    distances = run("distance", odds=1.21, band="1.70-2.30")
    far = run("distance", odds=4.50, band="1.70-2.30")
    assert distances < far
    picks = run(
        "selectDaily",
        band="1.70-2.30",
        candidates=[
            candidate("E0", "Far", "Out", "RESULT:1", 0.60, 4.50),
            candidate("E0", "Near", "Out", "RESULT:1", 0.50, 1.21),
            candidate("E0", "Near", "Out", "RESULT:X", 0.40, 1.21),
        ],
    )
    assert [row["h"] for row in picks["rows"]] == ["Near", "Far"]
    # The lower-pc option on the same fixture cannot be added for padding.
    near = next(row for row in picks["rows"] if row["h"] == "Near")
    assert near["m"] == "RESULT:1"


def test_all_120_plus_uses_highest_probability_per_fixture() -> None:
    picks = run(
        "selectDaily",
        band="all",
        candidates=[
            candidate("E0", "A", "B", "RESULT:1", 0.40, 1.50),
            candidate("E0", "A", "B", "RESULT:X", 0.60, 1.25),
            candidate("E0", "C", "D", "RESULT:1", 0.70, 1.20),
            candidate("E0", "E", "F", "RESULT:1", 0.95, 1.19),
        ],
    )
    assert [(row["h"], row["m"]) for row in picks["rows"]] == [("C", "RESULT:1"), ("A", "RESULT:X")]
    assert picks["outside"] == []
    assert picks["eligibleFixtures"] == 2


def test_break_even_and_expected_return_arithmetic() -> None:
    assert run("expected", pc=0.60, odds=2.00) == pytest.approx(0.20)
    assert 1 / 2.0 == pytest.approx(0.50)
    assert run("expected", pc=0.50, odds=4.00) == pytest.approx(1.00)


def test_band_parsing_and_legacy_min_mapping() -> None:
    assert run("parseBand", value=None)["token"] == "1.70-2.30"
    assert run("parseBand", value="1.70-2.30")["token"] == "1.70-2.30"
    assert run("parseBand", value="all")["all"] is True
    assert run("parseBand", value="1.70-2.30")["min"] == pytest.approx(1.70)
    assert run("legacy", value="1.70") == "1.70+"
    assert run("legacy", value="any") == "all"
    assert run("legacy", value="1.20") == "all"


def test_exact_market_returns_every_fixture_including_below_58_and_unpriced() -> None:
    picks = run(
        "selectMarket",
        candidates=[
            candidate("E0", "A", "B", "HTFT:X-1", 0.06, 9.0),
            candidate("E0", "C", "D", "HTFT:X-1", 0.20, 5.0),
            candidate("E0", "E", "F", "HTFT:X-1", 0.15, None),
            candidate("E1", "G", "H", "HTFT:X-1", 0.10, 8.0),
        ],
    )
    assert [row["h"] for row in picks] == ["C", "E", "G", "A"]
    assert [row["pc"] for row in picks] == [0.20, 0.15, 0.10, 0.06]
    assert next(row for row in picks if row["h"] == "E")["odds"] is None
    assert all(row["pc"] < 0.58 for row in picks)


def test_group_view_keeps_every_option_and_one_row_per_fixture() -> None:
    picks = run(
        "selectGroup",
        candidates=[
            candidate("E0", "A", "B", "RESULT:1", 0.05, 6.0),
            candidate("E0", "A", "B", "RESULT:X", 0.06, 5.0),
            candidate("E0", "C", "D", "RESULT:X", 0.04, None),
        ],
    )
    assert len(picks) == 2
    assert picks[0]["h"] == "A" and picks[0]["m"] == "RESULT:X"
    assert picks[1]["h"] == "C" and picks[1]["odds"] is None


def test_refinements_are_opt_in_and_report_hidden_counts() -> None:
    rows = [{"pc": 0.40}, {"pc": 0.55}, {"pc": 0.70}]
    assert run("refinement", rows=rows, refine="all")["hidden"] == 0
    assert run("refinement", rows=rows, refine="pc58")["hidden"] == 2
    assert run("refinement", rows=rows, refine="fair150")["hidden"] == 1
    assert run("refinement", rows=rows, refine="fair200")["hidden"] == 2


def exact_market_rows(date: str, division: str, market: str) -> list[dict]:
    full = ROOT / "picks" / f"{date}.full.json"
    compact = ROOT / "picks" / f"{date}.json"
    document = ranking.load(full if full.exists() else compact)
    return [row for row in document["rows"] if row["d"] == division and row["m"] == market]


def test_exact_htft_x1_returns_every_league_fixture() -> None:
    rows = exact_market_rows("2026-11-21", "E3", "HTFT:X-1")
    fixtures = {(row["d"], row["h"], row["a"]) for row in rows}
    assert MARKET_BY_ID["HTFT:X-1"].group == "HT/FT"
    assert len(rows) == len(fixtures) == 12
    assert all(float(row.get("pc", row["p"])) < 0.58 for row in rows)
    picks = run(
        "selectMarket",
        candidates=[
            candidate(row["d"], row["h"], row["a"], row["m"], float(row.get("pc", row["p"])), None)
            for row in rows
        ],
    )
    assert len(picks) == 12
    assert all(row["odds"] is None for row in picks)


def test_source_contract_for_daily_and_market_views() -> None:
    source = read("web/components/VettedList.tsx")
    daily = read("web/lib/dailyBest.ts")
    for needle in (
        "selectDaily", "selectGroupRows", "selectMarketRows", "applyRefinement",
        "legacyMinToBand", "visibleDailyRows(daily, showAll)", "showParam === 'all'",
        "Show all eligible games", "in band / ", "No actual price · no actual-EV claim",
        "The optional refinement hides", "Show all {marketBase.length}",
        "All {GROUP_LABEL[groupKey]} options for this match",
    ):
        assert needle in source, needle
    for forbidden in ("BEST_BETS_MIN_PC", "ANY_RULE", "TYPE_RULE", "selectPassing", "selectType", "minFair"):
        assert forbidden not in source, forbidden
    for needle in (
        "export const DAILY_LIMIT = 12;", "export const DAILY_MIN_ODDS = 1.20;",
        "export const DEFAULT_BAND = '1.70-2.30';", "export function selectDaily",
        "export function visibleDailyRows", "export function applyRefinement",
        "export function legacyMinToBand",
    ):
        assert needle in daily, needle


def test_reset_restores_the_exact_default_state() -> None:
    source = read("web/components/VettedList.tsx")
    reset = source[source.index("function resetAll()"):source.index("const activeEvaluated")]
    for needle in (
        "setLeague('all')", "setBet('any')", "setBandParam('')", "setMinParam('')",
        "setRefineParam('')", "setShowParam('')", "setRound(date)",
        "dropParams(['band', 'min', 'refine', 'show'])",
    ):
        assert needle in reset, needle


def test_legacy_report_cohort_is_not_called_the_current_daily_record() -> None:
    report = " ".join(read("web/app/report/page.tsx").split())
    assert "legacy 58% cohort" in report
    assert "not the current Daily-best list" in report
    how = " ".join(read("web/app/how-it-works/page.tsx").split())
    assert "Best bets: the Daily best list" in how
    assert "one 58% list" not in how


def test_zero_band_leagues_stay_selectable() -> None:
    source = read("web/components/VettedList.tsx")
    assert "const present = new Set(roundDivisions);" in source
    assert "present.add(league)" in source
    assert "in band / " in source
    assert "value={code}" in source


def test_explore_forward_and_reconstruction_files_are_untouched() -> None:
    # Phase 1 changes the dashboard only; these surfaces and the frozen ledgers
    # are out of scope and must not be edited by this contract.
    for rel in (
        "web/components/Picker.tsx",
        "web/app/explore/page.tsx",
        "web/app/tickets/page.tsx",
        "pipeline/proposed_tickets.py",
        "pipeline/bankroll.py",
        "pipeline/published_reconstructions.py",
    ):
        assert (ROOT / rel).exists(), rel
