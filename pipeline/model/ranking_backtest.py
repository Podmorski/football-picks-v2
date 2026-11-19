"""Ranking backtest with walk-forward calibration and a favourite check.

A round is predicted from components fitted only on matches before that round date.
For each target season the shown percentage is scaled by a factor fitted on earlier
seasons' picks (mean landed / mean predicted) per strategy x group x price range;
picks whose calibrated fair odds leave the range are dropped, exactly as the
dashboard filters on the calibrated value.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import numpy as np

from ..counts import wilson_interval
from ..markets import MARKETS, MARKET_BY_ID, market_mask, settle
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
FAVOURITE_THRESHOLD = 0.60
CALIBRATION_CLIP = (0.60, 1.15)


def season_start(match) -> int:
    return int(str(match.season).split("-")[0])


def _band_of(fair: float) -> str | None:
    for key, low, high in BANDS:
        if low <= fair < high:
            return key
    return None


HOME_BACKING = ("RESULT:1", "DOUBLE_CHANCE:1X", "HALF_RESULT:I1", "SECOND_HALF_RESULT:II1",
                "HALF_DC:I1X", "SECOND_HALF_DC:II1X", "WIN_BOTH_HALVES:DP 1", "WIN_TO_NIL:SP 1",
                "MARGIN:HP 1", "MARGIN:HH 1 3+", "RESULT_AND_GOALS:1&2+", "RESULT_AND_GOALS:1&3+",
                "RESULT_AND_GOALS:1&0-2", "DC_AND_GOALS:1X&0-2", "DC_AND_GOALS:1X&2+", "DC_AND_GOALS:1X&3+")
AWAY_BACKING = ("RESULT:2", "DOUBLE_CHANCE:X2", "HALF_RESULT:I2", "SECOND_HALF_RESULT:II2",
                "HALF_DC:IX2", "SECOND_HALF_DC:IIX2", "WIN_BOTH_HALVES:DP 2", "WIN_TO_NIL:SP 2",
                "MARGIN:HP 2", "MARGIN:HH 2 3+", "RESULT_AND_GOALS:2&2+", "RESULT_AND_GOALS:2&3+",
                "DC_AND_GOALS:X2&0-2", "DC_AND_GOALS:X2&2+")


def backs_team(market_id: str) -> str | None:
    """'home' / 'away' when the bet is a bet on that team, else None."""
    if market_id in HOME_BACKING:
        return "home"
    if market_id in AWAY_BACKING:
        return "away"
    if market_id.startswith("TEAM_GOALS:I1") or market_id.startswith("TEAM_GOALS_HALF:I1"):
        return "home"
    if market_id.startswith("TEAM_GOALS:I2") or market_id.startswith("TEAM_GOALS_HALF:I2"):
        return "away"
    if market_id.startswith("HTFT:1-") or market_id.startswith("HTFT:X-1"):
        return "home"
    if market_id.startswith("HTFT:2-") or market_id.startswith("HTFT:X-2"):
        return "away"
    return None


def _bucket() -> dict:
    return {"p": 0.0, "n": 0, "hits": 0}


def _rows(buckets: dict, calibrated: bool) -> list[dict]:
    out = []
    for (strategy, group, band), data in sorted(buckets.items()):
        if data["n"] < 30:
            continue
        hits = data["hits"]
        low, high = wilson_interval(hits, data["n"])
        out.append(
            {
                "strategy": strategy,
                "group": group,
                "band": band,
                "calibrated": calibrated,
                "picks": data["n"],
                "mean_probability": round(data["p"] / data["n"], 4),
                "hits": hits,
                "hit_rate": round(hits / data["n"], 4),
                "ci": [round(low, 4), round(high, 4)],
            }
        )
    return out


def run(matches_by_division: dict[str, list], half_life: float, k: float) -> dict:
    raw: dict[tuple[str, str, str], dict] = defaultdict(_bucket)
    calibrated: dict[tuple[str, str, str], dict] = defaultdict(_bucket)
    season_raw: dict[int, dict[tuple[str, str, str], dict]] = defaultdict(lambda: defaultdict(_bucket))
    team_bets: dict[tuple[str, str], int] = defaultdict(int)
    team_favs: dict[tuple[str, str], int] = defaultdict(int)
    mask = market_mask()
    home_win_index = next(i for i, m in enumerate(MARKETS) if m.id == "RESULT:1")

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

            # Walk-forward calibration from earlier seasons only.
            factors: dict[tuple[str, str, str], float] = {}
            prior: dict[tuple[str, str, str], dict] = defaultdict(_bucket)
            for earlier in sorted(season_raw):
                if earlier >= target:
                    break
                for key, data in season_raw[earlier].items():
                    prior[key]["p"] += data["p"]
                    prior[key]["n"] += data["n"]
                    prior[key]["hits"] += data["hits"]
            for key, data in prior.items():
                if data["n"] >= 50 and data["p"] > 0:
                    ratio = data["hits"] / data["p"]
                    factors[key] = float(min(max(ratio, CALIBRATION_CLIP[0]), CALIBRATION_CLIP[1]))

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
                home_lambda, away_lambda = goals.anchored_lambdas(test.home, test.away, test.odds, use_odds=True)
                per_band: dict[str, list[tuple]] = defaultdict(list)
                home_wins = np.zeros(len(test_index))

                for row in range(len(test_index)):
                    lh = float(home_lambda[row])
                    la = float(away_lambda[row])
                    joint = joint_vector(
                        lh * goals.share_home, la * goals.share_away,
                        lh * (1 - goals.share_home), la * (1 - goals.share_away), goals.rho,
                    )
                    probs = joint @ mask
                    home_wins[row] = float(probs[home_win_index])
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
                            usable = [c for c in candidates if c[2] >= LEAN_MIN_LEAGUE_N and c[1] >= LEAN_MIN_RATIO]
                            usable.sort(key=lambda c: (-c[1], -c[0]))
                        else:
                            usable = sorted(candidates, key=lambda c: -c[0])

                        seen: set[int] = set()
                        taken = 0
                        for probability, _lean, _ln, position, row in usable:
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
                            raw[key]["p"] += probability
                            raw[key]["n"] += 1
                            raw[key]["hits"] += 1 if hit else 0
                            season_raw[target][(strategy, market.group, band)]["p"] += probability
                            season_raw[target][(strategy, market.group, band)]["n"] += 1
                            season_raw[target][(strategy, market.group, band)]["hits"] += 1 if hit else 0

                            factor = factors.get(key, 1.0)
                            shown = min(0.999, max(0.001, probability * factor))
                            if _band_of(1.0 / shown) != band:
                                continue

                            calibrated[key]["p"] += shown
                            calibrated[key]["n"] += 1
                            calibrated[key]["hits"] += 1 if hit else 0

                            backing = backs_team(market.id)
                            if backing is not None:
                                team_bets[(strategy, band)] += 1
                                favourite = home_wins[row] if backing == "home" else 1.0 - home_wins[row]
                                if favourite >= FAVOURITE_THRESHOLD:
                                    team_favs[(strategy, band)] += 1

                            taken += 1
                            if taken >= TOP_N:
                                break

    favourites = []
    for (strategy, band), bets in sorted(team_bets.items()):
        favourites.append(
            {
                "strategy": strategy,
                "band": band,
                "team_bets": bets,
                "favourite_bets": team_favs[(strategy, band)],
                "share": round(team_favs[(strategy, band)] / bets, 4) if bets else None,
            }
        )

    final: dict[tuple[str, str, str], dict] = defaultdict(_bucket)
    for season in sorted(season_raw):
        for key, data in season_raw[season].items():
            final[key]["p"] += data["p"]
            final[key]["n"] += data["n"]
            final[key]["hits"] += data["hits"]
    calibration = {
        "|".join(key): round(float(min(max(d["hits"] / d["p"], CALIBRATION_CLIP[0]), CALIBRATION_CLIP[1])), 4)
        for key, d in final.items()
        if d["n"] >= 50 and d["p"] > 0
    }

    return {
        "seasons": [f"{year}-{(year + 1) % 100:02d}" for year in SEASONS],
        "bands": [band[0] for band in BANDS],
        "strategies": list(STRATEGIES),
        "groups": _rows(calibrated, True),
        "before": _rows(raw, False),
        "calibration": calibration,
        "favourites": favourites,
    }
