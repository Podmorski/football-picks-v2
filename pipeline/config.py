"""Configuration: paths, download policy and the league registry."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent
RAW_DIR = ROOT_DIR / "data" / "raw"
WEB_DATA_DIR = ROOT_DIR / "web" / "public" / "data"
LEAGUES_FILE = PACKAGE_DIR / "leagues.yaml"

BASE_URL = "https://football-data.co.uk"
USER_AGENT = "football-picks-v2 (+https://github.com/Podmorski/football-picks-v2)"

# First season held in the archive (2015-16).
FIRST_SEASON_START = 2015

# football-data.co.uk asks for polite use; never go below one second between requests.
REQUEST_INTERVAL_SECONDS = 1.05

REQUIRED_DIVISION_KEYS = ("code", "name", "country", "tier")


@dataclass(frozen=True, slots=True)
class League:
    code: str
    name: str
    country: str
    tier: int
    ft_only: bool = False

    @property
    def has_odds(self) -> bool:
        return not self.ft_only


def season_label(start_year: int) -> str:
    """2015 -> '2015-16'."""
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def season_code(start_year: int) -> str:
    """2015 -> '1516' (the {YYZZ} segment of the archive URL)."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def season_start_year(label: str) -> int:
    """'2015-16' -> 2015."""
    return int(str(label).split("-")[0])


def season_csv_url(code: str, division: str) -> str:
    return f"{BASE_URL}/mmz4281/{code}/{division}.csv"


def fixtures_url() -> str:
    return f"{BASE_URL}/fixtures.csv"


def extra_url(code: str) -> str:
    return f"{BASE_URL}/new/{code}.csv"


def _read_yaml(path: Path | None = None) -> dict:
    source = path or LEAGUES_FILE
    with source.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_divisions(path: Path | None = None) -> list[League]:
    source = path or LEAGUES_FILE
    document = _read_yaml(source)

    entries = document.get("divisions")
    if not entries:
        raise ValueError(f"no divisions defined in {source}")

    leagues: list[League] = []
    seen: set[str] = set()
    for entry in entries:
        missing = [key for key in REQUIRED_DIVISION_KEYS if key not in entry]
        if missing:
            raise ValueError(f"division entry {entry!r} is missing {missing}")
        code = str(entry["code"]).strip()
        if code in seen:
            raise ValueError(f"duplicate division code {code!r} in {source}")
        seen.add(code)
        leagues.append(
            League(
                code=code,
                name=str(entry["name"]).strip(),
                country=str(entry["country"]).strip(),
                tier=int(entry["tier"]),
            )
        )
    return leagues


def load_extras(path: Path | None = None) -> list[League]:
    """Extra leagues: one file each, full-time scores only, no pre-match odds."""
    source = path or LEAGUES_FILE
    document = _read_yaml(source)
    entries = document.get("extras") or []

    leagues: list[League] = []
    seen: set[str] = set()
    for entry in entries:
        missing = [key for key in ("code", "name", "country") if key not in entry]
        if missing:
            raise ValueError(f"extra entry {entry!r} is missing {missing}")
        code = str(entry["code"]).strip()
        if code in seen:
            raise ValueError(f"duplicate extra code {code!r} in {source}")
        seen.add(code)
        leagues.append(
            League(
                code=code,
                name=str(entry["name"]).strip(),
                country=str(entry["country"]).strip(),
                tier=1,
                ft_only=True,
            )
        )
    return leagues


def load_leagues(path: Path | None = None) -> list[League]:
    """Every league, main archive first, extras second."""
    divisions = load_divisions(path)
    extras = load_extras(path)
    codes = {league.code for league in divisions} & {league.code for league in extras}
    if codes:
        raise ValueError(f"codes defined as both division and extra: {sorted(codes)}")
    return divisions + extras
