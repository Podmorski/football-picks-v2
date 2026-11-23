"""Vetting checks on hand-made candidates; a failing bet is never passed."""
from __future__ import annotations

from pipeline.vetting import (
    ANY_RULE,
    DEFAULT_RULE,
    TYPE_RULE,
    Candidate,
    c1, c2, c3, c4, c5, c6, c8, c9, c10, c11, c12,
    evaluate, evaluate_rows, lift_of, type_evaluate,
)


def good(**overrides) -> Candidate:
    base = dict(
        probability=0.60, model_probability=0.48, league_rate=0.40, league_n=5000,
        home_rate=0.50, home_n=20, away_rate=0.45, away_n=20, fair_odds=1.60,
        counts_probability=0.55, home_form=0.50, away_form=0.45, mozzart_odds=1.80,
        bookmaker_disagreement=0.05, bookmaker_p80=0.10, xg_for=1.6, xg_against=1.4,
        league_xg=1.4, bet_direction="result", division_matches=50,
        days_since_home=7, days_since_away=7, division_gap=3,
    )
    base.update(overrides)
    return Candidate(**base)


def test_default_rule_passes_a_good_candidate() -> None:
    passed, checks = evaluate(good(), DEFAULT_RULE)
    assert passed
    assert {check["id"] for check in checks} == {"c1", "c2", "c3", "c4", "c6", "c7"}


def type_good(**overrides) -> Candidate:
    base = dict(
        probability=0.20, model_probability=0.15, league_rate=0.12, league_n=1000,
        home_rate=0.13, home_n=12, away_rate=0.12, away_n=10, fair_odds=5.0,
    )
    base.update(overrides)
    return Candidate(**base)


def test_any_rule_is_the_default_rule() -> None:
    assert ANY_RULE == DEFAULT_RULE


def test_type_rule_thresholds_are_fixed() -> None:
    assert TYPE_RULE == {
        "min_lift_multiplier": 1.25,
        "min_lift_points": 0.03,
        "min_record_n": 8,
        "min_agreement": 0.05,
        "agreement_fraction": 0.25,
        "max_fair_odds": 6.0,
    }


def test_type_rule_has_no_probability_or_odds_floor() -> None:
    # 20% and fair 5.00 would fail the Any-bet rule and a 1.70 floor.
    candidate = type_good()
    assert candidate.probability < 0.45 and candidate.fair_odds >= 1.70
    assert type_evaluate(candidate)[0] is True
    assert evaluate(candidate, DEFAULT_RULE)[0] is False
    # A short price passes too: TYPE_RULE has no minimum odds.
    short = type_good(
        probability=0.667, league_rate=0.50, model_probability=0.50, fair_odds=1.50,
        home_rate=0.55, away_rate=0.52,
    )
    assert short.fair_odds < 1.70
    assert type_evaluate(short)[0] is True


def test_type_rule_rejects_long_shots() -> None:
    candidate = type_good(
        probability=1 / 6.5, league_rate=0.08, model_probability=0.08,
        fair_odds=6.5, home_rate=0.10, away_rate=0.09,
    )
    passed, checks = type_evaluate(candidate)
    assert passed is False
    assert next(check for check in checks if check["id"] == "t6")["passed"] is False


def test_type_rule_needs_lift_records_and_agreement() -> None:
    assert type_evaluate(type_good(probability=0.13))[0] is False
    assert type_evaluate(type_good(home_n=7))[0] is False
    assert type_evaluate(type_good(probability=0.20, model_probability=0.20))[0] is False
    # The agreement allowance grows with the probability: 12 points is fine at 60%.
    big = type_good(
        probability=0.60, league_rate=0.40, model_probability=0.52,
        fair_odds=1 / 0.60, home_rate=0.45, away_rate=0.42,
    )
    assert type_evaluate(big)[0] is True


def test_lift_of_is_probability_over_league_usual() -> None:
    assert round(lift_of(type_good()), 4) == 1.6667
    assert lift_of(type_good(league_rate=0.0)) == 0.0


def test_c1_threshold() -> None:
    assert c1(good(probability=0.44), 0.45)[0] is False
    assert c1(good(probability=0.45), 0.45)[0] is True


