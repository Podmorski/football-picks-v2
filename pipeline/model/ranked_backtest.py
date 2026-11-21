"""Walk-forward audit of live Ranked versus Strict market-first selection.

The displayed probability is the picker-calibrated ``pc``: raw goals-model
probability multiplied by the target season's group/band factor and clipped to
[0.001, 0.999]. Fair odds are ``1 / pc``. Raw model probability is used only by
TYPE_RULE's agreement check. As in the existing TYPE_RULE backtest, calculations
use unrounded probabilities; the live JSON rounds pc to four decimals.

Primary cohorts are evaluated for every visible group with no fair-odds floor.
Ranked keeps one highest-pc candidate per match. Strict keeps one highest-pc
TYPE_RULE-passing candidate per match. The separate rejected-candidate diagnostic
contains every settleable visible candidate failing TYPE_RULE before either
one-per-match selection; it is not a selectable strategy or a paired causal
contrast. Every visible HT/FT-group market is also evaluated separately as an
explicitly exploratory single-market cohort (Ranked = every eligible fixture).

Only exact Bet365 PRE-MATCH mappings are eligible for actual-bookmaker returns:
1X2 and integer-total over/under 2.5. No similar market, average, synthetic margin,
closing price or Mozzart snapshot is substituted. Actual returns are always
labelled as priced-subset measurements, never whole-cohort realised profit.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from array import array
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..markets import MARKETS, market_mask
from ..vetting import TYPE_RULE, team_empirical_values
from .data import EPOCH, build_arrays, subset
from .empirical import build as build_empirical, signature_hits
from .goals_engine import fit as fit_goals
from .grid import joint_vector
from .picker_backtest import MIN_TRAINING_MATCHES, ROUND_WEEKDAYS, band_of, season_start
from .ranking_backtest import (
    RETURN_BOOTSTRAP_RESAMPLES,
    RETURN_BOOTSTRAP_SEED,
    pick_return,
)
from .type_backtest import GROUPS, SEASONS, _summarise as summarise_legacy_strict
from .type_backtest import passes as strict_passes, season_label

BOOTSTRAP_RESAMPLES = RETURN_BOOTSTRAP_RESAMPLES
BOOTSTRAP_SEED = RETURN_BOOTSTRAP_SEED
SMALL_SAMPLE_SELECTIONS = 200
SMALL_SAMPLE_ROUND_DATES = 30
NOT_MEASURABLE = "realised historical return not measurable from current data"

# One bookmaker, one exact market, one explicitly pre-match column. BbAv/Avg are
# not bookmaker prices; PSC/AvgC/B365C and all other closing fields are forbidden.
BOOKMAKER_PRICE_COLUMNS = {
    "RESULT:1": "B365H",
    "RESULT:X": "B365D",
    "RESULT:2": "B365A",
    "GOAL_RANGE_FT:3+": "B365>2.5",
    "GOAL_RANGE_FT:0-2": "B365<2.5",
}

POSITIONS_BY_GROUP = {
    group: tuple(i for i, market in enumerate(MARKETS) if market.group == group)
    for group in GROUPS
}
HTFT_POSITIONS = POSITIONS_BY_GROUP["HT/FT"]
FAILURE_IDS = ("t1", "t3", "t4", "t6")


@dataclass(slots=True)
class AuditCandidate:
    position: int
    p: float
    raw: float
    fair: float
    lift: float
    landed: bool | None
    passed: bool
    failures: tuple[str, ...] = ()
    actual_odds: float | None = None


@dataclass(slots=True)
class Eligibility:
    fixtures: int = 0
    candidates: int = 0
    dates: set[str] = field(default_factory=set)


@dataclass(slots=True)
class OutcomeStats:
    n: int = 0
    hits: int = 0
    p_sum: float = 0.0
    covered_fixtures: int = 0
    dates: set[str] = field(default_factory=set)

    def add(self, candidate: AuditCandidate, date: str) -> None:
        assert candidate.landed is not None
        self.n += 1
        self.hits += int(candidate.landed)
        self.p_sum += candidate.p
        self.dates.add(date)

    def summary(self, eligible_candidates: int, rejected_candidates: int) -> dict:
        landed = self.hits / self.n if self.n else None
        predicted = self.p_sum / self.n if self.n else None
        return {
            "candidates": self.n,
            "fixtures": self.covered_fixtures,
            "round_dates": len(self.dates),
            "share_of_rejected_candidates": _round(self.n / rejected_candidates) if rejected_candidates else None,
            "share_of_eligible_candidates": _round(self.n / eligible_candidates) if eligible_candidates else None,
            "landed": self.hits,
            "landed_pct": _round(landed),
            "mean_predicted": _round(predicted),
            "predicted_minus_landed": (
                _round(predicted - landed) if predicted is not None and landed is not None else None
            ),
            "small_sample": self.n < SMALL_SAMPLE_SELECTIONS or len(self.dates) < SMALL_SAMPLE_ROUND_DATES,
        }


@dataclass(slots=True)
class Cohort:
    """Aggregate picks online; only fair odds and date totals are retained."""

    n: int = 0
    hits: int = 0
    p_sum: float = 0.0
    return_sum: float = 0.0
    covered_fixtures: int = 0
    fairs: array = field(default_factory=lambda: array("d"))
    # date -> [n, hits, p sum, fair-return sum, actual n, actual-return sum]
    dates: dict[str, list[float]] = field(default_factory=dict)
    actual_mapped: int = 0
    actual_priced: int = 0

    def add(self, candidate: AuditCandidate, date: str, *, new_fixture: bool) -> None:
        assert candidate.landed is not None
        hit = int(candidate.landed)
        fair_return = pick_return(candidate.fair, bool(candidate.landed))
        self.n += 1
        self.hits += hit
        self.p_sum += candidate.p
        self.return_sum += fair_return
        self.fairs.append(candidate.fair)
        if new_fixture:
            self.covered_fixtures += 1
        row = self.dates.setdefault(date, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        row[0] += 1
        row[1] += hit
        row[2] += candidate.p
        row[3] += fair_return

        market_id = MARKETS[candidate.position].id
        if market_id in BOOKMAKER_PRICE_COLUMNS:
            self.actual_mapped += 1
        if candidate.actual_odds is not None:
            self.actual_priced += 1
            row[4] += 1
            row[5] += pick_return(candidate.actual_odds, bool(candidate.landed))

    def summary(self, eligibility: Eligibility, *, candidate_diagnostic: bool = False) -> dict:
        landed = self.hits / self.n if self.n else None
        predicted = self.p_sum / self.n if self.n else None
        fair_return = self.return_sum / self.n if self.n else None
        _, fair_ci = _clustered_mean_ci(list(self.dates.values()), 0, 3)
        output = {
            "selections": self.n,
            "round_dates": len(self.dates),
            "covered_fixtures": self.covered_fixtures,
            "eligible_fixtures": eligibility.fixtures,
            "eligible_round_dates": len(eligibility.dates),
            "fixture_coverage": _round(self.covered_fixtures / eligibility.fixtures) if eligibility.fixtures else None,
            "eligible_candidates": eligibility.candidates,
            "landed": self.hits,
            "landed_pct": _round(landed),
            "mean_predicted": _round(predicted),
            "predicted_minus_landed": (
                _round(predicted - landed) if predicted is not None and landed is not None else None
            ),
            "median_fair_odds": _round(float(np.median(self.fairs)), 3) if self.n else None,
            "fair_return": _round(fair_return),
            "fair_return_ci": [_round(fair_ci[0]), _round(fair_ci[1])],
            "small_sample": self.n < SMALL_SAMPLE_SELECTIONS or len(self.dates) < SMALL_SAMPLE_ROUND_DATES,
            "actual_bookmaker_return": self._actual_summary(),
        }
        if candidate_diagnostic:
            output["candidate_coverage"] = _round(self.n / eligibility.candidates) if eligibility.candidates else None
            output["diagnostic_only"] = True
        return output

    def _actual_summary(self) -> dict:
        priced_dates = [row for row in self.dates.values() if row[4] > 0]
        actual_return = sum(row[5] for row in priced_dates) / self.actual_priced if self.actual_priced else None
        _, actual_ci = _clustered_mean_ci(priced_dates, 4, 5)
        measurable = self.actual_priced > 0
        return {
            "measurement": (
                "exact Bet365 pre-match return on the priced subset only"
                if measurable else NOT_MEASURABLE
            ),
            "market_mapped_selections": self.actual_mapped,
            "priced_selections": self.actual_priced,
            "mapped_coverage": _round(self.actual_mapped / self.n) if self.n else None,
            "priced_coverage": _round(self.actual_priced / self.n) if self.n else None,
            "priced_of_mapped": _round(self.actual_priced / self.actual_mapped) if self.actual_mapped else None,
            "round_dates": len(priced_dates),
            "return": _round(actual_return),
            "return_ci": [_round(actual_ci[0]), _round(actual_ci[1])],
            "scope_warning": (
                "Subset accounting only; this is not a realised return for the whole cohort."
                if measurable else "No exact mapped pre-match price supports an actual-return estimate."
            ),
        }


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


def _clustered_mean_ci(
    date_rows: list[list[float]], n_index: int, sum_index: int,
    resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED,
) -> tuple[float | None, list[float | None]]:
    """Ratio-of-sums cluster bootstrap, equivalent to mean_return_ci on picks."""
    rows = [row for row in date_rows if row[n_index] > 0]
    if not rows:
        return None, [None, None]
    counts = np.asarray([row[n_index] for row in rows], dtype=np.float64)
    totals = np.asarray([row[sum_index] for row in rows], dtype=np.float64)
    mean = float(totals.sum() / counts.sum())
    rng = np.random.default_rng(seed)
    draws = np.empty(resamples, dtype=np.float64)
    count = len(rows)
    for draw in range(resamples):
        chosen = rng.integers(0, count, count)
        draws[draw] = totals[chosen].sum() / counts[chosen].sum()
    low, high = np.percentile(draws, [2.5, 97.5])
    return mean, [float(low), float(high)]


def actual_price(market_id: str, odds: dict) -> float | None:
    """Return only an exact, valid Bet365 pre-match price; otherwise no claim."""
    column = BOOKMAKER_PRICE_COLUMNS.get(market_id)
    if column is None:
        return None
    value = odds.get(column)
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if np.isfinite(price) and price > 1.0 else None


def factors_for_target(season_factors: dict, target: int) -> dict:
    """Select only the precomputed walk-forward factors for the target season."""
    return season_factors.get(season_label(target), {})


def failure_reasons(
    probability: float, model: float, usual: float, home_rate: float, home_n: int,
    away_rate: float, away_n: int, fair: float,
) -> tuple[str, ...]:
    """Non-exclusive TYPE_RULE failures; mirrors t1/t3/t4/t6 independently."""
    failures = []
    if not (
        usual > 0
        and probability >= usual * float(TYPE_RULE["min_lift_multiplier"])
        and probability >= usual + float(TYPE_RULE["min_lift_points"])
    ):
        failures.append("t1")
    min_n = int(TYPE_RULE["min_record_n"])
    if home_n < min_n or away_n < min_n or home_rate < usual or away_rate < usual:
        failures.append("t3")
    empirical = team_empirical_values(usual, home_rate, home_n, away_rate, away_n)
    allowed = max(float(TYPE_RULE["min_agreement"]), float(TYPE_RULE["agreement_fraction"]) * probability)
    if abs(model - empirical) > allowed:
        failures.append("t4")
    if fair > float(TYPE_RULE["max_fair_odds"]):
        failures.append("t6")
    return tuple(failures)


def _visible(candidate: AuditCandidate) -> bool:
    return not MARKETS[candidate.position].id.startswith("CORRECT_SCORE:")


def select_group(candidates: list[AuditCandidate], group: str) -> tuple[AuditCandidate | None, AuditCandidate | None]:
    """Live group contract: Ranked best pc, Strict best passing pc, one each."""
    ranked = strict = None
    for candidate in candidates:
        if not _visible(candidate) or MARKETS[candidate.position].group != group:
            continue
        if ranked is None or candidate.p > ranked.p:
            ranked = candidate
        if candidate.passed and (strict is None or candidate.p > strict.p):
            strict = candidate
    return ranked, strict


def select_single_market(
    candidates: list[AuditCandidate], position: int,
) -> tuple[list[AuditCandidate], list[AuditCandidate]]:
    """Live single-market contract: every fixture, no Strict gate in Ranked."""
    eligible = [
        candidate for candidate in candidates
        if candidate.position == position and _visible(candidate)
    ]
    ranked = sorted(eligible, key=lambda candidate: candidate.p, reverse=True)
    strict = sorted((candidate for candidate in eligible if candidate.passed), key=lambda candidate: candidate.p, reverse=True)
    return ranked, strict


def _legacy_strict_pick(candidate: AuditCandidate, date: str) -> dict:
    assert candidate.landed is not None
    return {
        "date": date,
        "p": candidate.p,
        "fair": candidate.fair,
        "lift": candidate.lift,
        "landed": bool(candidate.landed),
        "return": pick_return(candidate.fair, bool(candidate.landed)),
    }


def _strict_parity(legacy: dict[str, list[dict]], reference: dict | None) -> dict:
    if reference is None:
        return {"status": "not_checked", "groups": []}
    expected = {row["group"]: row for row in reference["groups"]}
    rows = []
    fields = ("picks", "rounds", "picks_per_round", "landed", "predicted", "return", "return_ci")
    for group in GROUPS:
        actual = summarise_legacy_strict(legacy.get(group, []))
        wanted = expected[group]
        differences = {
            key: {"expected": wanted[key], "actual": actual[key]}
            for key in fields if actual[key] != wanted[key]
        }
        rows.append({"group": group, "matches": not differences, "differences": differences})
    return {
        "status": "exact" if all(row["matches"] for row in rows) else "mismatch",
        "reference": "web/public/data/type_backtest.json",
        "compared_fields": list(fields),
        "groups": rows,
    }


def _methodology() -> dict:
    return {
        "research_only": True,
        "probability": (
            "Displayed pc = raw goals-model p x target-season group/band calibration factor, "
            "clipped to [0.001, 0.999]; fair odds = 1/pc. Raw p is used only for t4 agreement."
        ),
        "numeric_precision": (
            "Unrounded internal probabilities, matching the existing TYPE_RULE backtest. "
            "The live round JSON rounds pc to four decimals; fair-return calculations here do not use "
            "the two-decimal fair-odds display string."
        ),
        "minimum_fair_odds": "Any odds (no floor)",
        "ranked": "One highest-pc visible candidate per match per group; single market keeps every eligible fixture; pc descending.",
        "strict": "TYPE_RULE exactly; one highest-pc passing candidate per match per group; single market keeps every passing fixture.",
        "strict_rejected": (
            "Every settleable visible group candidate failing at least one TYPE_RULE check before "
            "one-per-match selection. Candidate-level diagnostic only; not a selected-pick cohort."
        ),
        "walk_forward": (
            "For every division and Tuesday/Saturday/Sunday round, goals and empirical rates use only "
            "matches strictly before that date; at least 200 prior division matches are required."
        ),
        "calibration": (
            "picker.json season_factors fitted on seasons before each target season by picker_backtest; "
            "the target season's mapping only is applied. 2019-20 has no fitted factors and uses 1.0."
        ),
        "settlement": "Flat one-unit stake; fair profit = fair - 1 when landed and -1 when lost. Unsettleable selected rows are excluded.",
        "coverage": "Covered/eligible settleable fixtures. Rejected diagnostics also report rejected/eligible candidates.",
        "bootstrap": {
            "resamples": BOOTSTRAP_RESAMPLES,
            "seed": BOOTSTRAP_SEED,
            "unit": "round date",
            "interval": "95% percentile CI; dates resampled with replacement; ratio of summed returns to summed selections",
            "multiple_comparisons": "Intervals are unadjusted across all groups, checks and exploratory markets.",
        },
        "small_sample_rule": (
            f"Flagged when selections < {SMALL_SAMPLE_SELECTIONS} or contributing round dates < "
            f"{SMALL_SAMPLE_ROUND_DATES}; descriptive caution, not a significance test."
        ),
        "actual_odds": (
            "Optional exact Bet365 pre-match priced-subset returns only. No average, closing, similar-market, "
            "synthetic-margin or Mozzart substitution. Missing mappings/prices produce no actual-return claim."
        ),
        "interpretation": (
            "Fair-odds return is model-price accounting, not realised profit. Landed approximately equal to "
            "predicted supports calibration only. Ranked, Strict and rejected cohorts differ in composition; "
            "their contrast is descriptive and not a causal paired comparison. No cohort is selected as best."
        ),
        "htft_exploratory": (
            "Every visible HT/FT-group market is reported separately, including combination/double-chance "
            "members. These are secondary exploratory multiple comparisons, not confirmed strategies."
        ),
    }


def run(
    matches_by_division: dict[str, list], half_life: float, season_factors: dict | None = None,
    *, strict_reference: dict | None = None, progress: bool = False,
) -> dict:
    season_factors = season_factors or {}
    mask = market_mask()
    prepared = []
    for code, matches in sorted(matches_by_division.items()):
        if not matches:
            continue
        ordered = sorted(matches, key=lambda match: (match.date, match.home, match.away))
        prepared.append((code, build_arrays(ordered), np.array([season_start(m) for m in ordered], dtype=np.int32)))

    eligibility = {(kind, key): Eligibility() for kind, keys in (("group", GROUPS), ("market", HTFT_POSITIONS)) for key in keys}
    cohorts: dict[tuple[str, str, object], Cohort] = defaultdict(Cohort)
    reasons: dict[tuple[str, str], OutcomeStats] = defaultdict(OutcomeStats)
    legacy_strict: dict[str, list[dict]] = defaultdict(list)

    for target in SEASONS:
        factors = factors_for_target(season_factors, target)
        if progress:
            print(f"ranked audit season {season_label(target)}", flush=True)
        for code, arrays, starts in prepared:
            season_mask = starts == target
            if not season_mask.any():
                continue
            days = sorted({float(value) for value in arrays.dates[season_mask]})
            for day in days:
                round_date = EPOCH + dt.timedelta(days=int(day))
                if round_date.weekday() not in ROUND_WEEKDAYS:
                    continue
                train_index = np.where(arrays.dates < day)[0]
                test_index = np.where((arrays.dates == day) & season_mask)[0]
                if len(train_index) < MIN_TRAINING_MATCHES or len(test_index) == 0:
                    continue
                train = subset(arrays, train_index)
                test = subset(arrays, test_index)
                goals = fit_goals(train, day, half_life)
                empirical = build_empirical(train, day, half_life)
                home_lambda, away_lambda = goals.anchored_lambdas(test.home, test.away, test.odds, use_odds=True)
                date = round_date.isoformat()

                for row in range(len(test_index)):
                    lh = float(home_lambda[row])
                    la = float(away_lambda[row])
                    joint = joint_vector(
                        lh * goals.share_home, la * goals.share_away,
                        lh * (1 - goals.share_home), la * (1 - goals.share_away), goals.rho,
                    )
                    probs = joint @ mask
                    home_index = int(test.home[row])
                    away_index = int(test.away[row])
                    hthg = None if np.isnan(test.hthg[row]) else int(test.hthg[row])
                    htag = None if np.isnan(test.htag[row]) else int(test.htag[row])
                    hits, applicable = signature_hits(int(test.fthg[row]), int(test.ftag[row]), hthg, htag)
                    candidates_by_group: dict[str, list[AuditCandidate]] = {}

                    for group, positions in POSITIONS_BY_GROUP.items():
                        candidates = []
                        for position in positions:
                            raw = float(probs[position])
                            if raw <= 0:
                                continue
                            band = band_of(raw)
                            factor = factors.get(f"{group}|{band}", 1.0) if band else 1.0
                            probability = min(0.999, max(0.001, raw * factor))
                            fair = 1.0 / probability
                            usual = float(empirical.league_rate[position])
                            home_rate = float(empirical.home_rate[home_index][position])
                            away_rate = float(empirical.away_rate[away_index][position])
                            home_n = int(empirical.home_n[home_index])
                            away_n = int(empirical.away_n[away_index])
                            passed = strict_passes(
                                probability, raw, usual, home_rate, home_n, away_rate, away_n, fair,
                            )
                            landed = bool(hits[position]) if applicable[position] else None
                            failures = () if passed or landed is None else failure_reasons(
                                probability, raw, usual, home_rate, home_n, away_rate, away_n, fair,
                            )
                            market_id = MARKETS[position].id
                            candidates.append(AuditCandidate(
                                position=position, p=probability, raw=raw, fair=fair,
                                lift=probability / usual if usual > 0 else 0.0,
                                landed=landed, passed=passed, failures=failures,
                                actual_odds=actual_price(market_id, test.odds[row]),
                            ))
                        candidates_by_group[group] = candidates

                        eligible = eligibility[("group", group)]
                        settleable = [candidate for candidate in candidates if candidate.landed is not None]
                        if settleable:
                            eligible.fixtures += 1
                            eligible.candidates += len(settleable)
                            eligible.dates.add(date)

                        rejected_seen = False
                        reason_fixture_seen: set[str] = set()
                        for candidate in settleable:
                            if candidate.passed:
                                continue
                            assert candidate.failures
                            cohorts[("group", "rejected", group)].add(candidate, date, new_fixture=False)
                            rejected_seen = True
                            for reason in candidate.failures:
                                reasons[(group, reason)].add(candidate, date)
                                reason_fixture_seen.add(reason)
                        if rejected_seen:
                            cohorts[("group", "rejected", group)].covered_fixtures += 1
                        for reason in reason_fixture_seen:
                            reasons[(group, reason)].covered_fixtures += 1

                        ranked, strict = select_group(candidates, group)
                        if ranked is not None and ranked.landed is not None:
                            cohorts[("group", "ranked", group)].add(ranked, date, new_fixture=True)
                        if strict is not None and strict.landed is not None:
                            cohorts[("group", "strict", group)].add(strict, date, new_fixture=True)
                            legacy_strict[group].append(_legacy_strict_pick(strict, date))

                    for position in HTFT_POSITIONS:
                        candidates = [
                            candidate for candidate in candidates_by_group["HT/FT"]
                            if candidate.position == position and candidate.landed is not None
                        ]
                        if not candidates:
                            continue
                        eligible = eligibility[("market", position)]
                        eligible.fixtures += 1
                        eligible.candidates += len(candidates)
                        eligible.dates.add(date)
                        ranked, strict = select_single_market(candidates, position)
                        for candidate in ranked:
                            cohorts[("market", "ranked", position)].add(candidate, date, new_fixture=True)
                        for candidate in strict:
                            cohorts[("market", "strict", position)].add(candidate, date, new_fixture=True)
            if progress:
                print(f"ranked audit season {season_label(target)} division {code} complete", flush=True)

    group_rows = []
    legacy_summaries = {}
    for group in GROUPS:
        eligible = eligibility[("group", group)]
        ranked = cohorts[("group", "ranked", group)].summary(eligible)
        strict = cohorts[("group", "strict", group)].summary(eligible)
        rejected = cohorts[("group", "rejected", group)].summary(eligible, candidate_diagnostic=True)
        legacy = summarise_legacy_strict(legacy_strict.get(group, []))
        legacy_summaries[group] = legacy
        assert strict["selections"] == legacy["picks"]
        # Use the existing helper's exact Strict arithmetic and bootstrap for parity.
        strict.update({
            "selections": legacy["picks"],
            "round_dates": legacy["rounds"],
            "landed_pct": legacy["landed"],
            "mean_predicted": legacy["predicted"],
            "predicted_minus_landed": (
                _round(legacy["predicted"] - legacy["landed"])
                if legacy["predicted"] is not None and legacy["landed"] is not None else None
            ),
            "fair_return": legacy["return"],
            "fair_return_ci": legacy["return_ci"],
        })
        failure_rows = {
            reason: reasons[(group, reason)].summary(eligible.candidates, rejected["selections"])
            for reason in FAILURE_IDS
        }
        group_rows.append({
            "group": group,
            "cohorts": {"ranked": ranked, "strict": strict, "strict_rejected": rejected},
            "failure_reasons_non_exclusive": failure_rows,
        })

    htft_rows = []
    for position in HTFT_POSITIONS:
        market = MARKETS[position]
        eligible = eligibility[("market", position)]
        htft_rows.append({
            "market": market.id,
            "label": market.plain,
            "exploratory": True,
            "cohorts": {
                "ranked": cohorts[("market", "ranked", position)].summary(eligible),
                "strict": cohorts[("market", "strict", position)].summary(eligible),
            },
            "actual_price_mapping": BOOKMAKER_PRICE_COLUMNS.get(market.id),
            "actual_return_note": NOT_MEASURABLE,
        })

    return {
        "schema_version": 1,
        "seasons": [season_label(year) for year in SEASONS],
        "round_weekdays": ["Tuesday", "Saturday", "Sunday"],
        "divisions": sorted(code for code, matches in matches_by_division.items() if matches),
        "half_life_days": half_life,
        "methodology": _methodology(),
        "rule": dict(TYPE_RULE),
        "strict_parity": _strict_parity(legacy_strict, strict_reference),
        "groups": group_rows,
        "htft_markets_exploratory": htft_rows,
        "actual_odds_methodology": {
            "bookmaker": "Bet365",
            "price_type": "pre-match only",
            "mappings": [
                {"market": market, "column": column}
                for market, column in BOOKMAKER_PRICE_COLUMNS.items()
            ],
            "unmapped_markets": NOT_MEASURABLE,
            "coverage": "Reported per cohort as mapped, priced and priced-of-mapped selection shares.",
        },
        "limitations": [
            "Fair-odds returns do not establish realised profitability.",
            "Only the five explicit Bet365 mappings can support historical actual-bookmaker subset returns.",
            "HT/FT realised historical return is not measurable from current data.",
            "Failure reasons overlap and are non-exclusive; rejected candidates are not a one-per-match strategy.",
            "All intervals are unadjusted despite multiple group, check and exploratory-market comparisons.",
            "No optimal group, rule or filter is selected from observed returns.",
        ],
    }


def write(
    matches_by_division: dict[str, list], half_life: float, path: Path,
    season_factors: dict | None = None, *, strict_reference_path: Path | None = None,
    progress: bool = False,
) -> dict:
    reference = None
    if strict_reference_path is not None:
        reference = json.loads(strict_reference_path.read_text(encoding="utf-8"))
    payload = run(
        matches_by_division, half_life, season_factors,
        strict_reference=reference, progress=progress,
    )
    if reference is not None and payload["strict_parity"]["status"] != "exact":
        mismatches = [
            row for row in payload["strict_parity"]["groups"] if not row["matches"]
        ]
        raise RuntimeError(f"Strict cohort differs from committed TYPE_RULE backtest: {mismatches}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return payload


def main(argv=None) -> int:
    from ..config import RAW_DIR, WEB_DATA_DIR, load_divisions, load_extras
    from ..run import cached_seasons
    from ..run_model import load_by_division

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--half-life", type=float, default=365.0)
    parser.add_argument("--output", type=Path, default=WEB_DATA_DIR / "ranked_backtest.json")
    parser.add_argument("--strict-reference", type=Path, default=WEB_DATA_DIR / "type_backtest.json")
    args = parser.parse_args(argv)

    divisions = load_divisions()
    current_start = cached_seasons(RAW_DIR)
    if current_start is None:
        raise RuntimeError("No cached seasons found")
    by_division = load_by_division(RAW_DIR, divisions, load_extras(), current_start)
    picker = json.loads((WEB_DATA_DIR / "picker.json").read_text(encoding="utf-8"))
    payload = write(
        {league.code: by_division.get(league.code, []) for league in divisions},
        args.half_life, args.output, picker["season_factors"],
        strict_reference_path=args.strict_reference, progress=True,
    )
    print(f"Strict parity: {payload['strict_parity']['status']}", flush=True)
    print(f"Wrote complete aggregate audit: {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
