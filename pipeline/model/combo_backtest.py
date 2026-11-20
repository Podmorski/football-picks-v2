"""Target-payout combo backtest, walk-forward.

For every Tuesday/Saturday/Sunday round from 2019-20 to 2025-26 the model is
fitted on matches before the round and calibrated with that season's walk-forward
factors (fitted on earlier seasons only). The pool is each match's best "Combos"
bet with fair odds at least 1.50. For every target payout and max leg count the
optimiser (pipeline.ticket_opt) picks the highest-probability ticket whose
combined fair odds reach the target.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

from ..counts import wilson_interval
from ..markets import MARKETS, market_mask, settle
from ..ticket_opt import optimise
from .data import EPOCH, build_arrays, subset
from .goals_engine import fit as fit_goals
from .grid import joint_vector
from .picker_backtest import band_of

SEASONS = tuple(range(2019, 2026))
ROUND_WEEKDAYS = (1, 5, 6)
MIN_TRAINING_MATCHES = 200
MAX_PROBABILITY = 0.80
FLOOR = 1.50
TARGETS = (2.0, 3.0, 5.0, 10.0, 20.0)
MAX_LEGS = (2, 3, 4, 5)
GROUP = "Combos"


def season_start(match) -> int:
    return int(str(match.season).split("-")[0])


def season_label(year: int) -> str:
    return f"{year}-{(year + 1) % 100:02d}"


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


def run(matches_by_division: dict[str, list], half_life: float, season_factors: dict | None = None) -> dict:
    season_factors = season_factors or {}
    mask = market_mask()
    combos_positions = [i for i, market in enumerate(MARKETS) if market.group == GROUP]

    prepared = []
    for _code, matches in sorted(matches_by_division.items()):
        if not matches:
            continue
        ordered = sorted(matches, key=lambda match: (match.date, match.home, match.away))
        prepared.append((_code, build_arrays(ordered), np.array([season_start(m) for m in ordered], dtype=np.int32)))

    strategies: dict[tuple[float, int], list[dict]] = {
        (target, legs): [] for target in TARGETS for legs in MAX_LEGS
    }

    for target_season in SEASONS:
        factors = season_factors.get(season_label(target_season), {})
        for _code, arrays, starts in prepared:
            season_mask = starts == target_season
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

                pool: list[dict] = []
                for row in range(len(test_index)):
                    lh = float(home_lambda[row])
                    la = float(away_lambda[row])
                    joint = joint_vector(
                        lh * goals.share_home, la * goals.share_away,
                        lh * (1 - goals.share_home), la * (1 - goals.share_away), goals.rho,
                    )
                    probs = joint @ mask
                    best = None
                    for position in combos_positions:
                        probability = float(probs[position])
                        if probability <= 0 or probability > MAX_PROBABILITY:
                            continue
                        band = band_of(probability)
                        factor = factors.get(f"{MARKETS[position].group}|{band}", 1.0) if band else 1.0
                        shown = min(0.999, max(0.001, probability * factor))
                        fair = 1.0 / shown
                        if fair < FLOOR:
                            continue
                        if best is None or shown > best["pc"]:
                            best = {"pc": shown, "fair": fair, "position": position, "row": row}
                    if best is None:
                        continue
                    position = best["position"]
                    hthg = None if np.isnan(test.hthg[row]) else int(test.hthg[row])
                    htag = None if np.isnan(test.htag[row]) else int(test.htag[row])
                    hit = settle(MARKETS[position], int(test.fthg[row]), int(test.ftag[row]), hthg, htag)
                    if hit is None:
                        continue
                    pool.append(
                        {
                            "pc": best["pc"],
                            "fair": best["fair"],
                            "hit": hit,
                            "h": test.home[row],
                            "a": test.away[row],
                        }
                    )
                if not pool:
                    continue

                for target in TARGETS:
                    for legs in MAX_LEGS:
                        tickets = optimise(pool, target, legs, alternatives=1, min_fair=FLOOR)
                        if not tickets:
                            continue
                        ticket = tickets[0]
                        probability = 1.0 / ticket["fair"]
                        all_hit = all(leg["hit"] for leg in ticket["legs"])
                        strategies[(target, legs)].append(
                            {
                                "p": probability,
                                "landed": all_hit,
                                "ret": (ticket["fair"] - 1.0) if all_hit else -1.0,
                            }
                        )

    summary = []
    for target in TARGETS:
        for legs in MAX_LEGS:
            stats = _summarise(strategies[(target, legs)])
            stats["target"] = target
            stats["max_legs"] = legs
            stats["strategy"] = f"target {target:.2f} / max {legs}"
            stats["mozzart"] = {"n": 0, "return": None}
            summary.append(stats)

    return {
        "seasons": [season_label(year) for year in SEASONS],
        "targets": list(TARGETS),
        "max_legs": list(MAX_LEGS),
        "strategies": summary,
        "note": "Walk-forward model fit and calibration; returns at fair odds; Mozzart only for settled live rounds.",
    }


def write(matches_by_division: dict[str, list], half_life: float, path: Path, season_factors: dict | None = None) -> dict:
    payload = run(matches_by_division, half_life, season_factors)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return payload
