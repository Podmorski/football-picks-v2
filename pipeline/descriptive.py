"""Deterministic descriptive match statistics from existing HT/FT history.

Every calculation is strictly before the fixture date. These values are
historical frequencies, not calibrated probabilities, rankings or filters.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from . import ranking
from .markets import result as score_result
from .parse import Match

SCHEMA_VERSION = 1
DEFINITIONS_VERSION = "descriptive-v1"
WINDOW_SIZES = (6, 12)
H2H_LIMIT = 6
RESULT_CODES = ("1", "X", "2")
HTFT_CODES = tuple(f"{half}-{full}" for half in RESULT_CODES for full in RESULT_CODES)
STREAK_IDS = (
    "win", "unbeaten", "winless", "losing", "drawing",
    "btts", "no_btts", "over25", "under25",
)
NOTE = "Historical frequencies describe past matches; they are not calibrated chances."


def _match_key(match: Match) -> tuple:
    return (
        match.date, match.home, match.away, int(match.fthg), int(match.ftag),
        -1 if match.hthg is None else int(match.hthg),
        -1 if match.htag is None else int(match.htag),
    )


@dataclass(frozen=True, slots=True)
class HistoryIndex:
    by_team: dict[str, tuple[Match, ...]]
    by_pair: dict[tuple[str, str], tuple[Match, ...]]


def build_history(matches: Iterable[Match]) -> HistoryIndex:
    """Index completed matches deterministically; missing FT scores never count."""
    completed = sorted(
        (
            match for match in matches
            if match.fthg is not None and match.ftag is not None
        ),
        key=_match_key,
    )
    by_team: dict[str, list[Match]] = defaultdict(list)
    by_pair: dict[tuple[str, str], list[Match]] = defaultdict(list)
    for match in completed:
        by_team[match.home].append(match)
        if match.away != match.home:
            by_team[match.away].append(match)
        pair = (match.home, match.away) if match.home <= match.away else (match.away, match.home)
        by_pair[pair].append(match)
    return HistoryIndex(
        by_team={team: tuple(rows) for team, rows in by_team.items()},
        by_pair={pair: tuple(rows) for pair, rows in by_pair.items()},
    )


def _before(matches: Sequence[Match], cutoff: dt.date) -> list[Match]:
    return [match for match in matches if match.date < cutoff]


def _rate(count: int, n: int, digits: int = 4) -> float | None:
    return round(count / n, digits) if n else None


def _result_rates(matches: Sequence[Match], half_time: bool) -> dict:
    applicable = [
        match for match in matches
        if not half_time or (match.hthg is not None and match.htag is not None)
    ]
    n = len(applicable)
    counts = {code: 0 for code in RESULT_CODES}
    for match in applicable:
        if half_time:
            assert match.hthg is not None and match.htag is not None
            home_goals, away_goals = match.hthg, match.htag
        else:
            home_goals, away_goals = match.fthg, match.ftag
        counts[score_result(int(home_goals), int(away_goals))] += 1
    return {"n": n, **{code: _rate(counts[code], n) for code in RESULT_CODES}}


def _htft_rates(matches: Sequence[Match]) -> dict:
    applicable = [
        match for match in matches
        if match.hthg is not None and match.htag is not None
    ]
    n = len(applicable)
    counts = {code: 0 for code in HTFT_CODES}
    for match in applicable:
        assert match.hthg is not None and match.htag is not None
        half = score_result(int(match.hthg), int(match.htag))
        full = score_result(int(match.fthg), int(match.ftag))
        counts[f"{half}-{full}"] += 1
    return {"n": n, **{code: _rate(counts[code], n) for code in HTFT_CODES}}


def window_stats(matches: Sequence[Match], team: str) -> dict:
    """W/D/L, goals, points and historical market frequencies for one team."""
    n = len(matches)
    wins = draws = losses = goals_for = goals_against = points = 0
    btts = over25 = 0
    for match in matches:
        at_home = match.home == team
        gf = int(match.fthg if at_home else match.ftag)
        ga = int(match.ftag if at_home else match.fthg)
        goals_for += gf
        goals_against += ga
        if gf > ga:
            wins += 1
            points += 3
        elif gf == ga:
            draws += 1
            points += 1
        else:
            losses += 1
        if gf > 0 and ga > 0:
            btts += 1
        if gf + ga >= 3:
            over25 += 1
    return {
        "n": n,
        "w": wins,
        "d": draws,
        "l": losses,
        "gf": goals_for,
        "ga": goals_against,
        "gf_pm": _rate(goals_for, n),
        "ga_pm": _rate(goals_against, n),
        "points": points,
        "points_pm": _rate(points, n),
        "btts": {"count": btts, "rate": _rate(btts, n)},
        "over25": {"count": over25, "rate": _rate(over25, n)},
        "ft": _result_rates(matches, half_time=False),
        "ht": _result_rates(matches, half_time=True),
        "htft": _htft_rates(matches),
    }


def _team_result(match: Match, team: str) -> str:
    at_home = match.home == team
    gf = int(match.fthg if at_home else match.ftag)
    ga = int(match.ftag if at_home else match.fthg)
    return "W" if gf > ga else "L" if gf < ga else "D"


def _streak(matches: Sequence[Match], team: str, predicate) -> int:
    length = 0
    for match in reversed(matches):
        if not predicate(match, team):
            break
        length += 1
    return length


def compute_streaks(matches: Sequence[Match], team: str) -> dict:
    """Current streak lengths from the most recent completed match backwards."""
    def goals(match: Match) -> tuple[int, int]:
        at_home = match.home == team
        return (
            int(match.fthg if at_home else match.ftag),
            int(match.ftag if at_home else match.fthg),
        )

    return {
        "win": _streak(matches, team, lambda match, _: _team_result(match, team) == "W"),
        "unbeaten": _streak(matches, team, lambda match, _: _team_result(match, team) != "L"),
        "winless": _streak(matches, team, lambda match, _: _team_result(match, team) != "W"),
        "losing": _streak(matches, team, lambda match, _: _team_result(match, team) == "L"),
        "drawing": _streak(matches, team, lambda match, _: _team_result(match, team) == "D"),
        "btts": _streak(matches, team, lambda match, _: goals(match)[0] > 0 and goals(match)[1] > 0),
        "no_btts": _streak(matches, team, lambda match, _: goals(match)[0] == 0 or goals(match)[1] == 0),
        "over25": _streak(matches, team, lambda match, _: sum(goals(match)) >= 3),
        "under25": _streak(matches, team, lambda match, _: sum(goals(match)) <= 2),
    }


def team_block(index: HistoryIndex, team: str, cutoff: dt.date, venue: str) -> dict:
    overall = _before(index.by_team.get(team, ()), cutoff)
    if venue == "home":
        venue_matches = [match for match in overall if match.home == team]
    elif venue == "away":
        venue_matches = [match for match in overall if match.away == team]
    else:
        raise ValueError(f"unknown venue: {venue}")
    windows = {}
    for size in WINDOW_SIZES:
        windows[f"overall{size}"] = window_stats(overall[-size:], team)
        windows[f"venue{size}"] = window_stats(venue_matches[-size:], team)
    return {
        "windows": windows,
        "streaks": {
            "overall": compute_streaks(overall, team),
            "venue": compute_streaks(venue_matches, team),
        },
    }


def head_to_head(index: HistoryIndex, home: str, away: str, cutoff: dt.date, limit: int = H2H_LIMIT) -> dict:
    """Prior loaded main-division league meetings from the current home perspective."""
    pair = (home, away) if home <= away else (away, home)
    meetings = _before(index.by_pair.get(pair, ()), cutoff)
    n = len(meetings)
    wins = draws = losses = goals_for = goals_against = btts = over25 = 0
    for match in meetings:
        at_home = match.home == home
        gf = int(match.fthg if at_home else match.ftag)
        ga = int(match.ftag if at_home else match.fthg)
        goals_for += gf
        goals_against += ga
        if gf > ga:
            wins += 1
        elif gf == ga:
            draws += 1
        else:
            losses += 1
        if gf > 0 and ga > 0:
            btts += 1
        if gf + ga >= 3:
            over25 += 1
    recent = list(reversed(meetings[-limit:]))
    return {
        "n": n,
        "w": wins,
        "d": draws,
        "l": losses,
        "gf": goals_for,
        "ga": goals_against,
        "btts": {"count": btts, "rate": _rate(btts, n)},
        "over25": {"count": over25, "rate": _rate(over25, n)},
        "meetings": [
            {
                "date": match.date.isoformat(),
                "home": match.home,
                "away": match.away,
                "fthg": int(match.fthg),
                "ftag": int(match.ftag),
                "hthg": None if match.hthg is None else int(match.hthg),
                "htag": None if match.htag is None else int(match.htag),
            }
            for match in recent
        ],
    }


def fixture_stats(
    index: HistoryIndex, division: str, home: str, away: str,
    kickoff: str | None, cutoff: dt.date,
) -> dict:
    return {
        "d": division,
        "h": home,
        "a": away,
        "k": kickoff,
        "cutoff": cutoff.isoformat(),
        "home": team_block(index, home, cutoff, "home"),
        "away": team_block(index, away, cutoff, "away"),
        "h2h": head_to_head(index, home, away, cutoff),
    }


def _round_fixtures(document: dict) -> list[dict]:
    fixtures = document.get("fixture_list")
    if fixtures:
        return [
            {"d": fixture["d"], "k": fixture.get("k"), "h": fixture["h"], "a": fixture["a"]}
            for fixture in fixtures
        ]
    seen = set()
    output = []
    for row in document.get("rows", []):
        key = (row["d"], row.get("k"), row["h"], row["a"])
        if key in seen:
            continue
        seen.add(key)
        output.append({"d": row["d"], "k": row.get("k"), "h": row["h"], "a": row["a"]})
    return output


def round_sidecar(document: dict, index: HistoryIndex) -> dict:
    cutoff = dt.date.fromisoformat(document["date"])
    fixtures = [
        fixture_stats(index, fixture["d"], fixture["h"], fixture["a"], fixture["k"], cutoff)
        for fixture in _round_fixtures(document)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "definitions_version": DEFINITIONS_VERSION,
        "round_date": document["date"],
        "cutoff_date": cutoff.isoformat(),
        "note": NOTE,
        "definitions": {
            "windows": [6, 12],
            "cutoff": "completed matches strictly before cutoff_date only",
            "result_codes": "FT/HT 1/X/2 are historical match home/draw/away; W/D/L are the named team's perspective",
            "frequency": "rate = count / applicable n; null when n = 0, never padded",
            "streaks": "most recent completed match backwards; 0 when the latest match does not satisfy",
            "h2h": "prior main-division league meetings only, current home team's W/D/L perspective",
        },
        "fixtures": fixtures,
    }


def sidecar_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def backfill_rounds(picks_dir: Path, matches_by_division: dict[str, list], out_dir: Path) -> list[dict]:
    """Write deterministic sidecars for every indexed round, never touching picks."""
    index = build_history(
        match
        for _code, matches in sorted(matches_by_division.items())
        for match in matches
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    coverage = []
    for path in sorted(picks_dir.glob("*.json")):
        if path.name.endswith(".full.json"):
            continue
        document = ranking.load(path)
        if not document.get("rows"):
            continue
        payload = round_sidecar(document, index)
        text = sidecar_text(payload)
        output = out_dir / f"{document['date']}.json"
        if not output.exists() or output.read_text(encoding="utf-8") != text:
            output.write_text(text, encoding="utf-8")
        coverage.append({"date": document["date"], "fixtures": len(payload["fixtures"])})
    return coverage
