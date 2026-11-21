"""Task 12 UX contracts: truthful states, active-round identity and current labels."""
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
        "Strong = top third of the displayed passing rows",
        "activeMeta", "activeKind", "roundMeta",
    ):
        assert needle in source, needle
    assert "Closest candidates" not in source
    assert "kind === 'example'" not in source


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
        "Strong and Possible",
        "minimum playable price",
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
