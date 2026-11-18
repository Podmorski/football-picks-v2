"""Picker backtest: replay every Tuesday and Saturday round and score both views.

A round's picks depend only on matches strictly before the round date; the arrays
passed in may contain later matches, but nothing after the cutoff is fitted or read.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import numpy as np

from ..counts import wilson_interval
from ..outcomes import OUTCOMES_BY_ID
from ..picks import DEFAULT_CONFIG, finalise, select_views
from . import blend as blend_module
from .counts_engine import fit as fit_counts
from .data import EPOCH, MatchArrays, build_arrays, day_number, subset
from .goals_engine import fit as fit_goals

SEASONS = tuple(range(2019, 2026))
ROUND_WEEKDAYS = (1, 5)
MIN_TRAINING_MATCHES = 200
VIEW_NAMES = ("most_likely", "stand_out")


def season_start(match) -> int:
    return int(str(match.season).split("-")[0])


def live_components(decisions: dict) -> tuple[dict[str, str], list[str]]:
    """Per-group component for the live model, degrading a stacked blend to its odds input."""
    live: dict[str, str] = {}
    degraded: list[str] = []
    for group, entry in decisions.get("groups", {}).items():
        component = entry.get("live_component") or "odds"
        if component == "full":
            degraded.append(group)
            component = "odds"
        live[group] = component
    return live, degraded


def picks_for_round(
    matches: list,
    round_date: dt.date,
    half_life: float,
    k: float,
    settings: dict | None = None,
    live: dict[str, str] | None = None,
    calibration: dict | None = None,
    arrays: MatchArrays | None = None,
    division: str = "",
) -> dict[str, list[dict]]:
    """Both views for one round date. Only matches before the date are used."""
    settings = {**DEFAULT_CONFIG, **(settings or {})}
    ordered = sorted(matches, key=lambda match: (match.date, match.home, match.away))
    pool = arrays if arrays is not None else build_arrays(ordered)

    day = day_number(round_date)
    train_index = np.where(pool.dates < day)[0]
    test_index = np.where(pool.dates == day)[0]
    if len(train_index) < MIN_TRAINING_MATCHES or len(test_index) == 0:
        return {"most_likely": [], "stand_out": []}

    train = subset(pool, train_index)
    test = subset(pool, test_index)
    counts = fit_counts(train, day, half_life, k)
    goals = fit_goals(train, day, half_life)

    live_map = {group: (live or {}).get(group, "odds") for group in blend_module.GROUP_NAMES}
    needs_goals = any(component == "goals" for component in live_map.values())
    odds_p = goals.probabilities(test.home, test.away, test.odds, use_odds=True)
    counts_p = counts.probabilities(test.home, test.away)
    goals_p = goals.probabilities(test.home, test.away, test.odds, use_odds=False) if needs_goals else odds_p
    base = np.repeat(counts.league_rates()[None, :], len(test_index), axis=0)
    full = blend_module.Blend(stack={}, platt={}, live=live_map).apply(base, counts_p, goals_p, odds_p)

    rows = [
        {
            "div": division,
            "league": division,
            "kickoff": ordered[int(position)].time,
            "home": ordered[int(position)].home,
            "away": ordered[int(position)].away,
            "home_index": int(test.home[offset]),
            "away_index": int(test.away[offset]),
            "no_odds": not ordered[int(position)].odds,
            "match": ordered[int(position)],
        }
        for offset, position in enumerate(test_index)
    ]

    selected = select_views(
        rows,
        {
            "full": full,
            "counts": counts_p,
            "odds": odds_p,
            "n_home": counts.n_home[test.home],
            "n_away": counts.n_away[test.away],
        },
        counts,
        calibration,
        settings,
    )

    by_match = {(row["home"], row["away"]): row for row in rows}
    output: dict[str, list[dict]] = {}
    for view_name in VIEW_NAMES:
        sort_key = "probability" if view_name == "most_likely" else "lift"
        picks = finalise(selected[view_name], sort_key, settings)
        kept = []
        for pick in picks:
            match = by_match[(pick["home"], pick["away"])]["match"]
            outcome = OUTCOMES_BY_ID[pick["outcome"]]
            if outcome.needs_ht and not match.has_ht:
                continue
            pick["landed"] = bool(outcome.fn(match.fthg, match.ftag, match.hthg, match.htag))
            pick["settled"] = True
            pick["result"] = f"{match.fthg}-{match.ftag}"
            kept.append(pick)
        output[view_name] = kept
    return output


def _summarise(picks: list[dict], rounds: int) -> dict:
    count = len(picks)
    hits = sum(1 for pick in picks if pick.get("landed"))
    if count == 0:
        return {
            "rounds": rounds,
            "picks": 0,
            "mean_probability": None,
            "hits": 0,
            "hit_rate": None,
            "ci": [None, None],
            "by_play": [],
            "by_league": [],
            "no_odds_picks": 0,
        }

    low, high = wilson_interval(hits, count)
    by_play: dict[str, list] = defaultdict(list)
    by_league: dict[str, list] = defaultdict(list)
    for pick in picks:
        by_play[pick["outcome"]].append(pick)
        by_league[pick["league"]].append(pick)

    def rows(groups: dict[str, list], limit: int | None = None) -> list[dict]:
        output = []
        for name, group in groups.items():
            hit_count = sum(1 for pick in group if pick.get("landed"))
            lo, hi = wilson_interval(hit_count, len(group))
            output.append(
                {
                    "name": name,
                    "label": group[0]["play"],
                    "picks": len(group),
                    "mean_probability": round(float(np.mean([pick["probability"] for pick in group])), 4),
                    "hits": hit_count,
                    "hit_rate": round(hit_count / len(group), 4),
                    "ci": [round(lo, 4), round(hi, 4)],
                }
            )
        output.sort(key=lambda row: (-row["picks"], row["name"]))
        return output[:limit] if limit else output

    return {
        "rounds": rounds,
        "picks": count,
        "mean_probability": round(float(np.mean([pick["probability"] for pick in picks])), 4),
        "hits": hits,
        "hit_rate": round(hits / count, 4),
        "ci": [round(low, 4), round(high, 4)],
        "by_play": rows(by_play),
        "by_league": rows(by_league, 10),
        "no_odds_picks": sum(1 for pick in picks if pick.get("no_odds")),
    }


def run(
    matches_by_division: dict[str, list],
    decisions: dict,
    half_life: float,
    k: float,
    config: dict | None = None,
    calibration: dict | None = None,
) -> dict:
    settings = {**DEFAULT_CONFIG, **(config or {})}
    live, degraded = live_components(decisions)
    needs_goals = any(component == "goals" for component in live.values())

    collected: dict[str, list[dict]] = {name: [] for name in VIEW_NAMES}
    round_dates: dict[str, set] = {name: set() for name in VIEW_NAMES}

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
                if (arrays.dates < day).sum() < MIN_TRAINING_MATCHES:
                    continue
                for view_name, picks in picks_for_round(
                    ordered,
                    round_date,
                    half_life,
                    k,
                    settings=settings,
                    live=live,
                    calibration=calibration,
                    arrays=arrays,
                    division=code,
                ).items():
                    if picks:
                        collected[view_name].extend(picks)
                        round_dates[view_name].add(round_date.isoformat())

    return {
        "seasons": [f"{year}-{(year + 1) % 100:02d}" for year in SEASONS],
        "weekdays": ["Tuesday", "Saturday"],
        "degraded_groups": degraded,
        "views": {name: _summarise(collected[name], len(round_dates[name])) for name in VIEW_NAMES},
    }
