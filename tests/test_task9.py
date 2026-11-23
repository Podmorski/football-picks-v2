"""Task 9 A1-A4 wiring and the team-empirical agreement."""
from __future__ import annotations

from pathlib import Path

from pipeline.vetting import Candidate, type_evaluate

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_a1_type_agreement_uses_the_team_empirical() -> None:
    # League usual 40%, but both team records are 80%, so the team empirical is 60%.
    candidate = Candidate(
        probability=0.60, model_probability=0.60, league_rate=0.40, league_n=5000,
        home_rate=0.80, home_n=20, away_rate=0.80, away_n=20, fair_odds=1 / 0.60,
    )
    passed, checks = type_evaluate(candidate)
    assert passed
    agreement = next(check for check in checks if check["id"] == "t4")
    assert agreement["passed"] is True
    assert "empirical 60.0%" in agreement["value"]


def test_a1_team_empirical_is_wired_everywhere() -> None:
    python_rule = read("pipeline/vetting.py")
    assert "def team_empirical" in python_rule
    assert "team_empirical(candidate)" in python_rule
    ts_rule = read("web/lib/vetting.ts")
    assert "export function teamEmpirical" in ts_rule
    assert "teamEmpirical(candidate)" in ts_rule
    assert "countsProbability: teamEmpirical" in read("web/lib/vetted.ts")
    assert "team empirical" in read("web/components/VettedList.tsx")
    assert "team_empirical_values" in read("pipeline/model/type_backtest.py")


def test_a2_band_and_refinement_controls_are_in_every_view() -> None:
    source = read("web/components/VettedList.tsx")
    daily = read("web/lib/dailyBest.ts")
    assert "aria-label=\"Daily-best actual-odds band\"" in source
    assert "aria-label=\"Optional refinement\"" in source
    assert "BAND_OPTIONS.map" in source
    assert "REFINEMENTS.map" in source
    assert "selectDaily" in source
    assert "applyRefinement" in source
    assert "1.70-2.30" in daily
    assert "fair150" in daily and "fair200" in daily


def test_a3_dropdowns_are_full_width_on_mobile() -> None:
    source = read("web/components/VettedList.tsx")
    assert source.count("w-full rounded-lg border") >= 3
    assert "grid gap-3 sm:grid-cols-2 lg:grid-cols-4" in source


def test_a4_round_buttons_are_oldest_left_and_report_wording() -> None:
    for rel in ("web/app/page.tsx", "web/app/explore/page.tsx"):
        source = read(rel)
        assert ".sort((a, b) => (a.date < b.date ? -1 : 1))" in source
        assert ".slice(-6)" in source
    report = read("web/app/report/page.tsx")
    assert "Walk-forward over 2019-20..2025-26" in report
    assert "Footnote: one pick per match, highest probability" in report
