"""Task 12/13 UX contracts: states, active-round identity, Ranked/Strict and labels."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_best_bets_distinguishes_loading_failure_and_unified_empty_state() -> None:
    source = read("web/components/VettedList.tsx")
    for needle in (
        "roundState", "marketsState", "pricesState",
        "Loading the round and market data…",
        "Could not load the round data",
        "Could not load the market data",
        "Mozzart prices could not be loaded.",
        "Mozzart prices are not embedded in this build.",
        "No Mozzart snapshot for this round.",
        "Daily best needs frozen Mozzart prices. This build is unpriced.",
        "No Mozzart price for this league in this round.",
        "selectDaily", "selectGroupRows", "selectMarketRows",
        "activeMeta", "activeKind", "roundMeta",
        "Show all eligible games", "Show all",
        "All {GROUP_LABEL[groupKey]} options for this match",
    ):
        assert needle in source, needle
    for removed in (
        "Ranked — all candidates", "Strict checks only", "Strong = probability",
        "<Badge variant=\"value\">Value", "Play only at odds",
        "BEST_BETS_MIN_PC", "No candidates meet the preferred settings",
        "Lower-probability alternatives",
    ):
        assert removed not in source, removed


def test_best_bets_group_and_single_market_selection() -> None:
    source = read("web/components/VettedList.tsx")
    assert "const displayed = useMemo" in source
    assert "selectGroupRows(scoped)" in source
    assert "selectMarketRows(scoped)" in source
    assert "const daily = useMemo(() => selectDaily(leagueScoped, band)" in source
    vetted = read("web/lib/dailyBest.ts")
    assert "export function selectGroupRows" in vetted
    assert "export function selectMarketRows" in vetted
    assert "export function selectDaily" in vetted


def test_daily_best_has_no_58_or_legacy_rule_gate() -> None:
    source = read("web/components/VettedList.tsx")
    assert "BEST_BETS_MIN_PC" not in source
    assert "!isStrict || option.passed" not in source
    assert "selectType(" not in source
    assert "selectPassing(" not in source
    daily = read("web/lib/dailyBest.ts")
    for forbidden in ("ANY_RULE", "TYPE_RULE", "vetting", "BEST_BETS_MIN_PC"):
        assert forbidden not in daily, forbidden


def test_match_details_expose_all_group_options() -> None:
    source = read("web/components/VettedList.tsx")
    assert "const matchOptions = groupKey" in source
    assert "option.d === row.d && option.h === row.h && option.a === row.a" in source
    assert "Highest model probability:" in source
    assert "All {GROUP_LABEL[groupKey]} options for this match" in source
    # Every group option is listed; there is no probability or price gate here.
    assert "option.candidate.probability >= BEST_BETS_MIN_PC" not in source


def test_band_refinements_and_counts() -> None:
    source = read("web/components/VettedList.tsx")
    assert '<option value="any">Daily best</option>' in source
    assert 'aria-label="Daily-best actual-odds band"' in source
    assert 'aria-label="Optional refinement"' in source
    assert "in band / " in source
    assert "fixtures)" in source
    assert "legacyMinToBand" in source
    assert "Model chance" in source
    assert "break-even" in source
    assert "model return" in source
    assert "counts.groups.get(group)?.size" in source
    assert "counts.markets.get(market.id)?.size" in source


def test_no_strong_possible_or_value_strength_labels() -> None:
    source = read("web/components/VettedList.tsx")
    for removed in ("'Strong' : 'Possible'", "Value legs only", "ticketVsFair", "ticketMinPlay", "Play only at odds"):
        assert removed not in source, removed
    how = read("web/app/how-it-works/page.tsx")
    assert "Strong and Possible" not in how
    assert "Best bets: the Daily best list" in how


def test_any_rule_and_correct_score_unchanged() -> None:
    rule = read("web/lib/vetting.ts")
    assert "export const ANY_RULE: VettingRule = DEFAULT_RULE;" in rule
    vetted = read("web/lib/vetted.ts")
    assert "isHiddenMarketId" in vetted
    source = read("web/components/VettedList.tsx")
    assert "isHiddenMarketId" in source


def test_value_distinguishes_loading_failure_unpriced_and_empty() -> None:
    source = read("web/components/ValueList.tsx")
    for needle in (
        "roundState", "marketsState", "pricesState",
        "Loading the round data…",
        "Could not load the round data",
        "Loading Mozzart prices…",
        "Could not load Mozzart prices.",
        "This build has no Mozzart prices",
        "No Mozzart snapshot for this round.",
        "No Value bets in this round.",
        "Loading market labels…",
        "Market labels could not be loaded",
        "activeMeta", "activeKind", "roundMeta",
    ):
        assert needle in source, needle
    assert "kind === 'example'" not in source


def test_pages_use_active_client_round_meta() -> None:
    for rel, heading in (
        ("web/app/page.tsx", "Best bets"),
        ("web/app/value/page.tsx", "Value bets"),
        ("web/app/explore/page.tsx", "Explore"),
    ):
        source = read(rel)
        assert "roundMeta" in source
        assert "roundMeta={roundMeta}" in source
        assert heading in source
        assert "chosen.label} — best plays" not in source
        assert "chosen.label} — value bets" not in source


def test_explore_round_identity_is_client_scoped() -> None:
    source = read("web/components/Picker.tsx")
    assert "roundMeta" in source
    assert "activeMeta" in source
    assert "activeKind" in source
    assert "activeKind === 'example'" in source
    assert "Example" in source
    # The table and ticket behaviour are intentionally untouched.
    for needle in ("Target tickets", "Suggested tickets — past rounds", "sortRows", "matchParam"):
        assert needle in source, needle


def test_report_research_table_labels() -> None:
    source = read("web/app/report/page.tsx")
    normalized = " ".join(source.split())
    for needle in (
        "Legacy research · STRICT_checks TYPE_RULE cohort",
        "not the current Daily-best list",
        "legacy 58% cohort",
        "calibrated probability ≥",
        "not realised Mozzart profit",
    ):
        assert " ".join(needle.split()) in normalized, needle
    assert "highest lift" not in source
    assert "report.note" not in source
    assert "unified 58% selection" not in source


def test_combo_record_mozzart_footnote_is_conditional() -> None:
    source = read("web/components/ComboRecord.tsx")
    assert "hasMozzart" in source
    assert "Mozzart returns are included where settled rounds carry frozen prices." in source
    assert "Mozzart returns appear once settled live rounds carry frozen prices; there are none yet." in source


def test_user_facing_copy_is_current() -> None:
    how = read("web/app/how-it-works/page.tsx")
    for needle in (
        "Twenty-two main divisions",
        "Tuesday, Saturday and Sunday",
        "Best bets: the Daily best list",
        "Automatic round proposals",
        "All 1.20+",
        "Mozzart snapshots and Value",
        "Value bets remain a separate experimental page",
    ):
        assert needle in how, needle
    for stale in ("twelve", "1.54", "40–65", "High/Low", "Tuesday and Saturday"):
        assert stale not in how, stale

    record = read("web/app/record/page.tsx")
    assert "40–65" not in record
    assert "40-65" not in record
    assert "inRange" not in record
