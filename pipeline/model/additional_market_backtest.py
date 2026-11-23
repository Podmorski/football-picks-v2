"""Full walk-forward audit for research-only additional score-settleable markets.

Candidate single-market cohorts keep every eligible fixture. A separate
descriptive comparison adds unique candidates to research copies of the Combos
and HT/FT Ranked groups; production registries and selections are untouched.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from array import array
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..markets import MARKETS, market_mask, settle
from .additional_markets import (
    AUGMENTED_CANDIDATES,
    CANDIDATES,
    CandidateSpec,
    candidate_mask,
    catalogue_summary,
)
from .data import EPOCH, build_arrays, subset
from .empirical import build as build_empirical, signature_hits
from .goals_engine import fit as fit_goals
from .grid import joint_vector
from .picker_backtest import MIN_TRAINING_MATCHES, ROUND_WEEKDAYS, band_of, season_start
from .ranked_backtest import _clustered_mean_ci, _round
from .ranking_backtest import RETURN_BOOTSTRAP_RESAMPLES, RETURN_BOOTSTRAP_SEED, pick_return
from .type_backtest import SEASONS, season_label

SMALL_SAMPLE_SELECTIONS = 200
SMALL_SAMPLE_ROUND_DATES = 30
NOT_MEASURABLE = "realised historical return not measurable from current data"
AFFECTED_GROUPS = ("Combos", "HT/FT")


@dataclass(slots=True)
class CandidateStats:
    n: int = 0
    hits: int = 0
    p_sum: float = 0.0
    pc_sum: float = 0.0
    return_sum: float = 0.0
    fairs: array = field(default_factory=lambda: array("d"))
    dates: dict[str, list[float]] = field(default_factory=dict)

    def add(self, p: float, pc: float, landed: bool, date: str) -> None:
        fair = 1.0 / pc
        result = pick_return(fair, landed)
        self.n += 1
        self.hits += int(landed)
        self.p_sum += p
        self.pc_sum += pc
        self.return_sum += result
        self.fairs.append(fair)
        row = self.dates.setdefault(date, [0.0, 0.0])
        row[0] += 1
        row[1] += result

    def summary(self, spec: CandidateSpec) -> dict:
        landed = self.hits / self.n if self.n else None
        mean_p = self.p_sum / self.n if self.n else None
        mean_pc = self.pc_sum / self.n if self.n else None
        mean_return = self.return_sum / self.n if self.n else None
        _, ci = _clustered_mean_ci(list(self.dates.values()), 0, 1)
        return {
            "id": spec.id,
            "group": spec.group,
            "catalogue_status": spec.catalogue_status,
            "equivalent_existing_id": spec.equivalent_existing_id,
            "activation_blocker": spec.activation_blocker,
            "selections": self.n,
            "round_dates": len(self.dates),
            "landed": self.hits,
            "landed_pct": _round(landed),
            "mean_raw_p": _round(mean_p),
            "mean_pc": _round(mean_pc),
            "landed_minus_raw_p": (
                _round(landed - mean_p) if landed is not None and mean_p is not None else None
            ),
            "landed_minus_pc": (
                _round(landed - mean_pc) if landed is not None and mean_pc is not None else None
            ),
            "median_fair_odds": _round(float(np.median(self.fairs)), 3) if self.n else None,
            "fair_return": _round(mean_return),
            "fair_return_ci": [_round(ci[0]), _round(ci[1])],
            "small_sample": self.n < SMALL_SAMPLE_SELECTIONS or len(self.dates) < SMALL_SAMPLE_ROUND_DATES,
            "actual_bookmaker_return": {
                "measurement": NOT_MEASURABLE,
                "reason": "No exact pre-match historical bookmaker mapping exists for this combination.",
            },
        }


@dataclass(slots=True)
class GroupImpact:
    evaluated: int = 0
    baseline_selections: int = 0
    augmented_selections: int = 0
    changed: int = 0
    additional_wins: int = 0
    baseline_changed_count: int = 0
    augmented_changed_count: int = 0
    baseline_changed_landed: int = 0
    baseline_changed_pc: float = 0.0
    augmented_changed_landed: int = 0
    augmented_changed_pc: float = 0.0
    winner_counts: Counter = field(default_factory=Counter)

    def summary(self) -> dict:
        baseline_denom = self.baseline_changed_count
        augmented_denom = self.augmented_changed_count
        return {
            "fixtures_evaluated": self.evaluated,
            "baseline_selections": self.baseline_selections,
            "augmented_selections": self.augmented_selections,
            "changed": self.changed,
            "changed_share_of_evaluated": _round(self.changed / self.evaluated) if self.evaluated else None,
            "additional_candidate_wins": self.additional_wins,
            "additional_winner_counts": dict(sorted(self.winner_counts.items())),
            "baseline_changed": {
                "selections": baseline_denom,
                "landed": self.baseline_changed_landed,
                "landed_pct": _round(self.baseline_changed_landed / baseline_denom) if baseline_denom else None,
                "mean_pc": _round(self.baseline_changed_pc / baseline_denom) if baseline_denom else None,
            },
            "augmented_changed": {
                "selections": augmented_denom,
                "landed": self.augmented_changed_landed,
                "landed_pct": _round(self.augmented_changed_landed / augmented_denom) if augmented_denom else None,
                "mean_pc": _round(self.augmented_changed_pc / augmented_denom) if augmented_denom else None,
            },
        }


def _calibrated(raw: float, group: str, factors: dict) -> tuple[float, float]:
    band = band_of(raw)
    factor = factors.get(f"{group}|{band}", 1.0) if band else 1.0
    return min(0.999, max(0.001, raw * factor)), 1.0 / min(0.999, max(0.001, raw * factor))


def _methodology() -> dict:
    return {
        "research_only": True,
        "candidates_are_not_registered": True,
        "seasons": [season_label(year) for year in SEASONS],
        "divisions": 22,
        "round_weekdays": ["Tuesday", "Saturday", "Sunday"],
        "half_life_days": 365,
        "minimum_training_matches": MIN_TRAINING_MATCHES,
        "walk_forward": "Goals and empirical rates use matches strictly before each round; picker factors are existing target-season factors and are not refit.",
        "single_market_cohort": "Every eligible fixture for each candidate; p raw and pc calibrated by group/band factor; fair = 1/pc.",
        "group_impact": (
            "Research copy only: unique candidates are added to Combos/HT.FT group Ranked selection; "
            "logically equivalent duplicates are excluded. One highest-pc candidate per match remains the rule."
        ),
        "bootstrap": {
            "resamples": RETURN_BOOTSTRAP_RESAMPLES,
            "seed": RETURN_BOOTSTRAP_SEED,
            "unit": "round date",
            "interval": "95% percentile CI",
        },
        "small_sample": "Flagged below 200 selections or 30 contributing round dates.",
        "actual_odds": "No candidate has an exact historical pre-match bookmaker mapping; no approximate mapping was created.",
        "interpretation": (
            "Fair return is model-price accounting, not realised profit. All candidates are multiple comparisons; "
            "no candidate is selected from the largest observed return. Group impact is descriptive, not causal."
        ),
        "correct_score": "Excluded and remains hidden.",
        "closing_odds": "Never used.",
    }


def run(matches_by_division: dict[str, list], half_life: float, season_factors: dict | None = None, *, progress: bool = False) -> dict:
    season_factors = season_factors or {}
    production_mask = market_mask()
    additional_mask = candidate_mask()
    production_positions = {
        group: [position for position, market in enumerate(MARKETS) if market.group == group]
        for group in AFFECTED_GROUPS
    }
    augmented_ids = {spec.id for spec in AUGMENTED_CANDIDATES}
    augmented_positions = {
        group: [position for position, spec in enumerate(CANDIDATES) if spec.group == group and spec.id in augmented_ids]
        for group in AFFECTED_GROUPS
    }
    stats = {spec.id: CandidateStats() for spec in CANDIDATES}
    impact = {group: GroupImpact() for group in AFFECTED_GROUPS}

    prepared = []
    for code, matches in sorted(matches_by_division.items()):
        if not matches:
            continue
        ordered = sorted(matches, key=lambda match: (match.date, match.home, match.away))
        prepared.append((code, build_arrays(ordered), np.array([season_start(m) for m in ordered], dtype=np.int32)))

    for target in SEASONS:
        factors = season_factors.get(season_label(target), {})
        if progress:
            print(f"additional-market audit season {season_label(target)}", flush=True)
        for _code, arrays, starts in prepared:
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
                # Fit the same pre-round empirical layer as the trusted engine;
                # these candidate metrics do not use a TYPE_RULE threshold.
                build_empirical(train, day, half_life)
                home_lambda, away_lambda = goals.anchored_lambdas(test.home, test.away, test.odds, use_odds=True)
                date = round_date.isoformat()

                for row in range(len(test_index)):
                    lh = float(home_lambda[row])
                    la = float(away_lambda[row])
                    joint = joint_vector(
                        lh * goals.share_home, la * goals.share_away,
                        lh * (1 - goals.share_home), la * (1 - goals.share_away), goals.rho,
                    )
                    production_probs = joint @ production_mask
                    additional_probs = joint @ additional_mask
                    fthg = int(test.fthg[row])
                    ftag = int(test.ftag[row])
                    hthg = None if np.isnan(test.hthg[row]) else int(test.hthg[row])
                    htag = None if np.isnan(test.htag[row]) else int(test.htag[row])
                    hits, applicable = signature_hits(fthg, ftag, hthg, htag)

                    candidate_rows: dict[int, tuple[float, float, float, bool | None]] = {}
                    for position, spec in enumerate(CANDIDATES):
                        raw = float(additional_probs[position])
                        landed = settle(spec.market, fthg, ftag, hthg, htag)
                        candidate_rows[position] = (raw, *_calibrated(raw, spec.group, factors), landed) if raw > 0 else (raw, 0.0, 0.0, landed)
                        if raw > 0 and landed is not None:
                            pc = candidate_rows[position][1]
                            stats[spec.id].add(raw, pc, bool(landed), date)

                    for group in AFFECTED_GROUPS:
                        baseline: tuple[int, float, bool] | None = None
                        for position in production_positions[group]:
                            raw = float(production_probs[position])
                            if raw <= 0 or not applicable[position]:
                                continue
                            pc, _fair = _calibrated(raw, group, factors)
                            if baseline is None or pc > baseline[1]:
                                baseline = (position, pc, bool(hits[position]))

                        augmented: tuple[str, int, float, bool] | None = None if baseline is None else (
                            "production", baseline[0], baseline[1], baseline[2]
                        )
                        for position in augmented_positions[group]:
                            raw, pc, _fair, landed = candidate_rows[position]
                            if raw <= 0 or landed is None:
                                continue
                            if augmented is None or pc > augmented[2]:
                                augmented = ("additional", position, pc, bool(landed))

                        if baseline is not None or augmented is not None:
                            impact[group].evaluated += 1
                        if baseline is not None:
                            impact[group].baseline_selections += 1
                        if augmented is not None:
                            impact[group].augmented_selections += 1
                        baseline_key = None if baseline is None else ("production", baseline[0])
                        augmented_key = None if augmented is None else (augmented[0], augmented[1])
                        if augmented_key != baseline_key:
                            block = impact[group]
                            block.changed += 1
                            if augmented is not None and augmented[0] == "additional":
                                block.additional_wins += 1
                                block.winner_counts[CANDIDATES[augmented[1]].id] += 1
                            if baseline is not None:
                                block.baseline_changed_count += 1
                                block.baseline_changed_landed += int(baseline[2])
                                block.baseline_changed_pc += baseline[1]
                            if augmented is not None:
                                block.augmented_changed_count += 1
                                block.augmented_changed_landed += int(augmented[3])
                                block.augmented_changed_pc += augmented[2]
            if progress:
                print(f"additional-market audit season {season_label(target)} division {_code} complete", flush=True)

    return {
        "schema_version": 1,
        "methodology": _methodology(),
        "catalogue": catalogue_summary(),
        "candidates": [stats[spec.id].summary(spec) for spec in CANDIDATES],
        "group_selection_impact": {
            group: impact[group].summary() for group in AFFECTED_GROUPS
        },
        "limitations": [
            "Fair-odds returns are not realised profitability.",
            "No candidate has an exact historical bookmaker price mapping.",
            "Catalogue evidence is from an existing 24 September 2026 snapshot, not a current availability check.",
            "Four proposed HT/FT+BTTS markets are logically equivalent to existing basic HT/FT markets.",
            "All candidate returns and group impacts are unadjusted multiple comparisons.",
            "No candidate is activated or recommended from the largest observed return.",
        ],
    }


def write(
    matches_by_division: dict[str, list], half_life: float, path: Path,
    season_factors: dict | None = None, *, progress: bool = False,
) -> dict:
    payload = run(matches_by_division, half_life, season_factors, progress=progress)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return payload


def main(argv=None) -> int:
    from ..config import RAW_DIR, WEB_DATA_DIR, load_divisions, load_extras
    from ..run import cached_seasons
    from ..run_model import load_by_division

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--half-life", type=float, default=365.0)
    parser.add_argument("--output", type=Path, default=WEB_DATA_DIR / "additional_markets_backtest.json")
    args = parser.parse_args(argv)

    divisions = load_divisions()
    current_start = cached_seasons(RAW_DIR)
    if current_start is None:
        raise RuntimeError("No cached seasons found")
    by_division = load_by_division(RAW_DIR, divisions, load_extras(), current_start)
    picker = json.loads((WEB_DATA_DIR / "picker.json").read_text(encoding="utf-8"))
    payload = write(
        {league.code: by_division.get(league.code, []) for league in divisions},
        args.half_life, args.output, picker["season_factors"], progress=True,
    )
    print(f"Wrote {len(payload['candidates'])} candidate cohorts to {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
