"""Ranking backtest: minimum-odds levels, log-odds lean, walk-forward calibration.

For each target season the shown percentage is scaled by a factor fitted on earlier
seasons' picks per strategy x group x level, and the lean score is the log-odds lift
of the shown probability over the league rate shrunk toward the pooled all-league
rate (n/(n+k), k from the tuned decisions).
"""
from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict

import numpy as np

from ..counts import wilson_interval
from ..markets import MARKETS, market_mask, settle
from .data import EPOCH, build_arrays, subset
from .empirical import build as build_empirical
from .goals_engine import fit as fit_goals
from .grid import joint_vector

SEASONS = tuple(range(2019, 2026))
ROUND_WEEKDAYS = (1, 5)
MIN_TRAINING_MATCHES = 200
LEVELS = (("any", 1.50), ("2.00+", 2.00), ("2.50+", 2.50), ("3.00+", 3.00))
FAIR_MIN = 1.50
FAIR_MAX = 4.00
EXCLUDED = {"RESULT:1", "RESULT:2"}
TOP_N = 15
STRATEGIES = ("lean", "probability")
LEAN_MIN_LIFT = 0.20
LEAN_MIN_LEAGUE_N = 200
SHRINK_K = 20.0
CALIBRATION_CLIP = (0.70, 1.15)


def season_start(match) -> int:
    return int(str(match.season).split("-")[0])


