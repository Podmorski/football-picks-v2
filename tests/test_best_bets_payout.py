"""Task 21 Phase 4: Best-bets payout defaults, fallbacks and price arithmetic."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import ranking, report

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def row(home: str, away: str, market: str, pc: float, status: str = "pending", p: float = 0.45) -> dict:
    return {
        "d": "E0", "h": home, "a": away, "m": market, "p": p, "pc": pc,
        "lr": 0.40, "ln": 5000, "hr": 0.50, "hn": 20, "ar": 0.45, "an": 20, "st": status,
    }


def test_any_bet_default_is_fair_120_plus_pc_58() -> None:
    source = read("web/components/VettedList.tsx")
    assert "isAny ? ANY_BET_MIN_FAIR.toFixed(2) : 'any'" in source
    assert "minOddsParam === '' ? defaultMinOdds : minOddsParam" in source
    assert "useParam('min', '')" in source
    vetted = read("web/lib/vetted.ts")
    assert "export const ANY_BET_MIN_FAIR = 1.20;" in vetted
    assert "export const BEST_BETS_MIN_PC = 0.58;" in vetted
    assert "item.candidate.fairOdds < ANY_BET_MIN_FAIR" in vetted
    assert "item.candidate.probability < BEST_BETS_MIN_PC" in vetted
    assert "export const DEFAULT_MIN_FAIR = 1.70;" in vetted


def test_group_and_single_market_keep_any_odds_default() -> None:
    source = read("web/components/VettedList.tsx")
    # The default is conditional on Any bet; group/market deliberately fall back to any odds.
    assert ": 'any';" in source
    assert "const minFair = minOdds === 'any' ? 0" in source
    for option in ('Any odds', 'Min fair odds 1.20', 'Min fair odds 1.40', 'Min fair odds 1.70', 'Min fair odds 2.00', 'Min fair odds 2.50'):
        assert option in source, option


def test_explicit_url_selections_survive() -> None:
    source = read("web/components/VettedList.tsx")
    # An explicit `?min=` (numeric or Any odds) is stored in minOddsParam and wins.
    assert "minOddsParam === '' ? defaultMinOdds : minOddsParam" in source
    assert "!MIN_FAIR_OPTIONS.includes(minOdds)" in source
    assert "Min fair odds {Number(minOdds).toFixed(2)}" in source


def test_fallbacks_are_outside_preferred_and_labeled() -> None:
    source = read("web/components/VettedList.tsx")
    assert ".filter((item) => !(item.candidate.probability >= BEST_BETS_MIN_PC && item.candidate.fairOdds >= minFair))" in source
    assert ".slice(0, 3)" in source
    assert "const payoutOnlyFailure = qualified.length === 0 && pcCandidates.length > 0;" in source
    assert "58%+ candidates below the selected payout floor" in source
    assert "Highest-probability candidates below 58%" in source
    assert "Outside the preferred contract. Shown for context only, not as passing selections." in source


def test_break_even_and_expected_return_arithmetic_and_unpriced_absence() -> None:
    vetted = read("web/lib/vetted.ts")
    assert "export function breakEvenChance(odds: number): number" in vetted
    assert "return odds > 0 ? 1 / odds : 0;" in vetted
    assert "export function expectedReturn(probability: number, odds: number): number" in vetted
    assert "return probability * odds - 1;" in vetted
    source = read("web/components/VettedList.tsx")
    assert "breakEvenChance(price.odds)" in source
    assert "expectedReturn(candidate.probability, price.odds)" in source
    # The arithmetic lives inside the priced branch; the unpriced branch has no EV claim.
    priced = source[source.index("{price ? ("):source.index(") : <p>{priceUnavailableText()}</p>}")]
    assert "Model chance" in priced and "expected return" in priced
    unpriced = source[source.index(") : <p>{priceUnavailableText()}</p>}"):]
    assert "break-even" not in unpriced.split("</div>", 1)[0]
    # Formula sanity: 60% at 2.00 breaks even at 50% and returns +20%.
    assert 1 / 2.0 == pytest.approx(0.5)
    assert 0.60 * 2.0 - 1 == pytest.approx(0.20)


def test_no_value_badge_or_positive_ev_gate() -> None:
    source = read("web/components/VettedList.tsx")
    for forbidden in ('<Badge variant="value">Value', "Value legs only", "only if", "edge >= 0", "positive expected"):
        assert forbidden not in source, forbidden
    assert "Arithmetic at the offered price only; no positive-edge claim." in source


def test_dropdown_counts_follow_displayed_preferred_rows() -> None:
    source = read("web/components/VettedList.tsx")
    assert "for (const item of qualified)" in source
    assert "counts.groups.get(group)?.size" in source
    assert "counts.markets.get(market.id)?.size" in source
    assert "Counts follow exactly the same filters." in source


def test_report_record_reconciles_under_default_payout_floor() -> None:
    payload = json.loads((ROOT / "web" / "public" / "data" / "best-bets-record.json").read_text(encoding="utf-8"))
    assert payload["min_pc"] == 0.58 and payload["min_fair"] == 1.20
    assert payload["rounds"]
    for item in [*payload["rounds"], payload["cumulative"]]:
        assert item["passing"] == item["landed"] + item["lost"] + item["void"] + item["pending"]
        assert item["settled"] == item["landed"] + item["lost"]


def test_committed_rounds_reproduce_the_record_selection() -> None:
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