def test_c2_league_plus_five() -> None:
    assert c2(good(probability=0.44, league_rate=0.40))[0] is False
    assert c2(good(probability=0.46, league_rate=0.40))[0] is True


def test_c3_team_records() -> None:
    assert c3(good(away_n=7))[0] is False
    assert c3(good(home_rate=0.30, league_rate=0.40))[0] is False
    assert c3(good())[0] is True


def test_c4_agreement_uses_team_empirical() -> None:
    # For good(): ((20*0.50 + 20*0.40)/40 + (20*0.45 + 20*0.40)/40)/2 = 0.4375.
    assert c4(good(model_probability=0.70))[0] is False
    assert c4(good(model_probability=0.48))[0] is True
    assert "empirical 43.8%" in c4(good())[1]
    # A model far from the league usual but close to the team estimate passes.
    strong = good(model_probability=0.60, home_rate=0.80, away_rate=0.80)
    assert c4(strong)[0] is True


def test_c5_recent_form() -> None:
    assert c5(good(home_form=0.30))[0] is False
    assert c5(good())[0] is True


def test_c6_floor() -> None:
    assert c6(good(fair_odds=1.39))[0] is False
    assert c6(good(fair_odds=1.40))[0] is True


def test_c7_is_a_flag_not_a_filter() -> None:
    passed, checks = evaluate(good(mozzart_odds=1.10), DEFAULT_RULE)
    assert passed
    assert next(check for check in checks if check["id"] == "c7")["passed"] is False


def test_c8_bookmaker_disagreement() -> None:
    assert c8(good(bookmaker_disagreement=0.20, bookmaker_p80=0.10))[0] is False
    assert c8(good())[0] is True


def test_c9_xg_direction() -> None:
    assert c9(good(xg_for=1.0, xg_against=1.0, league_xg=1.4, bet_direction="goals"))[0] is False
    assert c9(good(bet_direction="goals"))[0] is True


def test_c10_promoted() -> None:
    assert c10(good(division_matches=7))[0] is False


def test_c11_rest() -> None:
    assert c11(good(days_since_away=2))[0] is False


def test_c12_international_gap() -> None:
    assert c12(good(division_gap=10))[0] is False


def test_evaluate_never_passes_a_failing_rule() -> None:
    rule = {"c1": 0.50, "c2": True, "c3": True, "c4": True, "c6": True, "c7": True}
    passed, _checks = evaluate(good(probability=0.48), rule)
    assert passed is False


def test_empty_state() -> None:
    passing, failing = evaluate_rows([], DEFAULT_RULE)
    assert passing == [] and failing == []


def test_evaluate_rows_splits() -> None:
    rows = [good(probability=0.60).__dict__, good(probability=0.30, model_probability=0.30).__dict__]
    passing, failing = evaluate_rows(rows, DEFAULT_RULE)
    assert len(passing) == 1
    assert len(failing) == 1


def test_ticks_match_vetting() -> None:
    passed, checks = evaluate(good(), DEFAULT_RULE)
    assert passed
    by_id = {check["id"]: check for check in checks}
    for check_id in ("c1", "c2", "c3", "c4", "c6"):
        assert by_id[check_id]["passed"] is True
    failed_passed, failed_checks = evaluate(good(probability=0.30, model_probability=0.30), DEFAULT_RULE)
    assert failed_passed is False
    assert {"c1", "c2"} <= {check["id"] for check in failed_checks if not check["passed"]}


def test_mozzart_value_toggle_is_gone_from_best_bets() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "web" / "components" / "VettedList.tsx").read_text(encoding="utf-8")
    assert "useParam('mozzart'" not in source
    assert "Only where Mozzart pays at least fair" not in source


def test_best_bets_band_and_legacy_min_mapping() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "web" / "components" / "VettedList.tsx").read_text(encoding="utf-8")
    shared = (root / "web" / "lib" / "dailyBest.ts").read_text(encoding="utf-8")
    assert "useParam('min', '')" in source
    assert "useParam('band', '')" in source
    assert "legacyMinToBand(minParam)" in source
    assert "export function selectDaily" in shared
    assert "export function legacyMinToBand" in shared
    assert "'1.70-2.30'" in shared
    assert "'4.01+'" in shared
    assert "'all'" in shared
