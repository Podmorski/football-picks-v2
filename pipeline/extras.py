"""Parser for the "extra" league files (football-data.co.uk/new/{CODE}.csv).

These files carry full-time goals only (no half-time scores) and closing odds only.
Closing odds are never read, so an extra league has no odds input at all: the model
falls back to the unanchored goals engine and HT-based outcomes are never offered.

One file can hold more than one competition (Argentina ships two); we keep the
competition with the most rows and record which one that was.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from .parse import Match, normalise, parse_date, parse_int, read_text

FIRST_SEASON_YEAR = 2015


def season_label(raw: str) -> tuple[str, int] | None:
    """'2015/2016' -> ('2015-16', 2015); '2015' -> ('2015', 2015)."""
    text = normalise(raw)
    if not text:
        return None
    head = text.split("/")[0].strip()
    if not head[:4].isdigit():
        return None
    start = int(head[:4])
    if "/" in text:
        tail = text.split("/")[1].strip()[:4]
        end = int(tail) if tail.isdigit() else start + 1
        return f"{start}-{end % 100:02d}", start
    return f"{start}", start


@dataclass(slots=True)
class ExtraResult:
    matches: list[Match]
    league_name: str
    rows_total: int
    rows_invalid: int
    seasons: list[str]


def parse_extra_csv(path: Path | str, season_filter: bool = True) -> ExtraResult:
    text = read_text(path)
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    if not rows:
        return ExtraResult([], "", 0, 0, [])

    header = [normalise(cell).lstrip("\ufeff") for cell in rows[0]]
    index = {name: position for position, name in enumerate(header) if name}
    required = ("Date", "Home", "Away", "HG", "AG")
    missing = [name for name in required if name not in index]
    if missing:
        raise ValueError(f"{path}: missing columns {missing} in {header}")

    def cell(row: list[str], name: str) -> str:
        position = index.get(name)
        if position is None or position >= len(row):
            return ""
        return row[position]

    league_counts: dict[str, int] = {}
    parsed_rows: list[tuple[int, list[str]]] = []
    for row in rows[1:]:
        league = normalise(cell(row, "League"))
        if league:
            league_counts[league] = league_counts.get(league, 0) + 1
        parsed_rows.append((len(parsed_rows), row))

    dominant = max(league_counts, key=league_counts.get) if league_counts else ""

    matches: list[Match] = []
    invalid = 0
    seasons: set[str] = set()
    for _, row in parsed_rows:
        if normalise(cell(row, "League")) != dominant:
            continue
        labelled = season_label(cell(row, "Season"))
        date = parse_date(cell(row, "Date"))
        home = normalise(cell(row, "Home"))
        away = normalise(cell(row, "Away"))
        fthg = parse_int(cell(row, "HG"))
        ftag = parse_int(cell(row, "AG"))
        if labelled is None or date is None or not home or not away or fthg is None or ftag is None:
            invalid += 1
            continue
        label, start = labelled
        if season_filter and start < FIRST_SEASON_YEAR:
            continue
        seasons.add(label)
        matches.append(
            Match(
                season=label,
                date=date,
                home=home,
                away=away,
                fthg=fthg,
                ftag=ftag,
                hthg=None,
                htag=None,
                time=normalise(cell(row, "Time")) or None,
                odds={},  # closing-only columns: never read
            )
        )

    return ExtraResult(
        matches=matches,
        league_name=dominant,
        rows_total=sum(1 for _ in parsed_rows),
        rows_invalid=invalid,
        seasons=sorted(seasons, key=lambda label: int(label.split("-")[0])),
    )
