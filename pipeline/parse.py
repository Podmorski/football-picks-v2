"""Parsing of football-data.co.uk season CSVs into match records.

The archive is messy across seasons: dates appear as dd/mm/yy and dd/mm/yyyy,
columns come and go (Time, the various odds providers), encodings differ and
there are trailing empty rows. Everything here is defensive.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_COLUMNS = ("Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG")
HT_COLUMNS = ("HTHG", "HTAG")

# Kept for later milestones (odds-based work). Missing columns are simply absent.
ODDS_COLUMNS = (
    "PSH", "PSD", "PSA",
    "PSCH", "PSCD", "PSCA",
    "AvgH", "AvgD", "AvgA",
    "BbAvH", "BbAvD", "BbAvA",
    "B365H", "B365D", "B365A",
    "P>2.5", "P<2.5",
    "PC>2.5", "PC<2.5",
    "Avg>2.5", "Avg<2.5",
    "BbAv>2.5", "BbAv<2.5",
    "B365>2.5", "B365<2.5",
)

_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_SLASH_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")
_DASH_DATE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")

TUESDAY = 1
SATURDAY = 5


class MissingColumns(ValueError):
    """A season file does not carry the columns we must have."""

    def __init__(self, path: Path | str, missing: list[str], available: list[str]):
        self.path = str(path)
        self.missing = list(missing)
        self.available = list(available)
        super().__init__(f"{path}: missing columns {self.missing}")


@dataclass(frozen=True, slots=True)
class Match:
    season: str
    date: dt.date
    home: str
    away: str
    fthg: int
    ftag: int
    hthg: int | None
    htag: int | None
    time: str | None = None
    odds: dict[str, float] = field(default_factory=dict)

    @property
    def weekday(self) -> int:
        return self.date.weekday()

    @property
    def total_goals(self) -> int:
        return self.fthg + self.ftag

    @property
    def ht_goals(self) -> int | None:
        if self.hthg is None or self.htag is None:
            return None
        return self.hthg + self.htag

    @property
    def has_ht(self) -> bool:
        return self.hthg is not None and self.htag is not None


@dataclass(slots=True)
class ParseResult:
    matches: list[Match]
    season: str
    rows_total: int
    rows_invalid: int
    columns: list[str]

    @property
    def ht_missing(self) -> int:
        return sum(1 for match in self.matches if not match.has_ht)


def read_text(path: Path | str) -> str:
    """Decode the file, trying the encodings the archive actually uses."""
    data = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def normalise(text: str | None) -> str:
    if text is None:
        return ""
    return " ".join(str(text).replace("\ufeff", "").split())


def parse_date(value: str | None) -> dt.date | None:
    """dd/mm/yy, dd/mm/yyyy, (rarely) ISO. Two-digit years are 20xx."""
    text = normalise(value)
    if not text:
        return None

    iso = _ISO_DATE.match(text)
    if iso:
        try:
            return dt.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    slashed = _SLASH_DATE.match(text)
    if slashed:
        day, month, year_text = slashed.groups()
        year = int(year_text) if len(year_text) == 4 else 2000 + int(year_text)
        try:
            return dt.date(year, int(month), int(day))
        except ValueError:
            return None

    dashed = _DASH_DATE.match(text)
    if dashed:
        day, month, year_text = dashed.groups()
        try:
            return dt.date(int(year_text), int(month), int(day))
        except ValueError:
            return None

    return None


def parse_int(value: str | None) -> int | None:
    text = normalise(value)
    if not text or text in {"-", "N/A", "NA"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_float(value: str | None) -> float | None:
    text = normalise(value)
    if not text or text in {"-", "N/A", "NA"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _iter_rows(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text))
    rows: list[list[str]] = []
    for row in reader:
        # Drop trailing empty cells; a row with nothing left is a blank line.
        while row and not normalise(row[-1]):
            row.pop()
        if row and any(normalise(cell) for cell in row):
            rows.append(row)
    return rows


def parse_season_csv(path: Path | str, season: str) -> ParseResult:
    """Parse one division-season file. Raises MissingColumns on schema problems."""
    text = read_text(path)
    rows = _iter_rows(text)
    if not rows:
        raise MissingColumns(path, list(REQUIRED_COLUMNS), [])

    header = [normalise(cell) for cell in rows[0]]
    index = {name: position for position, name in enumerate(header) if name}

    missing = [name for name in REQUIRED_COLUMNS if name not in index]
    if missing:
        raise MissingColumns(path, missing, [h for h in header if h])
    missing_ht = [name for name in HT_COLUMNS if name not in index]
    if missing_ht:
        raise MissingColumns(path, missing_ht, [h for h in header if h])

    def cell(row: list[str], name: str) -> str:
        position = index.get(name)
        if position is None or position >= len(row):
            return ""
        return row[position]

    odds_positions = {name: index[name] for name in ODDS_COLUMNS if name in index}

    matches: list[Match] = []
    rows_total = 0
    rows_invalid = 0
    for row in rows[1:]:
        rows_total += 1
        date = parse_date(cell(row, "Date"))
        home = normalise(cell(row, "HomeTeam"))
        away = normalise(cell(row, "AwayTeam"))
        fthg = parse_int(cell(row, "FTHG"))
        ftag = parse_int(cell(row, "FTAG"))
        if date is None or not home or not away or fthg is None or ftag is None:
            rows_invalid += 1
            continue

        odds: dict[str, float] = {}
        for name, position in odds_positions.items():
            if position < len(row):
                value = parse_float(row[position])
                if value is not None:
                    odds[name] = value

        matches.append(
            Match(
                season=season,
                date=date,
                home=home,
                away=away,
                fthg=fthg,
                ftag=ftag,
                hthg=parse_int(cell(row, "HTHG")),
                htag=parse_int(cell(row, "HTAG")),
                time=normalise(cell(row, "Time")) or None,
                odds=odds,
            )
        )

    return ParseResult(
        matches=matches,
        season=season,
        rows_total=rows_total,
        rows_invalid=rows_invalid,
        columns=[h for h in header if h],
    )


def tuesday_or_saturday(match: Match) -> str:
    """Coarse weekday bucket used for the Tue/Sat splits."""
    if match.weekday == TUESDAY:
        return "tue"
    if match.weekday == SATURDAY:
        return "sat"
    return "other"
