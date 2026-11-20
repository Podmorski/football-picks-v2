"""Picker calibration: highest-probability bet per match per group, walk-forward.

For every Tuesday/Saturday/Sunday round from 2019-20 to 2025-26 the model is
fitted on matches before the round date. For each market group we keep that
match's highest-probability bet (and, for "Any", the highest across groups with
FT home/away wins and anything above 80% ignored). A multiplicative factor per
group x 20-80%-band is fitted on seasons before the target season only, then the
out-of-sample record is what the Record page shows.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from ..markets import MARKETS, market_mask, settle
from .data import EPOCH, build_arrays, subset
from .goals_engine import fit as fit_goals
from .grid import joint_vector
from .ranking_backtest import CALIBRATION_CLIP, mean_return_ci

SEASONS = tuple(range(2019, 2026))
ROUND_WEEKDAYS = (1, 5, 6)  # Tue, Sat, Sun
MIN_TRAINING_MATCHES = 200
MIN_N = 30
ANY = "Any"
EXCLUDED = {"RESULT:1", "RESULT:2"}
BANDS = ("20-30", "30-40", "40-50", "50-60", "60-70", "70-80")
GROUPS = sorted({market.group for market in MARKETS})


def season_start(match) -> int:
    return int(str(match.season).split("-")[0])


def band_of(probability: float) -> str | None:
    pct = probability * 100.0
    if 20 <= pct < 30:
        return "20-30"
    if 30 <= pct < 40:
        return "30-40"
    if 40 <= pct < 50:
        return "40-50"
    if 50 <= pct < 60:
        return "50-60"
    if 60 <= pct < 70:
        return "60-70"
    if 70 <= pct < 80:
        return "70-80"
    return None


def _bucket() -> dict:
    return {"n": 0, "p": 0.0, "hits": 0, "fair": 0.0, "picks": []}


def _clip(value: float) -> float:
    return float(min(max(value, CALIBRATION_CLIP[0]), CALIBRATION_CLIP[1]))


def run(matches_by_division: dict[str, list], half_life: float) -> dict:
    mask = market_mask()
    positions_by_group = {
        group: [i for i, market in enumerate(MARKETS) if market.group == group]
        for group in GROUPS
    }
    excluded_positions = {i for i, market in enumerate(MARKETS) if market.id in EXCLUDED}

    prepared = []
    for code, matches in sorted(matches_by_division.items()):
        if not matches:
            continue
        ordered = sorted(matches, key=lambda match: (match.date, match.home, match.away))
        prepared.append((code, build_arrays(ordered), np.array([season_start(m) for m in ordered], dtype=np.int32)))

    season_raw: dict[int, dict[tuple[str, str], dict]] = defaultdict(lambda: defaultdict(_bucket))
    season_test: dict[int, dict[tuple[str, str], dict]] = defaultdict(lambda: defaultdict(_bucket))

    for target in SEASONS:
        prior: dict[tuple[str, str], dict] = defaultdict(_bucket)
        for earlier in sorted(season_raw):
            if earlier >= target:
                break
            for key, data in season_raw[earlier].items():
                for field in ("n", "p", "hits", "fair"):
                    prior[key][field] += data[field]
        factors = {
            key: _clip(data["hits"] / data["p"])
            for key, data in prior.items()
            if data["n"] >= 50 and data["p"] > 0
        }

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

                for row in range(len(test_index)):
                    lh = float(home_lambda[row])
                    la = float(away_lambda[row])
                    joint = joint_vector(
                        lh * goals.share_home, la * goals.share_away,
                        lh * (1 - goals.share_home), la * (1 - goals.share_away), goals.rho,
                    )
                    probs = joint @ mask
                    chosen: dict[str, tuple[float, int]] = {}
                    for group, positions in positions_by_group.items():
                        best = None
                        for position in positions:
                            p = float(probs[position])
                            if p > 0 and (best is None or p > best[0]):
                                best = (p, position)
                        if best is not None:
                            chosen[group] = best
                    any_best = None
                    for position, market in enumerate(MARKETS):
                        if position in excluded_positions:
                            continue
                        p = float(probs[position])
                        if p <= 0 or p > 0.80:
                            continue
                        if any_best is None or p > any_best[0]:
                            any_best = (p, position)
                    if any_best is not None:
                        chosen[ANY] = any_best

                    hthg = None if np.isnan(test.hthg[row]) else int(test.hthg[row])
                    htag = None if np.isnan(test.htag[row]) else int(test.htag[row])
                    for group, (probability, position) in chosen.items():
                        band = band_of(probability)
                        if band is None:
                            continue
                        market = MARKETS[position]
                        hit = settle(market, int(test.fthg[row]), int(test.ftag[row]), hthg, htag)
                        if hit is None:
                            continue
                        key = (group, band)
                        raw = season_raw[target][key]
                        raw["n"] += 1
                        raw["p"] += probability
                        raw["hits"] += 1 if hit else 0
                        raw["fair"] += 1.0 / probability
                        if factors:
                            factor = factors.get(key, 1.0)
                            shown = min(0.999, max(0.001, probability * factor))
                            cell = season_test[target][key]
                            cell["n"] += 1
                            cell["p"] += shown
                            cell["hits"] += 1 if hit else 0
                            cell["fair"] += 1.0 / shown
                            cell["picks"].append(
                                {"date": round_date.isoformat(), "return": (1.0 / shown - 1.0) if hit else -1.0}
                            )

    live: dict[tuple[str, str], dict] = defaultdict(_bucket)
    for season in season_raw:
        for key, data in season_raw[season].items():
            for field in ("n", "p", "hits", "fair"):
                live[key][field] += data[field]
    live_factors = {
        f"{group}|{band}": round(_clip(data["hits"] / data["p"]), 4)
        for (group, band), data in live.items()
        if data["n"] >= 50 and data["p"] > 0
    }

    pooled: dict[tuple[str, str], dict] = defaultdict(_bucket)
    for season in sorted(season_test):
        for key, data in season_test[season].items():
            for field in ("n", "p", "hits", "fair"):
                pooled[key][field] += data[field]
            pooled[key]["picks"].extend(data["picks"])

    record = []
    for (group, band), data in sorted(pooled.items()):
        if data["n"] < MIN_N:
            continue
        mean, (low, high) = mean_return_ci(data["picks"])
        record.append(
            {
                "group": group,
                "band": band,
                "n": data["n"],
                "shown": round(data["p"] / data["n"], 4),
                "landed": round(data["hits"] / data["n"], 4),
                "return": None if mean is None else round(mean, 4),
                "ci": [None if low is None else round(low, 4), None if high is None else round(high, 4)],
            }
        )

    return {
        "seasons": [f"{year}-{(year + 1) % 100:02d}" for year in SEASONS],
        "groups": GROUPS + [ANY],
        "bands": list(BANDS),
        "factors": live_factors,
        "record": record,
    }


def write(matches_by_division: dict[str, list], half_life: float, path: Path) -> dict:
    payload = run(matches_by_division, half_life)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return payload
