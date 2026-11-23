"""58% Best bets and automatic proposal UI/workflow contracts."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_best_bets_is_one_inclusive_58_list_without_rule_modes_or_badges() -> None:
    source = read("web/components/VettedList.tsx")
    assert "const BEST_BETS_MIN_PC = 0.58" in source
    assert "item.candidate.probability >= BEST_BETS_MIN_PC" in source
    assert "selectByMatch(qualified)" in source
    assert "No candidates meet the visible filters and 58% threshold." in source
    for removed in (
        "selectPassing", "selectType", "Ranked — all candidates", "Strict checks only",
        "Value legs only", "Play only at odds", "'Strong' : 'Possible'", "<Badge variant=\"value\">Value",
    ):
        assert removed not in source, removed


def test_my_tickets_puts_automatic_proposals_first_and_keeps_saved_secondary() -> None:
    source = read("web/app/tickets/page.tsx")
    automatic = source.index("Automatic proposal record")
    saved = source.index("My saved tickets")
    assert automatic < saved
    for needle in (
        "Automatic proposals require private Mozzart prices. This build is unpriced; no actual prices are shown.",
        "Flat benchmark", "Adaptive risk-managed simulation", "Actual odds",
        "shared by ${count} proposals", "Pending until every leg is terminal.",
        "lost", "void", "Paper convention", "not a profit guarantee",
    ):
        assert needle in source, needle
    assert "/data/proposed-tickets-private.json" in source
    assert "/data/proposed-tickets-record.json" in source


def test_private_proposals_are_preloaded_only_for_priced_builds_and_gitignored() -> None:
    script = read("web/scripts/fetch-prices.mjs")
    assert "proposed-tickets-private.json" in script
    assert "proposals" in script
    assert "PRICED !== '1'" in script
    ignored = read(".gitignore")
    assert "web/public/data/proposed-tickets-private.json" in ignored
    record = json.loads((ROOT / "web" / "public" / "data" / "proposed-tickets-record.json").read_text(encoding="utf-8"))
    text = json.dumps(record).lower()
    assert '"odds"' not in text and '"price"' not in text and '"prices"' not in text
    assert record["policy_version"] == "adaptive-quarter-kelly-v1"


def test_price_and_update_workflows_freeze_and_settle_proposals_without_extra_requests() -> None:
    cli = read("pipeline/mozzart/cli.py")
    assert "ensure_proposals" in cli
    assert "frozen_snapshot" in cli
    update = read(".github/workflows/update.yml")
    assert "pipeline.proposed_tickets aggregate" in update
    prices = read(".github/workflows/prices.yml")
    assert "pipeline.mozzart.cli" in prices
    assert "pipeline.proposed_tickets" not in prices


def test_report_marks_legacy_research_and_current_58_record() -> None:
    source = read("web/app/report/page.tsx")
    normalized = " ".join(source.split())
    assert "Legacy research · STRICT_checks TYPE_RULE cohort" in normalized
    assert "not the current Best bets list" in normalized
    assert "Best bets results · unified 58% selection" in normalized
    assert "calibrated probability ≥" in normalized
    assert "Strong" not in normalized


def test_no_login_or_task17_activation() -> None:
    tickets = read("web/app/tickets/page.tsx")
    proposals = read("pipeline/proposed_tickets.py")
    assert "login" not in tickets.lower()
    assert "additional_markets" not in proposals
    markets = json.loads((ROOT / "web" / "public" / "data" / "markets.json").read_text(encoding="utf-8"))
    assert not any(market["id"].startswith("BTTS_AND_GOALS:") for market in markets["markets"])
