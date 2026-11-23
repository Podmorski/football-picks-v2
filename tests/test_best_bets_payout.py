"""Daily-best band defaults, legacy URL mapping and price arithmetic (Phase 1).

The old unified 58% cohort is now explicitly a frozen legacy research record.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import ranking, report

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_daily_best_is_the_default_with_a_visible_band() -> None:
    daily = read("web/lib/dailyBest.ts")
    assert "export const DAILY_LIMIT = 12;" in daily
    assert "export const DAILY_MIN_ODDS = 1.20;" in daily
    assert "export const DEFAULT_BAND = '1.70-2.30';" in daily
    for label in ("1.70–2.30 — default", "1.20–1.69", "2.31–4.00", "4.01+", "All 1.20+"):
        assert label in daily, label
    source = read("web/components/VettedList.tsx")
    assert "<option value=\"any\">Daily best</option>" in source
    assert "BAND_OPTIONS.map" in source
    assert "aria-label=\"Daily-best actual-odds band\"" in source


def test_legacy_min_links_map_to_an_actual_odds_floor() -> None:
    daily = read("web/lib/dailyBest.ts")
    assert "if (odds <= DAILY_MIN_ODDS) return 'all';" in daily
    assert "return `${formatNumber(odds)}+`;" in daily
    source = read("web/components/VettedList.tsx")
    assert "useParam('band', '')" in source
    assert "useParam('min', '')" in source
    assert "bandParam || legacyMinToBand(minParam) || DEFAULT_BAND" in source
    assert "dropParams(['min'])" in source


def test_no_probability_vetting_or_ev_gate_remains_in_best_bets() -> None:
    source = read("web/components/VettedList.tsx")
    for forbidden in ("BEST_BETS_MIN_PC", "ANY_RULE", "TYPE_RULE", "selectPassing", "selectType", "minFair", "0.58"):
        assert forbidden not in source, forbidden
    assert "No actual price · no actual-EV claim" in source
    assert "Arithmetic at the offered price only; no positive-edge claim." in source


def test_break_even_and_expected_return_arithmetic_and_unpriced_absence() -> None:
    daily = read("web/lib/dailyBest.ts")
    assert "export function expectedReturnOf(probability: number, odds: number): number" in daily
    assert "return probability * odds - 1;" in daily
    source = read("web/components/VettedList.tsx")
    assert "breakEvenChance(item.odds)" in source
    assert "expectedReturn(candidate.probability, item.odds)" in source
    priced = source[source.index("{item.odds !== null ? ("):source.index("No actual price · no actual-EV claim")]
    assert "break-even" in priced and "model return" in priced
    unpriced = source[source.index("<span>No actual price · no actual-EV claim</span>"):]
    assert "break-even" not in unpriced.split("</span>", 1)[0]
    assert 1 / 2.0 == pytest.approx(0.5)
    assert 0.60 * 2.0 - 1 == pytest.approx(0.20)


def test_refinements_default_to_all_and_expose_hidden_counts() -> None:
    daily = read("web/lib/dailyBest.ts")
    assert "{ token: 'all', label: 'No refinement (all)' }" in daily
    assert "export function applyRefinement" in daily
    source = read("web/components/VettedList.tsx")
    assert "aria-label=\"Optional refinement\"" in source
    assert "The optional refinement hides" in source
    assert "Show all" in source


def test_report_labels_the_old_58_cohort_as_legacy() -> None:
    payload = json.loads((ROOT / "web" / "public" / "data" / "best-bets-record.json").read_text(encoding="utf-8"))
    assert payload["min_pc"] == 0.58 and payload["min_fair"] == 1.20
    source = " ".join(read("web/app/report/page.tsx").split())
    assert "Best bets results · legacy 58% cohort" in source
    assert "not the current Daily-best list" in source
    assert "unified 58% selection" not in source


def test_committed_rounds_still_reproduce_the_frozen_legacy_record() -> None:
    payload = json.loads((ROOT / "web" / "public" / "data" / "best-bets-record.json").read_text(encoding="utf-8"))
    for item in payload["rounds"]:
        full = ROOT / "picks" / f"{item['date']}.full.json"
        compact = ROOT / "picks" / f"{item['date']}.json"
        document = ranking.load(full if full.exists() else compact)
        stats = report.summarise(document["rows"])
        assert stats["passing"] == item["passing"], item["date"]
        assert stats["landed"] == item["landed"], item["date"]
        assert stats["lost"] == item["lost"], item["date"]
        assert stats["void"] == item["void"], item["date"]
