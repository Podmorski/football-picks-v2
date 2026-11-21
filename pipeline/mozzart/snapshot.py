"""Build the per-round price snapshot from the global feed and v2 fixtures."""
from __future__ import annotations

import datetime as dt

from . import mapping, teams
from .client import parse_kickoff

MAX_KICKOFF_HOURS = teams.MAX_KICKOFF_HOURS
MIN_LEAD_MINUTES = 20.0


def fixtures_from_round(document: dict) -> list[dict]:
    """Unique fixtures from either the compact (fixture_list) or decoded form."""
    if document.get("fixture_list"):
        return [
            {"d": row["d"], "k": row.get("k"), "h": row["h"], "a": row["a"]}
            for row in document["fixture_list"]
        ]
    out: dict[tuple, dict] = {}
    for row in document.get("picks", []):
        key = (row.get("d"), row.get("k"), row.get("h"), row.get("a"))
        out[key] = {"d": key[0], "k": key[1], "h": key[2], "a": key[3]}
    return list(out.values())


def _fixture_kickoff(round_date: dt.date, time_text: str | None) -> dt.datetime | None:
    if not time_text:
        return None
    try:
        hour, minute = (int(part) for part in str(time_text).split(":")[:2])
    except (TypeError, ValueError):
        return None
    return dt.datetime.combine(round_date, dt.time(hour, minute), tzinfo=dt.timezone.utc)


def _within_hours(left: dt.datetime | None, right: dt.datetime | None) -> bool:
    if left is None or right is None:
        return True
    return abs((left - right).total_seconds()) <= MAX_KICKOFF_HOURS * 3600


def match_event(event: dict, fixtures: list[dict], round_date: dt.date) -> tuple[dict | None, float]:
    """Best v2 fixture for a Mozzart event, by team similarity and kick-off."""
    kickoff = parse_kickoff(event)
    best, score = None, 0.0
    for fixture in fixtures:
        if not _within_hours(kickoff, _fixture_kickoff(round_date, fixture.get("k"))):
            continue
        home = teams.similarity(event.get("home", ""), fixture["h"])
        away = teams.similarity(event.get("away", ""), fixture["a"])
        if home < teams.MATCH_SIMILARITY or away < teams.MATCH_SIMILARITY:
            continue
        combined = (home + away) / 2
        if combined > score:
            best, score = fixture, combined
    return best, score


def event_prices(event: dict) -> dict[str, float]:
    """Every v2 market id this event prices, with the active odds."""
    prices: dict[str, float] = {}
    for market in event.get("markets", []) or []:
        section = market.get("rawName", "")
        period = market.get("period", "")
        for selection in market.get("selections", []) or []:
            if not selection.get("isActive", True):
                continue
            odds = selection.get("odds")
            if not isinstance(odds, (int, float)) or odds <= 1.0:
                continue
            market_id = mapping.resolve(section, period, selection.get("rawName", ""))
            if market_id is None:
                continue
            prices.setdefault(market_id, float(odds))
    return prices


def best_event(fixture: dict, events: list[dict]) -> dict | None:
    """Nearest Mozzart event by team-name similarity, for the unmatched report."""
    best, score = None, -1.0
    for event in events:
        value = teams.similarity(event.get("home", ""), fixture["h"]) + teams.similarity(event.get("away", ""), fixture["a"])
        if value > score:
            best, score = event, value
    return best


def build(
    round_date: dt.date, fixtures: list[dict], events: list[dict], fetched_at: dt.datetime,
    min_lead_minutes: float = MIN_LEAD_MINUTES,
) -> dict:
    """Join the feed to the round's fixtures and emit the snapshot document.

    Fixtures kicking off within ``min_lead_minutes`` of the fetch are marked
    started and not priced, so a late run never shows stale pre-match prices.
    """
    start_cutoff = fetched_at + dt.timedelta(minutes=min_lead_minutes)
    eligible: list[dict] = []
    started: list[dict] = []
    for fixture in fixtures:
        kickoff = _fixture_kickoff(round_date, fixture.get("k"))
        if kickoff is not None and kickoff <= start_cutoff:
            started.append(
                {"div": fixture["d"], "home": fixture["h"], "away": fixture["a"], "kickoff": kickoff.isoformat()}
            )
        else:
            eligible.append(fixture)

    by_division: dict[str, list[dict]] = {}
    for fixture in eligible:
        by_division.setdefault(fixture["d"], []).append(fixture)

    events_by_division: dict[str, list[dict]] = {}
    for event in events:
        division = teams.LEAGUE_LABELS.get(event.get("league", ""))
        if division is not None:
            events_by_division.setdefault(division, []).append(event)

    priced: dict[tuple, dict] = {}
    for event in events:
        division = teams.LEAGUE_LABELS.get(event.get("league", ""))
        if division is None or division not in by_division:
            continue
        fixture, score = match_event(event, by_division[division], round_date)
        if fixture is None:
            continue
        prices = event_prices(event)
        key = (fixture["d"], fixture["h"], fixture["a"])
        if not prices:
            continue
        kickoff = parse_kickoff(event)
        priced[key] = {
            "div": fixture["d"],
            "home": fixture["h"],
            "away": fixture["a"],
            "kickoff": kickoff.isoformat() if kickoff else fixture.get("k"),
            "prices": prices,
            "match_similarity": round(score, 3),
        }

    unmatched = []
    for fixture in eligible:
        key = (fixture["d"], fixture["h"], fixture["a"])
        if key in priced:
            continue
        row = {"div": fixture["d"], "home": fixture["h"], "away": fixture["a"], "kickoff": fixture.get("k")}
        candidate = best_event(fixture, events_by_division.get(fixture["d"], []))
        if candidate is not None:
            row["mozzart_home"] = candidate.get("home")
            row["mozzart_away"] = candidate.get("away")
        unmatched.append(row)

    return {
        "round_date": round_date.isoformat(),
        "fetched_at": fetched_at.astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
        "fixtures": sorted(priced.values(), key=lambda row: (row["div"], row["home"], row["away"])),
        "unmatched_fixtures": unmatched,
        "started_not_priced": sorted(started, key=lambda row: (row["kickoff"], row["div"], row["home"])),
    }
