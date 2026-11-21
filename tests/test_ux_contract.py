"""Task 12/13 UX contracts: states, active-round identity, Ranked/Strict and labels."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_best_bets_distinguishes_loading_failure_and_empty_verdicts() -> None:
    source = read("web/components/VettedList.tsx")
    for needle in (
        "roundState", "marketsState", "pricesState",
        "Loading the round and market data…",
        "Could not load the round data",
        "Could not load the market data",
        "Mozzart prices could not be loaded.",
        "Mozzart prices are not embedded in this build.",
        "No Mozzart snapshot for this round.",
        "reach fair odds ≥",
        "0 of ${eligible.length} candidates passed",
        "Highest-probability candidates that failed",
        "Strong = probability ≥ 55%",
        "activeMeta", "activeKind", "roundMeta",
        "Any odds", "Ranked — all candidates", "Strict checks only",
        "Show all odds", "Show ranked candidates",
        "selectByMatch(eligible)",
        "mode === 'strict' && !item.passed",
        "Highest-probability {groupKey} option for this match",
        "Lower-probability alternatives",
        "Does not pass",
    ):
        assert needle in source, needle
    assert "Closest candidates" not in source
    assert "top third" not in source
    assert "strongLimit" not in source
    assert "kind === 'example'" not in source


def test_ranked_group_and_single_market_selection() -> None:
    source = read("web/components/VettedList.tsx")
    assert "const rankedDisplayed = useMemo" in source
    assert "selectByMatch(eligible)" in source
    assert "return [...eligible].sort((a, b) => b.candidate.probability - a.candidate.probability);" in source
    assert "const displayed = isAny || isStrict ? strictPassing : rankedDisplayed;" in source
    vetted = read("web/lib/vetted.ts")
    assert "export function selectByMatch" in vetted
    assert "item.candidate.probability > current.candidate.probability" in vetted


def test_ranked_includes_failing_htft_while_strict_still_excludes() -> None:
    source = read("web/components/VettedList.tsx")
    # Ranked group options are not gated by TYPE_RULE; strict options still are.
    assert "!isStrict || option.passed" in source
    assert "selectByMatch(eligible)" in source
    strict = read("web/lib/vetted.ts")
    assert "if (!item.passed) continue;" in strict

    from pipeline.vetting import Candidate, type_evaluate

    candidate = Candidate(
        probability=0.10, model_probability=0.90, league_rate=0.40, league_n=5000,
        home_rate=0.30, home_n=4, away_rate=0.30, away_n=4, fair_odds=10.0,
    )
    passed, checks = type_evaluate(candidate)
    assert passed is False
    by_id = {check["id"]: check["passed"] for check in checks}
    assert by_id["t1"] is False
    assert by_id["t3"] is False
    assert by_id["t4"] is False
    assert by_id["t6"] is False


def test_match_details_expose_all_options() -> None:
    source = read("web/components/VettedList.tsx")
    assert "const matchOptions = groupKey" in source
    assert "option.row.d === row.d && option.row.h === row.h && option.row.a === row.a" in source
    assert "Highest-probability {groupKey} option for this match" in source
    assert "Lower-probability alternatives" in source
    assert "option.candidate.probability >= 0.55 ? 'Strong' : 'Possible'" in source


def test_any_odds_and_counts_follow_mode() -> None:
    source = read("web/components/VettedList.tsx")
    assert '<option value="any">Any odds</option>' in source
    assert "minOdds === 'any' ? 0" in source
    assert "minParamRef" in source
    assert "Show all odds" in source
    assert "Counts follow the current league, mode and minimum odds." in source
    assert "mode === 'strict' && !item.passed" in source
    assert "Show ranked candidates" in source


def test_strong_is_absolute_in_every_view() -> None:
    source = read("web/components/VettedList.tsx")
    assert "candidate.probability >= 0.55" in source
    assert "top third" not in source
    assert "strongLimit" not in source
    how = read("web/app/how-it-works/page.tsx")
    assert "at or above 55% in every Best bets view" in how
    assert "top third" not in how


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
        "STRICT_checks cohort",
        "not the default Ranked group/market list",
        "Ranked mode has no established profitability record",
        "This is the Any-bet record only",
        "TYPE_RULE research backtest",
        "TYPE_RULE before the UI minimum-fair filter",
        "One pick per match by highest probability",
        "not realised Mozzart profit",
        "Return (fair)",
        "Footnote: one pick per match, highest probability",
    ):
        assert " ".join(needle.split()) in normalized, needle
    assert "highest lift" not in source
    assert "report.note" not in source


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
        "Ranked and strict",
        "Strong and Possible",
        "minimum playable price",
        "any odds",
        "Mozzart snapshots and Value",
        "Value is unproven",
    ):
        assert needle in how, needle
    for stale in ("twelve", "1.54", "40–65", "High/Low", "Tuesday and Saturday"):
        assert stale not in how, stale

    record = read("web/app/record/page.tsx")
    assert "40–65" not in record
    assert "40-65" not in record
    assert "inRange" not in record
