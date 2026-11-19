"""Ranking backtest for both rankings, per market group x price range.

A round is predicted from components fitted only on matches before that round date,
and the empirical league rates it leans on are built from matches before that season's
first round (never later than the round date itself).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import numpy as np

from ..counts import wilson_interval
from ..markets import MARKETS, market_mask, settle
from .counts_engine import fit as fit_counts
from .data import EPOCH, build_arrays, subset
from .empirical import build as build_empirical
from .goals_engine import fit as fit_goals
from .grid import joint_vector

SEASONS = tuple(range(2019, 2026))
ROUND_WEEKDAYS = (1, 5)
MIN_TRAINING_MATCHES = 200
BANDS = (
    ("1.70-2.00", 1.70, 2.00),
    ("2.00-3.00", 2.00, 3.00),
    ("3.00-5.00", 3.00, 5.00),
    ("5.00-10.00", 5.00, 10.00),
    ("10.00+", 10.00, float("inf")),
)
EXCLUDED = {"RESULT:1", "RESULT:2"}
TOP_N = 15
STRATEGIES = ("lean", "probability")
LEAN_MIN_RATIO = 1.10
LEAN_MIN_LEAGUE_N = 200


def season_start(match) -> int:
    return int(str(match.season).split("-")[0])


def _band_of(fair: float) -> str | None:
    for key, low, high in BANDS:
        if low <= fair < high:
            return key
    return None


def run(matches_by_division: dict[str, list], half_life: float, k: float) -> dict:
    buckets: dict[tuple[str, str, str], dict] = defaultdict(lambda: {"p": 0.0, "hits": 0, "n": 0})
    rounds: dict[tuple[str, str], set] = defaultdict(set)
    mask = market_mask()

    for code, matches in sorted(matches_by_division.items()):
        if not matches:
            continue
        ordered = sorted(matches, key=lambda match: (match.date, match.home, match.away))
        arrays = build_arrays(ordered)
        starts = np.array([season_start(match) for match in ordered], dtype=np.int32)

        for target in SEASONS:
            season_mask = starts == target
            if not season_mask.any():
                continue
            days = sorted({float(value) for value in arrays.dates[season_mask]})
            if not days:
                continue

            season_start_day = days[0]
            empirical_train = np.where(arrays.dates < season_start_day)[0]
            if len(empirical_train) < MIN_TRAINING_MATCHES:
                continue
            empirical = build_empirical(subset(arrays, empirical_train), season_start_day, half_life)

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
                fit_counts(train, day, half_life, k)  # keeps the run comparable with production

                home_lambda, away_lambda = goals.anchored_lambdas(test.home, test.away, test.odds, use_odds=True)
                per_band: dict[str, list[tuple[float, float, int, int]]] = defaultdict(list)
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
                        band = _band_of(fair)
                        if band is None:
                            continue
                        league_rate = float(empirical.league_rate[position])
                        league_n = float(empirical.league_n[position])
                        lean = probability / league_rate if league_rate > 0 else 0.0
                        per_band[band].append((probability, lean, league_n, position, row))

                for band, candidates in per_band.items():
                    for strategy in STRATEGIES:
                        if strategy == "lean":
                            usable = [
                                item for item in candidates
                                if item[2] >= LEAN_MIN_LEAGUE_N and item[1] >= LEAN_MIN_RATIO
                            ]
                            usable.sort(key=lambda item: (-item[1], -item[0]))
                        else:
                            usable = sorted(candidates, key=lambda item: -item[0])

                        seen: set[int] = set()
                        taken = 0
                        for probability, lean, _league_n, position, row in usable:
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
                            key = (strategy, market.group, band)
                            buckets[key]["p"] += probability
                            buckets[key]["n"] += 1
                            buckets[key]["hits"] += 1 if hit else 0
                            rounds[(strategy, band)].add(round_date.isoformat())
                            taken += 1
                            if taken >= TOP_N:
                                break

    rows = []
    for (strategy, group, band), data in sorted(buckets.items()):
        if data["n"] < 30:
            continue
        hits = data["hits"]
        low, high = wilson_interval(hits, data["n"])
        rows.append(
            {
                "strategy": strategy,
                "group": group,
                "band": band,
                "picks": data["n"],
                "mean_probability": round(data["p"] / data["n"], 4),
                "hits": hits,
                "hit_rate": round(hits / data["n"], 4),
                "ci": [round(low, 4), round(high, 4)],
            }
        )

    return {
        "seasons": [f"{year}-{(year + 1) % 100:02d}" for year in SEASONS],
        "bands": [band[0] for band in BANDS],
        "strategies": list(STRATEGIES),
        "groups": rows,
        "rounds": {f"{strategy}|{band}": len(values) for (strategy, band), values in rounds.items()},
    }
