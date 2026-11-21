"""TYPE_RULE backtest per group, walk-forward (data before each round only).

For every Tuesday/Saturday/Sunday round from 2019-20 to 2025-26 the goals model
and the empirical rates are fitted on matches before that round. Each row is
calibrated with the target season's picker factors (group x band, walk-forward),
then judged by TYPE_RULE: lift vs league usual, team records, model/empirical
agreement and a fair-odds cap. For each group we keep one passing bet per match
(highest lift) and report picks per round, landed %, predicted %, return at fair
odds and a 95% CI bootstrapped over round dates.

No threshold is tuned on results.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from ..markets import MARKETS, market_mask, settle
from ..vetting import TYPE_RULE
from .data import EPOCH, build_arrays, subset
from .empirical import build as build_empirical
from .goals_engine import fit as fit_goals
from .grid import joint_vector
from .picker_backtest import MIN_TRAINING_MATCHES, ROUND_WEEKDAYS, band_of, season_start
from .ranking_backtest import RETURN_BOOTSTRAP_RESAMPLES, RETURN_BOOTSTRAP_SEED, mean_return_ci

SEASONS = tuple(range(2019, 2026))
GROUPS = ("Combos", "HT/FT", "Goals", "BTTS", "Half-time", "Team goals", "Result & double chance")
HIDDEN_GROUPS = {"Correct score"}


def season_label(year: int) -> str:
    return f"{year}-{(year + 1) % 100:02d}"


def passes(
    probability: float, model: float, usual: float, home_rate: float, home_n: int,
    away_rate: float, away_n: int, fair: float,
) -> bool:
    """Fast mirror of vetting.TYPE_RULE for the backtest loop."""
    if usual <= 0:
        return False
    if probability < usual * float(TYPE_RULE["min_lift_multiplier"]):
        return False
    if probability < usual + float(TYPE_RULE["min_lift_points"]):
        return False
    min_n = int(TYPE_RULE["min_record_n"])
    if home_n < min_n or away_n < min_n or home_rate < usual or away_rate < usual:
        return False
    if abs(model - usual) > max(float(TYPE_RULE["min_agreement"]), float(TYPE_RULE["agreement_fraction"]) * probability):
        return False
    if fair > float(TYPE_RULE["max_fair_odds"]):
        return False
    return True


def _summarise(picks: list[dict]) -> dict:
    n = len(picks)
    if n == 0:
        return {
            "picks": 0, "rounds": 0, "picks_per_round": None, "landed": None,
            "predicted": None, "return": None, "return_ci": [None, None],
        }
    hits = sum(1 for pick in picks if pick["landed"])
    mean_return, (low, high) = mean_return_ci(
        picks, resamples=RETURN_BOOTSTRAP_RESAMPLES, seed=RETURN_BOOTSTRAP_SEED
    )
    rounds = len({pick["date"] for pick in picks})
    return {
        "picks": n,
        "rounds": rounds,
        "picks_per_round": round(n / rounds, 3) if rounds else None,
        "landed": round(hits / n, 4),
        "predicted": round(sum(pick["p"] for pick in picks) / n, 4),
        "return": None if mean_return is None else round(mean_return, 4),
        "return_ci": [
            None if low is None else round(low, 4),
            None if high is None else round(high, 4),
        ],
    }


def run(matches_by_division: dict[str, list], half_life: float, season_factors: dict | None = None) -> dict:
    season_factors = season_factors or {}
    mask = market_mask()
    positions_by_group = {
        group: [i for i, market in enumerate(MARKETS) if market.group == group and market.group not in HIDDEN_GROUPS]
        for group in GROUPS
    }

    prepared = []
    for code, matches in sorted(matches_by_division.items()):
        if not matches:
            continue
        ordered = sorted(matches, key=lambda match: (match.date, match.home, match.away))
        prepared.append((code, build_arrays(ordered), np.array([season_start(m) for m in ordered], dtype=np.int32)))

    picks_by_group: dict[str, list[dict]] = defaultdict(list)

    for target in SEASONS:
        factors = season_factors.get(season_label(target), {})
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
                empirical = build_empirical(train, day, half_life)
                home_lambda, away_lambda = goals.anchored_lambdas(test.home, test.away, test.odds, use_odds=True)

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
                    best: dict[str, dict] = {}
                    for group, positions in positions_by_group.items():
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
                            if not passes(probability, raw, usual, home_rate, home_n, away_rate, away_n, fair):
                                continue
                            lift = probability / usual if usual > 0 else 0.0
                            current = best.get(group)
                            if current is None or lift > current["lift"]:
                                best[group] = {
                                    "position": position,
                                    "p": probability,
                                    "fair": fair,
                                    "lift": lift,
                                }
                    hthg = None if np.isnan(test.hthg[row]) else int(test.hthg[row])
                    htag = None if np.isnan(test.htag[row]) else int(test.htag[row])
                    for group, pick in best.items():
                        market = MARKETS[pick["position"]]
                        hit = settle(market, int(test.fthg[row]), int(test.ftag[row]), hthg, htag)
                        if hit is None:
                            continue
                        picks_by_group[group].append(
                            {
                                "date": round_date.isoformat(),
                                "p": pick["p"],
                                "fair": pick["fair"],
                                "lift": pick["lift"],
                                "landed": bool(hit),
                                "return": (pick["fair"] - 1.0) if hit else -1.0,
                            }
                        )

    rows = []
    for group in GROUPS:
        summary = _summarise(picks_by_group.get(group, []))
        summary["group"] = group
        rows.append(summary)

    return {
        "seasons": [season_label(year) for year in SEASONS],
        "groups": rows,
        "rule": {
            "lift_multiplier": TYPE_RULE["min_lift_multiplier"],
            "lift_points": TYPE_RULE["min_lift_points"],
            "record_min_n": TYPE_RULE["min_record_n"],
            "agreement_min": TYPE_RULE["min_agreement"],
            "agreement_fraction": TYPE_RULE["agreement_fraction"],
            "max_fair_odds": TYPE_RULE["max_fair_odds"],
        },
        "bootstrap": {"resamples": RETURN_BOOTSTRAP_RESAMPLES, "seed": RETURN_BOOTSTRAP_SEED, "unit": "round date"},
        "note": (
            "Walk-forward: goals model and empirical rates use matches before each round; "
            "calibration uses picker.json season factors (group x band). One passing bet per match "
            "per group (highest lift). Return at fair odds."
        ),
    }


def write(matches_by_division: dict[str, list], half_life: float, path: Path, season_factors: dict | None = None) -> dict:
    payload = run(matches_by_division, half_life, season_factors)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return payload
