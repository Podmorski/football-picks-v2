"""fixtures.csv parsing and round selection (Tuesday / Saturday / Sunday)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from .parse import ODDS_COLUMNS, normalise, parse_date, parse_float, read_text

TUESDAY = 1
FRIDAY = 4
SATURDAY = 5
SUNDAY = 6
MONDAY = 0
ROUND_WEEKDAYS = (TUESDAY, SATURDAY, SUNDAY)


@dataclass(slots=True)
class Fixture:
    div: str
    date: dt.date
    time: str | None
    home: str
    away: str
    odds: dict[str, float]


def parse_fixtures(path: Path | str) -> list[Fixture]:
    text = read_text(path)
    rows = [row for row in text.splitlines() if row.strip()]
    if not rows:
        return []

    header = [normalise(cell) for cell in rows[0].split(",")]
    index = {name: position for position, name in enumerate(header) if name}
    odds_positions = {name: index[name] for name in ODDS_COLUMNS if name in index}

    fixtures: list[Fixture] = []
    for row in rows[1:]:
        cells = row.split(",")
        if len(cells) < 5:
            continue

        def cell(name: str) -> str:
            position = index.get(name)
            if position is None or position >= len(cells):
                return ""
            return cells[position]

        date = parse_date(cell("Date"))
        home = normalise(cell("HomeTeam"))
        away = normalise(cell("AwayTeam"))
        if date is None or not home or not away:
            continue

        odds: dict[str, float] = {}
        for name, position in odds_positions.items():
            if position < len(cells):
                value = parse_float(cells[position])
                if value is not None:
                    odds[name] = value

        fixtures.append(
            Fixture(
                div=normalise(cell("Div")),
                date=date,
                time=normalise(cell("Time")) or None,
                home=home,
                away=away,
                odds=odds,
            )
        )
    return fixtures


def next_round_date(today: dt.date) -> dt.date:
    """Earliest Tuesday, Saturday or Sunday strictly after today (UK date)."""
    for offset in range(1, 8):
        candidate = today + dt.timedelta(days=offset)
        if candidate.weekday() in ROUND_WEEKDAYS:
            return candidate
    raise ValueError("no round day found within a week")


def current_or_next_round_date(today: dt.date) -> dt.date:
    """Today when today is a round day (so retries can publish it), else the next one."""
    if today.weekday() in ROUND_WEEKDAYS:
        return today
    return next_round_date(today)


def round_dates_for(today: dt.date) -> list[dt.date]:
    """The rounds a run should handle, in priority order.

    Friday publishes BOTH weekend rounds; Saturday retries both; Sunday only
    touches Sunday; Tuesday only Tuesday; Monday settles the weekend. Friday
    itself is never a round day.
    """
    weekday = today.weekday()
    if weekday == FRIDAY:
        saturday = today + dt.timedelta(days=1)
        return [saturday, saturday + dt.timedelta(days=1)]
    if weekday == SATURDAY:
        return [today, today + dt.timedelta(days=1)]
    if weekday == SUNDAY:
        return [today]
    if weekday == TUESDAY:
        return [today]
    if weekday == MONDAY:
        return [today - dt.timedelta(days=2), today - dt.timedelta(days=1)]
    return [current_or_next_round_date(today)]


def last_saturday(today: dt.date) -> dt.date:
    """Most recent Saturday strictly before today."""
    candidate = today - dt.timedelta(days=(today.weekday() - SATURDAY) % 7)
    if candidate >= today:
        candidate -= dt.timedelta(days=7)
    return candidate


def fixtures_for_date(fixtures: list[Fixture], date: dt.date, divisions: set[str] | None = None) -> list[Fixture]:
    selected = [fixture for fixture in fixtures if fixture.date == date]
    if divisions is None:
        return selected
    return [fixture for fixture in selected if fixture.div in divisions]


WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
