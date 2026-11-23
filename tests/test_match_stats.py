"""Shared opened-detail match statistics: states, labels and boundaries."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_best_bets_and_explore_use_the_shared_component_only_when_open() -> None:
    for rel in ("web/components/VettedList.tsx", "web/components/Picker.tsx"):
        source = read(rel)
        assert "import MatchStats from '@/components/MatchStats'" in source
        assert source.count("<MatchStats") == 1
        assert "date={activeDate}" in source
        assert "div={row.d}" in source
        assert "home={row.h}" in source
        assert "away={row.a}" in source
        open_index = source.index("open ?")
        component_index = source.index("<MatchStats")
        assert component_index > open_index


def test_states_are_independent_and_exact() -> None:
    source = read("web/components/MatchStats.tsx")
    for needle in (
        "{ status: 'loading' }",
        "{ status: 'error' }",
        "{ status: 'unavailable' }",
        "Loading statistics.",
        "Statistics could not be loaded.",
        "No statistics available for this round/fixture.",
        "role=\"status\"",
        "role=\"alert\"",
        "response.status === 404",
        "!response.ok",
        "schema_version !== 1",
    ):
        assert needle in source, needle


def test_presentation_labels_windows_streaks_and_h2h() -> None:
    source = read("web/components/MatchStats.tsx")
    for needle in (
        "Match statistics — history before this fixture",
        "Historical frequencies describe past matches; they are not calibrated chances.",
        "Home team —", "Away team —",
        "Overall — last 6", "Overall — last 12",
        "${venue} — last 6", "${venue} — last 12",
        "Overall streaks", "${venue} streaks",
        "FT result", "HT result", "BTTS and goals", "HT/FT",
        "Head-to-head — prior main-division league meetings",
        "No prior main-division league meetings in the loaded history.",
        "current home team W-D-L",
    ):
        assert needle in source, needle
    for key in ("win", "unbeaten", "winless", "losing", "drawing", "btts", "no_btts", "over25", "under25"):
        assert f"key: '{key}'" in source
    for code in ("1-1", "1-X", "1-2", "X-1", "X-X", "X-2", "2-1", "2-X", "2-2"):
        assert f"'{code}'" in source


def test_component_is_neutral_and_does_not_filter_or_expose_correct_score() -> None:
    source = read("web/components/MatchStats.tsx")
    for forbidden in (
        "text-success", "text-destructive", "bg-success", "bg-destructive",
        "CORRECT_SCORE", "selectByMatch", "selectType", "selectPassing",
        "TYPE_RULE", "ANY_RULE", "onFilter", "sort(", "Strong", "recommend",
    ):
        assert forbidden not in source, forbidden
    assert "min-w-0" in source
    assert "overflow-x-auto" in source
    assert "lg:grid-cols-2" in source


def test_types_cover_the_sidecar_contract() -> None:
    types = read("web/lib/types.ts")
    for needle in (
        "DescriptiveWindow", "DescriptiveTeam", "DescriptiveH2H",
        "DescriptiveFixture", "DescriptiveFile", "schema_version", "cutoff_date",
        "overall6", "overall12", "venue6", "venue12",
    ):
        assert needle in types, needle
