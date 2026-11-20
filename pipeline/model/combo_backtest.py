"""Combo backtest: singles and the best 2-5 leg tickets, walk-forward.

For every Tuesday/Saturday/Sunday round from 2019-20 to 2025-26 the model is
fitted on matches before the round. The singles strategy is the top 15 by
probability (one bet per match, FT 1/2 and above-80% bets ignored). The best
k-leg ticket is the top k of those, which maximises the product. Returns are at
fair odds; flat 1-unit stakes. Mozzart returns only exist for settled live
rounds with frozen prices.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

from ..counts import wilson_interval
from ..markets import MARKETS, market_mask, settle
from .data import EPOCH, build_arrays, subset
from .goals_engine import fit as fit_goals
from .grid import joint_vector
from .picker_backtest import band_of

SEASONS = tuple(range(2019, 2026))
ROUND_WEEKDAYS = (1, 5, 6)
MIN_TRAINING_MATCHES = 200
EXCLUDED = {"RESULT:1", "RESULT:2"}
MAX_PROBABILITY = 0.80
TOP_N = 15
SIZES = (2, 3, 4, 5)


def season_start(match) -> int:
    return int(str(match.season).split("-")[0])


def _product(values) -> float:
    total = 1.0
    for value in values:
        total *= value
    return total


def _summarise(rows: list[dict]) -> dict:
    n = len(rows)
    hits = sum(1 for row in rows if row["landed"])
    landed = hits / n if n else None
    predicted = sum(row["p"] for row in rows) / n if n else None
    mean_return = sum(row["ret"] for row in rows) / n if n else None
    low, high = wilson_interval(hits, n) if n else (None, None)
    longest = 0
    current = 0
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for row in rows:
        if row["ret"] < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
        equity += row["ret"]
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return {
        "tickets": n,
        "predicted": None if predicted is None else round(predicted, 4),
        "landed": None if landed is None else round(landed, 4),
        "ci": [None if low is None else round(low, 4), None if high is None else round(high, 4)],
        "return": None if mean_return is None else round(mean_return, 4),
        "longest_losing": longest,
        "worst_drawdown": round(worst, 3),
    }


def run(matches_by_division: dict[str, list], half_life: float, factors: dict | None = None) -> dict:
    factors = factors or {}
    mask = market_mask()
    prepared = []
    for code, matches in sorted(matches_by_division.items()):
        if not matches:
            continue
        ordered = sorted(matches, key=lambda match: (match.date, match.home, match.away))
        prepared.append((code, build_arrays(ordered), np.array([season_start(m) for m in ordered], dtype=np.int32)))

    strategies: dict[str, list[dict]] = {"Singles (top 15)": []}
    for size in SIZES:
        strategies[f"{size}-leg best"] = []

    for target in SEASONS:
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
                home_lambda, away_lambda = goals.anchored_lambdas(test.home, test.away, test.odds, use_odds=True)

                picks = []
                for row in range(len(test_index)):
                    lh = float(home_lambda[row])
                    la = float(away_lambda[row])
                    joint = joint_vector(
                        lh * goals.share_home, la * goals.share_away,
                        lh * (1 - goals.share_home), la * (1 - goals.share_away), goals.rho,
                    )
                    probs = joint @ mask
                    best = None
                    for position, market in enumerate(MARKETS):
                        if market.id in EXCLUDED:
                            continue
                        probability = float(probs[position])
                        if probability <= 0 or probability > MAX_PROBABILITY:
                            continue
                        band = band_of(probability)
                        factor = factors.get(f"{market.group}|{band}", 1.0) if band else 1.0
                        shown = min(0.999, max(0.001, probability * factor))
                        if best is None or shown > best[0]:
                            best = (shown, probability, position, row)
                    if best is not None:
                        picks.append(best)
                picks.sort(key=lambda item: -item[0])
                top = picks[:TOP_N]

                settled = []
                for shown, _probability, position, row in top:
                    hthg = None if np.isnan(test.hthg[row]) else int(test.hthg[row])
                    htag = None if np.isnan(test.htag[row]) else int(test.htag[row])
                    hit = settle(MARKETS[position], int(test.fthg[row]), int(test.ftag[row]), hthg, htag)
                    if hit is None:
                        continue
                    settled.append((shown, hit))
                if not settled:
                    continue

                for probability, hit in settled:
                    strategies["Singles (top 15)"].append(
                        {"p": probability, "landed": hit, "ret": (1.0 / probability - 1.0) if hit else -1.0}
                    )
                for size in SIZES:
                    if len(settled) < size:
                        continue
                    legs = settled[:size]
                    probability = _product(leg[0] for leg in legs)
                    all_hit = all(leg[1] for leg in legs)
                    fair = _product(1.0 / leg[0] for leg in legs)
                    strategies[f"{size}-leg best"].append(
                        {"p": probability, "landed": all_hit, "ret": (fair - 1.0) if all_hit else -1.0}
                    )

    summary = []
    for name, rows in strategies.items():
        stats = _summarise(rows)
        stats["strategy"] = name
        stats["mozzart"] = {"n": 0, "return": None}
        summary.append(stats)

    independence = []
    for size in SIZES:
        stats = next(row for row in summary if row["strategy"] == f"{size}-leg best")
        if stats["landed"] is not None and stats["predicted"]:
            independence.append(
                {
                    "size": size,
                    "predicted": stats["predicted"],
                    "landed": stats["landed"],
                    "ratio": round(stats["landed"] / stats["predicted"], 3),
                }
            )

    return {
        "seasons": [f"{year}-{(year + 1) % 100:02d}" for year in SEASONS],
        "strategies": summary,
        "independence": independence,
        "note": "Returns at fair odds; Mozzart returns only for settled live rounds with frozen prices.",
    }


def write(matches_by_division: dict[str, list], half_life: float, path: Path, factors: dict | None = None) -> dict:
    payload = run(matches_by_division, half_life, factors)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return payload
