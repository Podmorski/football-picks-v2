"""Counting: hit rates, Wilson 95% intervals, streaks and Top 10s.

A stat is serialised as the compact array ``[n, hits, rate, lo, hi]`` with
rate and interval bounds rounded to four decimals (null when n == 0).
"""
from __future__ import annotations

import math
from collections import defaultdict

from .config import season_start_year
from .outcomes import Outcome, evaluate
from .parse import Match, tuesday_or_saturday

# Two-sided 95% normal quantile.
Z95 = 1.959963984540054

WEEKDAY_BUCKETS = ("tue", "sat", "other")
MIN_TOP_N = 5
TOP_LIMIT = 10


def wilson_interval(hits: int, n: int, z: float = Z95) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return None, None
    p = hits / n
    denominator = 1 + (z * z) / n
    centre = (p + (z * z) / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + (z * z) / (4 * n * n)) / denominator
    lo = max(0.0, centre - margin)
    hi = min(1.0, centre + margin)
    # Remove floating-point dust at the boundaries (0/1 are exact results).
    return (0.0 if lo <= 1e-12 else lo, 1.0 if 1.0 - hi <= 1e-12 else hi)


def summary(hits: int, n: int, z: float = Z95) -> list:
    """[n, hits, rate, lo, hi] — the on-disk stat format."""
    if n <= 0:
        return [0, 0, None, None, None]
    lo, hi = wilson_interval(hits, n, z)
    return [n, hits, round(hits / n, 4), round(lo, 4), round(hi, 4)]


def current_streak(results_newest_first: list[bool]) -> int:
    """Consecutive hits counting back from the most recent match."""
    streak = 0
    for hit in results_newest_first:
        if not hit:
            break
        streak += 1
    return streak


def _results(matches_newest_first: list[Match], outcome: Outcome) -> list[bool]:
    results: list[bool] = []
    for match in matches_newest_first:
        hit = evaluate(outcome, match)
        if hit is None:
            continue
        results.append(hit)
    return results


def _stat(results: list[bool]) -> list:
    return summary(sum(1 for hit in results if hit), len(results))


def _sorted_newest_first(matches: list[Match]) -> list[Match]:
    return sorted(matches, key=lambda m: (m.date, m.home, m.away), reverse=True)


def league_counts(matches: list[Match], outcomes: list[Outcome]) -> dict:
    """Pooled, per-season and per-weekday tallies for every outcome."""
    seasons = sorted({match.season for match in matches}, key=season_start_year)

    pooled: dict[str, list] = {}
    by_season: dict[str, dict[str, list]] = {season: {} for season in seasons}
    by_weekday: dict[str, dict[str, list]] = {bucket: {} for bucket in WEEKDAY_BUCKETS}

    for outcome in outcomes:
        totals = [0, 0]
        season_counts = {season: [0, 0] for season in seasons}
        weekday_counts = {bucket: [0, 0] for bucket in WEEKDAY_BUCKETS}

        for match in matches:
            hit = evaluate(outcome, match)
            if hit is None:
                continue
            totals[0] += 1
            totals[1] += hit
            season_counts[match.season][0] += 1
            season_counts[match.season][1] += hit
            bucket = tuesday_or_saturday(match)
            weekday_counts[bucket][0] += 1
            weekday_counts[bucket][1] += hit

        pooled[outcome.id] = summary(totals[1], totals[0])
        for season in seasons:
            n, hits = season_counts[season]
            by_season[season][outcome.id] = summary(hits, n)
        for bucket in WEEKDAY_BUCKETS:
            n, hits = weekday_counts[bucket]
            by_weekday[bucket][outcome.id] = summary(hits, n)

    return {"pooled": pooled, "by_season": by_season, "by_weekday": by_weekday}


TEAM_SCOPES = (
    "overall",
    "home",
    "away",
    "last6",
    "last10",
    "home_last6",
    "home_last10",
    "away_last6",
    "away_last10",
)


