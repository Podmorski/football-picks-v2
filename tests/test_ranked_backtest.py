"""Synthetic contracts for the Ranked/Strict walk-forward audit."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from pipeline.markets import MARKETS, MARKET_BY_ID
from pipeline.model.goals_engine import extract_targets
from pipeline.model.ranked_backtest import (
    BOOKMAKER_PRICE_COLUMNS,
    BOOTSTRAP_SEED,
    GROUPS,
    HTFT_POSITIONS,
    NOT_MEASURABLE,
    POSITIONS_BY_GROUP,
    AuditCandidate,
    Cohort,
    Eligibility,
    _clustered_mean_ci,
    actual_price,
    factors_for_target,
    failure_reasons,
    select_group,
    select_single_market,
)
from pipeline.model.ranking_backtest import mean_return_ci, pick_return
from pipeline.model.type_backtest import passes as strict_passes
from pipeline.vetting import Candidate, type_evaluate

ROOT = Path(__file__).resolve().parents[1]
POSITION = {market.id: position for position, market in enumerate(MARKETS)}


def candidate(
    market: str, p: float, *, passed: bool = True, landed: bool = True,
    failures: tuple[str, ...] = (), odds: dict | None = None,
) -> AuditCandidate:
    return AuditCandidate(
        position=POSITION[market], p=p, raw=p, fair=1.0 / p, lift=1.0,
        landed=landed, passed=passed, failures=failures,
        actual_odds=actual_price(market, odds or {}),
    )


def test_ranked_and_strict_group_selection_matches_web_contract() -> None:
    rows = [
        candidate("HTFT:1-1", 0.40, passed=False, failures=("t3",)),
        candidate("HTFT:X-X", 0.30, passed=True),
        candidate("HTFT:2-2", 0.20, passed=True),
        candidate("BTTS:GG", 0.95, passed=True),
        candidate("CORRECT_SCORE:2:1", 0.99, passed=True),
    ]
    ranked, strict = select_group(rows, "HT/FT")
    assert ranked is not None and ranked.p == 0.40
    assert strict is not None and strict.p == 0.30
    assert MARKET_BY_ID["CORRECT_SCORE:2:1"].group == "Correct score"


def test_highest_probability_is_one_per_match_not_highest_lift() -> None:
    low = candidate("HTFT:1-1", 0.20, passed=True)
    high = candidate("HTFT:X-X", 0.60, passed=True)
    low.lift = 9.0
    high.lift = 1.1
    ranked, strict = select_group([low, high], "HT/FT")
    assert ranked is high and strict is high


def test_single_market_keeps_every_eligible_fixture_and_strict_only_passing() -> None:
    first = candidate("HTFT:1-1", 0.20, passed=False, failures=("t1",))
    other_market = candidate("HTFT:X-X", 0.90, passed=True)
    second = candidate("HTFT:1-1", 0.60, passed=True)
    ranked, strict = select_single_market([first, other_market, second], POSITION["HTFT:1-1"])
    assert [row.p for row in ranked] == [0.60, 0.20]
    assert [row.p for row in strict] == [0.60]


def test_rejection_reasons_are_non_exclusive_and_match_shared_type_rule() -> None:
    failures = failure_reasons(0.10, 0.90, 0.40, 0.30, 4, 0.30, 4, 10.0)
    assert failures == ("t1", "t3", "t4", "t6")

    random.seed(14)
    for _ in range(1000):
        usual = random.uniform(0.01, 0.8)
        probability = random.uniform(0.01, 0.99)
        model = random.uniform(0.01, 0.99)
        home_rate = random.uniform(0.0, 1.0)
        away_rate = random.uniform(0.0, 1.0)
        home_n = random.randint(0, 20)
        away_n = random.randint(0, 20)
        fair = 1.0 / probability
        args = (probability, model, usual, home_rate, home_n, away_rate, away_n, fair)
        shared = Candidate(
            probability=probability, model_probability=model, league_rate=usual, league_n=1000,
            home_rate=home_rate, home_n=home_n, away_rate=away_rate, away_n=away_n, fair_odds=fair,
        )
        passed, checks = type_evaluate(shared)
        reasons = failure_reasons(*args)
        assert strict_passes(*args) == passed == (not reasons)
        assert {check["id"] for check in checks if not check["passed"]} == set(reasons)


def test_correct_score_is_not_in_any_configured_cohort() -> None:
    configured = [position for positions in POSITIONS_BY_GROUP.values() for position in positions]
    assert configured
    assert all(not MARKETS[position].id.startswith("CORRECT_SCORE:") for position in configured)
    assert "Correct score" not in GROUPS


def test_target_season_calibration_ignores_future_mappings() -> None:
    factors = {
        "2019-20": {},
        "2020-21": {"HT/FT|50-60": 0.90},
        "2021-22": {"HT/FT|50-60": 9.99},
        "2025-26": {"HT/FT|50-60": 8.88},
    }
    assert factors_for_target(factors, 2019) == {}
    assert factors_for_target(factors, 2020) == {"HT/FT|50-60": 0.90}
    factors["2021-22"]["HT/FT|50-60"] = 123.0
    assert factors_for_target(factors, 2020) == {"HT/FT|50-60": 0.90}


def test_no_closing_odds_are_used_by_prices_or_model_anchor() -> None:
    pre = {"B365H": 2.10, "B365D": 3.40, "B365A": 3.60, "B365>2.5": 1.90, "B365<2.5": 1.90}
    closing = {
        "B365CH": 1.01, "B365CD": 9.0, "B365CA": 15.0,
        "PSCH": 1.02, "PSCD": 9.1, "PSCA": 16.0,
        "AvgCH": 1.03, "AvgCD": 9.2, "AvgCA": 17.0,
    }
    assert actual_price("RESULT:1", closing) is None
    assert actual_price("RESULT:1", {**pre, **closing}) == 2.10
    assert extract_targets(closing) is None
    assert extract_targets(pre) == extract_targets({**pre, **closing})
    assert all("C" not in column.replace("B365", "", 1) for column in BOOKMAKER_PRICE_COLUMNS.values())


def test_fair_return_and_settlement_arithmetic() -> None:
    assert pick_return(2.50, True) == 1.50
    assert pick_return(2.50, False) == -1.0
    cohort = Cohort()
    cohort.add(candidate("RESULT:1", 0.40, landed=True), "2024-01-06", new_fixture=True)
    cohort.add(candidate("RESULT:X", 0.25, landed=False), "2024-01-09", new_fixture=True)
    eligibility = Eligibility(fixtures=2, candidates=2, dates={"2024-01-06", "2024-01-09"})
    summary = cohort.summary(eligibility)
    assert summary["selections"] == 2
    assert summary["landed"] == 1
    assert summary["landed_pct"] == 0.5
    assert summary["mean_predicted"] == 0.325
    assert summary["median_fair_odds"] == 3.25
    assert summary["fair_return"] == 0.25
    assert summary["small_sample"] is True


def test_date_bootstrap_matches_existing_pick_level_helper() -> None:
    cohort = Cohort()
    picks = []
    rows = [
        ("2024-01-06", "RESULT:1", 0.50, True),
        ("2024-01-06", "RESULT:X", 0.25, False),
        ("2024-01-09", "RESULT:2", 1 / 3, True),
    ]
    for date, market, probability, landed in rows:
        item = candidate(market, probability, landed=landed)
        cohort.add(item, date, new_fixture=True)
        picks.append({"date": date, "return": pick_return(item.fair, landed)})
    expected_mean, expected_ci = mean_return_ci(picks, resamples=40, seed=BOOTSTRAP_SEED)
    actual_mean, actual_ci = _clustered_mean_ci(
        list(cohort.dates.values()), 0, 3, resamples=40, seed=BOOTSTRAP_SEED,
    )
    assert actual_mean == pytest.approx(expected_mean)
    assert actual_ci == pytest.approx(expected_ci)


def test_missing_or_ambiguous_actual_price_makes_no_actual_return_claim() -> None:
    assert actual_price("BTTS:GG", {"B365>2.5": 2.0}) is None
    assert actual_price("GOAL_RANGE_FT:2+", {"B365>2.5": 2.0}) is None
    assert actual_price("RESULT:1", {}) is None
    assert actual_price("RESULT:1", {"B365H": 1.0}) is None
    assert actual_price("GOAL_RANGE_FT:3+", {"B365>2.5": 2.0}) == 2.0
    assert actual_price("GOAL_RANGE_FT:0-2", {"B365<2.5": 1.8}) == 1.8

    cohort = Cohort()
    cohort.add(candidate("RESULT:1", 0.50, odds={}), "2024-01-06", new_fixture=True)
    cohort.add(candidate("BTTS:GG", 0.50, odds={"B365>2.5": 2.0}), "2024-01-06", new_fixture=True)
    summary = cohort.summary(Eligibility(fixtures=2, candidates=2))["actual_bookmaker_return"]
    assert summary["market_mapped_selections"] == 1
    assert summary["priced_selections"] == 0
    assert summary["return"] is None
    assert summary["return_ci"] == [None, None]
    assert summary["measurement"] == NOT_MEASURABLE


def test_committed_audit_is_complete_parity_checked_and_aggregate_only() -> None:
    path = ROOT / "web" / "public" / "data" / "ranked_backtest.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["strict_parity"]["status"] == "exact"
    assert [row["group"] for row in report["groups"]] == list(GROUPS)
    assert len(report["htft_markets_exploratory"]) == len(HTFT_POSITIONS)
    assert len(report["htft_markets_exploratory"]) > 9
    required = {
        "selections", "round_dates", "fixture_coverage", "landed", "landed_pct",
        "mean_predicted", "predicted_minus_landed", "median_fair_odds",
        "fair_return", "fair_return_ci", "small_sample", "actual_bookmaker_return",
    }
    for row in report["groups"]:
        assert set(row["cohorts"]) == {"ranked", "strict", "strict_rejected"}
        assert set(row["failure_reasons_non_exclusive"]) == {"t1", "t3", "t4", "t6"}
        for cohort in row["cohorts"].values():
            assert required <= set(cohort)
            assert cohort["selections"] > 0
    for row in report["htft_markets_exploratory"]:
        assert not row["market"].startswith("CORRECT_SCORE:")
        assert row["actual_return_note"] == NOT_MEASURABLE
        for cohort in row["cohorts"].values():
            assert required <= set(cohort)
            assert cohort["actual_bookmaker_return"]["return"] is None
    assert {(item["market"], item["column"]) for item in report["actual_odds_methodology"]["mappings"]} == {
        ("RESULT:1", "B365H"), ("RESULT:X", "B365D"), ("RESULT:2", "B365A"),
        ("GOAL_RANGE_FT:3+", "B365>2.5"), ("GOAL_RANGE_FT:0-2", "B365<2.5"),
    }
    forbidden_record_keys = {"home", "away", "fthg", "ftag", "hthg", "htag", "raw_csv", "mozzart_prices"}

    def walk(value) -> None:
        if isinstance(value, dict):
            assert not (forbidden_record_keys & set(value))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(report)
