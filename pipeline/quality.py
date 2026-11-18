"""Data-quality measurement for the downloaded archive."""
from __future__ import annotations

from collections import Counter

from .parse import Match, ParseResult


def duplicate_fixtures(matches: list[Match]) -> int:
    """Extra occurrences of the same (date, home, away) fixture."""
    counts = Counter((match.date, match.home, match.away) for match in matches)
    return sum(count - 1 for count in counts.values() if count > 1)


def season_quality(result: ParseResult, status: int = 200) -> dict:
    matches = result.matches
    teams = {match.home for match in matches} | {match.away for match in matches}
    dates = [match.date for match in matches]
    return {
        "season": result.season,
        "status": status,
        "rows": len(matches),
        "rows_in_file": result.rows_total,
        "rows_invalid": result.rows_invalid,
        "ht_missing": result.ht_missing,
        "duplicates": duplicate_fixtures(matches),
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
        "teams": len(teams),
        "missing_odds": False,
    }


def missing_season(season: str, status: int) -> dict:
    return {
        "season": season,
        "status": status,
        "rows": 0,
        "rows_in_file": 0,
        "rows_invalid": 0,
        "ht_missing": 0,
        "duplicates": 0,
        "date_min": None,
        "date_max": None,
        "teams": 0,
        "missing_odds": True,
    }


def totals(seasons: dict[int, dict]) -> dict:
    total_rows = sum(item["rows"] for item in seasons.values())
    total_ht_missing = sum(item["ht_missing"] for item in seasons.values())
    total_duplicates = sum(item["duplicates"] for item in seasons.values())
    return {
        "rows": total_rows,
        "ht_missing": total_ht_missing,
        "duplicates": total_duplicates,
    }