def teams_index(matches: list[Match]) -> dict[str, dict[str, list[Match]]]:
    """Split matches per team into newest-first lists by venue."""
    home: dict[str, list[Match]] = defaultdict(list)
    away: dict[str, list[Match]] = defaultdict(list)
    for match in matches:
        home[match.home].append(match)
        away[match.away].append(match)

    index: dict[str, dict[str, list[Match]]] = {}
    for team in sorted(set(home) | set(away)):
        index[team] = {
            "home": _sorted_newest_first(home.get(team, [])),
            "away": _sorted_newest_first(away.get(team, [])),
            "overall": _sorted_newest_first(home.get(team, []) + away.get(team, [])),
        }
    return index


def team_counts(
    matches: list[Match],
    outcomes: list[Outcome],
    focus_season: str | None,
    previous_season: str | None,
) -> dict[str, dict]:
    """Per-team stats: focus season (all scopes + streak) and previous season (core scopes)."""
    index = teams_index(matches)
    teams: dict[str, dict] = {}

    for team, venues in index.items():
        current = {
            key: [match for match in venue_matches if match.season == focus_season]
            for key, venue_matches in venues.items()
        }
        previous = {
            key: [match for match in venue_matches if match.season == previous_season]
            for key, venue_matches in venues.items()
        }

        stats: dict[str, dict] = {
            "current": {scope: {} for scope in TEAM_SCOPES},
            "previous": {scope: {} for scope in ("overall", "home", "away")},
            "streak": {},
        }

        for outcome in outcomes:
            for scope in ("overall", "home", "away"):
                stats["previous"][scope][outcome.id] = _stat(_results(previous[scope], outcome))

            overall = _results(current["overall"], outcome)
            home_results = _results(current["home"], outcome)
            away_results = _results(current["away"], outcome)

            # Rolling across season boundaries: last 6/10 and the streak follow the team's
            # most recent matches regardless of which season they fell in.
            overall_rolling = _results(venues["overall"], outcome)
            home_rolling = _results(venues["home"], outcome)
            away_rolling = _results(venues["away"], outcome)

            stats["current"]["overall"][outcome.id] = _stat(overall)
            stats["current"]["home"][outcome.id] = _stat(home_results)
            stats["current"]["away"][outcome.id] = _stat(away_results)
            stats["current"]["last6"][outcome.id] = _stat(overall_rolling[:6])
            stats["current"]["last10"][outcome.id] = _stat(overall_rolling[:10])
            stats["current"]["home_last6"][outcome.id] = _stat(home_rolling[:6])
            stats["current"]["home_last10"][outcome.id] = _stat(home_rolling[:10])
            stats["current"]["away_last6"][outcome.id] = _stat(away_rolling[:6])
            stats["current"]["away_last10"][outcome.id] = _stat(away_rolling[:10])
            stats["streak"][outcome.id] = current_streak(overall_rolling)

        teams[team] = stats

    return teams


def top_ten(
    teams: dict[str, dict],
    outcomes: list[Outcome],
    min_n: int = MIN_TOP_N,
    limit: int = TOP_LIMIT,
) -> dict[str, dict[str, list[dict]]]:
    """Per outcome: teams ranked by Wilson lower bound for home, away and last-10."""
    result: dict[str, dict[str, list[dict]]] = {}
    for outcome in outcomes:
        entry: dict[str, list[dict]] = {}
        for scope in ("home", "away", "last10"):
            rows: list[dict] = []
            for team, stats in teams.items():
                stat = stats["current"].get(scope, {}).get(outcome.id)
                if not stat or stat[0] < min_n:
                    continue
                rows.append(
                    {
                        "team": team,
                        "n": stat[0],
                        "hits": stat[1],
                        "rate": stat[2],
                        "lo": stat[3],
                        "hi": stat[4],
                    }
                )
            rows.sort(key=lambda row: (-row["lo"], -row["rate"], -row["n"], row["team"]))
            entry[scope] = rows[:limit]
        result[outcome.id] = entry
    return result
