"""Ranking backtest: per market group x price range, replayed round by round.

Each round is predicted from components fitted only on matches strictly before the
round date, ranked exactly like the dashboard does, and settled from the real score.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import numpy as np

from ..counts import wilson_interval
from ..markets import MARKETS, market_mask, settle
from . import blend as blend_module
from .counts_engine import fit as fit_counts
from .data import EPOCH, build_arrays, subset
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


def season_start(match) -> int:
    return int(str(match.season).split("-")[0])


def _band_of(fair: float) -> str | None:
    for key, low, high in BANDS:
        if low <= fair < high:
            return key
    return None


def run(matches_by_division: dict[str, list], half_life: float, k: float) -> dict:
    buckets: dict[tuple[str, str], dict] = defaultdict(lambda: {"p": 0.0, "hits": 0, "n": 0})
    rounds: dict[str, set] = defaultdict(set)

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
                counts = fit_counts(train, day, half_life, k)
                goals = fit_goals(train, day, half_life)
                home_lambda, away_lambda = goals.anchored_lambdas(test.home, test.away, test.odds, use_odds=True)

                per_band: dict[str, list[tuple[float, int, int]]] = defaultdict(list)
                for row in range(len(test_index)):
                    lh = float(home_lambda[row])
                    la = float(away_lambda[row])
                    joint = joint_vector(
                        lh * goals.share_home, la * goals.share_away,
                        lh * (1 - goals.share_home), la * (1 - goals.share_away), goals.rho,
                    )
                    probs = joint @ market_mask()
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
                        per_band[band].append((probability, position, row))

                for band, candidates in per_band.items():
                    candidates.sort(key=lambda item: -item[0])
                    seen: set[int] = set()
                    taken = 0
                    for probability, position, row in candidates:
                        if row in seen:
                            continue
                        seen.add(row)
                        market = MARKETS[position]
                        hit = settle(market, int(test.fthg[row]), int(test.ftag[row]),
                                     None if np.isnan(test.hthg[row]) else int(test.hthg[row]),
                                     None if np.isnan(test.htag[row]) else int(test.htag[row]))
                        if hit is None:
                            continue
                        key = (market.group, band)
                        buckets[key]["p"] += probability
                        buckets[key]["n"] += 1
                        buckets[key]["hits"] += 1 if hit else 0
                        rounds[band].add(round_date.isoformat())
                        taken += 1
                        if taken >= TOP_N:
                            break

    rows = []
    for (group, band), data in sorted(buckets.items()):
        samples = data["n"]
        if samples < 30:
            continue
        hits = data["hits"]
        low, high = wilson_interval(hits, samples)
        rows.append(
            {
                "group": group,
                "band": band,
                "picks": samples,
                "mean_probability": round(data["p"] / samples, 4),
                "hits": hits,
                "hit_rate": round(hits / samples, 4),
                "ci": [round(low, 4), round(high, 4)],
            }
        )

    return {
        "seasons": [f"{year}-{(year + 1) % 100:02d}" for year in SEASONS],
        "bands": [band[0] for band in BANDS],
        "groups": rows,
        "rounds": {band: len(values) for band, values in rounds.items()},
    }