def logit(probability: float) -> float:
    p = min(max(probability, 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def _bucket() -> dict:
    return {"p": 0.0, "n": 0, "hits": 0, "fair": 0.0}


def _table(buckets: dict, calibrated: bool) -> list[dict]:
    out = []
    for (strategy, group, level), data in sorted(buckets.items()):
        if data["n"] < 30:
            continue
        hits = data["hits"]
        low, high = wilson_interval(hits, data["n"])
        out.append(
            {
                "strategy": strategy,
                "group": group,
                "level": level,
                "calibrated": calibrated,
                "picks": data["n"],
                "mean_probability": round(data["p"] / data["n"], 4),
                "mean_fair_odds": round(data["fair"] / data["n"], 3),
                "break_even": round(1.0 / (data["fair"] / data["n"]), 4) if data["fair"] else None,
                "hits": hits,
                "hit_rate": round(hits / data["n"], 4),
                "ci": [round(low, 4), round(high, 4)],
            }
        )
    return out


def _level_table(buckets: dict) -> list[dict]:
    """Per strategy x level summary for the Record page."""
    merged: dict[tuple[str, str], dict] = defaultdict(_bucket)
    for (strategy, _group, level), data in buckets.items():
        cell = merged[(strategy, level)]
        for key in ("p", "n", "hits", "fair"):
            cell[key] += data[key]
    out = []
    for (strategy, level), data in sorted(merged.items()):
        if data["n"] < 30:
            continue
        hits = data["hits"]
        low, high = wilson_interval(hits, data["n"])
        average_fair = data["fair"] / data["n"]
        out.append(
            {
                "strategy": strategy,
                "level": level,
                "picks": data["n"],
                "mean_fair_odds": round(average_fair, 3),
                "hit_rate": round(hits / data["n"], 4),
                "break_even": round(1.0 / average_fair, 4) if average_fair else None,
                "edge": round(hits / data["n"] - 1.0 / average_fair, 4) if average_fair else None,
                "ci": [round(low, 4), round(high, 4)],
            }
        )
    return out


def run(matches_by_division: dict[str, list], half_life: float, k: float = SHRINK_K) -> dict:
    del k  # the tuned k is the shrinkage constant; accepted for call-site symmetry
    raw: dict[tuple[str, str, str], dict] = defaultdict(_bucket)
    calibrated: dict[tuple[str, str, str], dict] = defaultdict(_bucket)
    season_raw: dict[int, dict[tuple[str, str, str], dict]] = defaultdict(lambda: defaultdict(_bucket))
    mask = market_mask()

    prepared = []
    for code, matches in sorted(matches_by_division.items()):
        if not matches:
            continue
        ordered = sorted(matches, key=lambda match: (match.date, match.home, match.away))
        prepared.append((code, build_arrays(ordered), np.array([season_start(m) for m in ordered], dtype=np.int32)))

    for target in SEASONS:
        # Phase 1: empirical rates per division for this season, then the pooled baseline.
        built: dict[str, tuple] = {}
        pooled_num = np.zeros(len(MARKETS))
        pooled_den = np.zeros(len(MARKETS))
        for code, arrays, starts in prepared:
            season_mask = starts == target
            if not season_mask.any():
                continue
            days = sorted({float(value) for value in arrays.dates[season_mask]})
            train_index = np.where(arrays.dates < days[0])[0]
            if len(train_index) < MIN_TRAINING_MATCHES:
                continue
            empirical = build_empirical(subset(arrays, train_index), days[0], half_life)
            built[code] = (arrays, starts, season_mask, days, empirical)
            pooled_num += empirical.league_rate * empirical.league_n
            pooled_den += empirical.league_n
        if not built:
            continue
        pooled = np.divide(pooled_num, np.where(pooled_den > 0, pooled_den, 1.0))

        factors: dict[tuple[str, str, str], float] = {}
        prior: dict[tuple[str, str, str], dict] = defaultdict(_bucket)
        for earlier in sorted(season_raw):
            if earlier >= target:
                break
            for key, data in season_raw[earlier].items():
                for field in ("p", "n", "hits", "fair"):
                    prior[key][field] += data[field]
        for key, data in prior.items():
            if data["n"] >= 50 and data["p"] > 0:
                ratio = data["hits"] / data["p"]
                factors[key] = float(min(max(ratio, CALIBRATION_CLIP[0]), CALIBRATION_CLIP[1]))

        for code, (arrays, starts, season_mask, days, empirical) in built.items():
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
                home_lambda, away_lambda = goals.anchored_lambdas(test.home, test.away, test.odds, use_odds=True)

                candidates: list[tuple] = []
                for row in range(len(test_index)):
                    lh = float(home_lambda[row])
                    la = float(away_lambda[row])
                    joint = joint_vector(
                        lh * goals.share_home, la * goals.share_away,
                        lh * (1 - goals.share_home), la * (1 - goals.share_away), goals.rho,
                    )
                    probs = joint @ mask
                    for position, market in enumerate(MARKETS):
                        if market.id in EXCLUDED:
                            continue
                        probability = float(probs[position])
                        if probability <= 0:
                            continue
                        fair = 1.0 / probability
                        if fair < FAIR_MIN or fair > FAIR_MAX:
                            continue
                        league_rate = float(empirical.league_rate[position])
                        league_n = float(empirical.league_n[position])
                        shrunk = (
                            (league_n * league_rate + SHRINK_K * float(pooled[position]))
                            / (league_n + SHRINK_K)
                            if league_n + SHRINK_K > 0
                            else league_rate
                        )
                        lift = logit(probability) - logit(shrunk)
                        candidates.append((probability, lift, league_n, market.group, position, row))

                for level, low in LEVELS:
                    usable = [c for c in candidates if 1.0 / c[0] >= max(FAIR_MIN, low)]
                    for strategy in STRATEGIES:
                        if strategy == "lean":
                            pool = [c for c in usable if c[2] >= LEAN_MIN_LEAGUE_N and c[1] >= LEAN_MIN_LIFT]
                            pool.sort(key=lambda c: (-c[1], -c[0]))
                        else:
                            pool = sorted(usable, key=lambda c: -c[0])

                        seen: set[int] = set()
                        taken = 0
                        for probability, lift, _ln, group, position, row in pool:
                            if row in seen:
                                continue
                            seen.add(row)
                            market = MARKETS[position]
                            hit = settle(
                                market,
                                int(test.fthg[row]),
                                int(test.ftag[row]),
                                None if np.isnan(test.hthg[row]) else int(test.hthg[row]),
                                None if np.isnan(test.htag[row]) else int(test.htag[row]),
                            )
                            if hit is None:
                                continue

                            key = (strategy, group, level)
                            for field, value in (("p", probability), ("n", 1), ("hits", 1 if hit else 0), ("fair", 1.0 / probability)):
                                raw[key][field] += value
                                season_raw[target][key][field] += value

                            factor = factors.get(key, 1.0)
                            shown = min(0.999, max(0.001, probability * factor))
                            shown_fair = 1.0 / shown
                            if shown_fair < max(FAIR_MIN, low) or shown_fair > FAIR_MAX:
                                continue
                            calibrated[key]["p"] += shown
                            calibrated[key]["n"] += 1
                            calibrated[key]["hits"] += 1 if hit else 0
                            calibrated[key]["fair"] += shown_fair

                            taken += 1
                            if taken >= TOP_N:
                                break

    final: dict[tuple[str, str, str], dict] = defaultdict(_bucket)
    for season in sorted(season_raw):
        for key, data in season_raw[season].items():
            for field in ("p", "n", "hits", "fair"):
                final[key][field] += data[field]
    calibration = {
        "|".join(key): round(float(min(max(d["hits"] / d["p"], CALIBRATION_CLIP[0]), CALIBRATION_CLIP[1])), 4)
        for key, d in final.items()
        if d["n"] >= 50 and d["p"] > 0
    }

    return {
        "seasons": [f"{year}-{(year + 1) % 100:02d}" for year in SEASONS],
        "levels": [level for level, _ in LEVELS],
        "strategies": list(STRATEGIES),
        "groups": _table(calibrated, True),
        "before": _table(raw, False),
        "level_summary": _level_table(calibrated),
        "calibration": calibration,
    }
