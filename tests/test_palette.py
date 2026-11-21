"""Colour rule: green only for Landed, red only for Lost."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_green_and_red_only_on_landed_or_lost() -> None:
    for rel in (
        "web/components/VettedList.tsx",
        "web/components/Picker.tsx",
        "web/app/tickets/page.tsx",
    ):
        source = (ROOT / rel).read_text(encoding="utf-8")
        for line in source.splitlines():
            if "emerald" in line or "rose" in line:
                assert "landed" in line and "lost" in line, f"{rel}: {line.strip()}"


def test_no_destructive_text_outside_the_status_badge() -> None:
    for rel in ("web/components/VettedList.tsx", "web/components/Picker.tsx"):
        source = (ROOT / rel).read_text(encoding="utf-8")
        assert "text-destructive" not in source
        assert "text-success" not in source


def test_best_bets_cards_have_no_check_chips() -> None:
    source = (ROOT / "web/components/VettedList.tsx").read_text(encoding="utf-8")
    assert "check.passed ? '✓'" not in source
    assert "border-emerald" not in source
    assert "border-rose" not in source
