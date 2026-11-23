"""One-off, hard-capped API-Football results diagnostic.

Never used by production settlement. At most four GET requests total. Raw
responses are processed in memory only; output is aggregate diagnostics.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .config import RAW_DIR
from .fixtures import parse_fixtures
from .mozzart.teams import similarity

BASE_URL = "https://v3.football.api-sports.io"
MAX_REQUESTS = 4
DATES = ("2026-11-21", "2026-11-22")
V1_ENV = Path("/home/nikola/code/Work/Betting/.env")

DIVISION_NAMES = {
    "E0": ("premier league", "england"),
    "E1": ("championship", "england"),
    "E2": ("league one", "england"),
    "E3": ("league two", "england"),
    "EC": ("national league", "england"),
    "SC0": ("premiership", "scotland"),
    "SC1": ("championship", "scotland"),
    "SC2": ("league one", "scotland"),
    "SC3": ("league two", "scotland"),
    "D1": ("bundesliga", "germany"),
    "D2": ("2. bundesliga", "germany"),
    "I1": ("serie a", "italy"),
    "I2": ("serie b", "italy"),
    "SP1": ("la liga", "spain"),
    "SP2": ("segunda division", "spain"),
    "F1": ("ligue 1", "france"),
    "F2": ("ligue 2", "france"),
    "N1": ("eredivisie", "netherlands"),
    "B1": ("jupiler pro league", "belgium"),
    "P1": ("primeira liga", "portugal"),
    "T1": ("super lig", "turkey"),
    "G1": ("super league", "greece"),
}


def _key(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def load_api_key() -> str | None:
    key = os.environ.get("API_FOOTBALL_KEY")
    if key and key.strip():
        return key.strip()
    if V1_ENV.exists():
        for line in V1_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("API_FOOTBALL_KEY="):
                value = line.split("=", 1)[1].strip()
                return value or None
    return None


@dataclass(slots=True)
class ProbeLimit(RuntimeError):
    limit: int = MAX_REQUESTS

    def __str__(self) -> str:
        return f"API-Football probe request cap {self.limit} reached"


@dataclass(slots=True)
class Probe:
    key: str
    transport: Callable[[str, dict, dict], tuple[int, dict, dict]] | None = None
    calls: int = 0
    pages: list[dict] = field(default_factory=list)

    def fetch_page(self, date: str, page: int) -> dict:
        if self.calls >= MAX_REQUESTS:
            raise ProbeLimit()
        self.calls += 1
        url = f"{BASE_URL}/fixtures"
        params: dict[str, str | int] = {"date": date}
        if page > 1:
            params["page"] = page
        headers = {
            "x-apisports-key": self.key,
            "User-Agent": "football-picks-v2 diagnostic (github.com/Podmorski/football-picks-v2)",
        }
        if self.transport is not None:
            status, response_headers, data = self.transport(url, params, headers)
        else:
            full_url = f"{url}?{urllib.parse.urlencode(params)}"
            request = urllib.request.Request(full_url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    status, response_headers = response.status, dict(response.headers)
                    body = response.read()
            except urllib.error.HTTPError as exc:
                status, response_headers = exc.code, dict(exc.headers)
                body = exc.read()
            try:
                data = json.loads(body.decode("utf-8", errors="replace"))
            except (ValueError, AttributeError):
                data = {}
        page_info = {
            "date": date, "page": page, "status": status,
            "quota": {name: response_headers.get(name) for name in (
                "x-ratelimit-requests-limit", "x-ratelimit-requests-remaining",
                "X-RateLimit-Limit", "X-RateLimit-Remaining",
            ) if response_headers.get(name) is not None},
            "errors": data.get("errors") if isinstance(data, dict) else None,
            "paging": (data.get("paging") if isinstance(data, dict) else None) or {},
            "events": (data.get("response") if isinstance(data, dict) else None) or [],
        }
        self.pages.append(page_info)
        return page_info

    def fetch_date(self, date: str) -> list[dict]:
        first = self.fetch_page(date, 1)
        events = list(first["events"])
        total = int(first["paging"].get("total", 1) or 1)
        if total > 1 and self.calls < MAX_REQUESTS:
            second = self.fetch_page(date, 2)
            events.extend(second["events"])
        return events


def division_for(league: dict) -> str | None:
    name = _key(league.get("name", ""))
    country = _key(league.get("country", ""))
    for code, (wanted_name, wanted_country) in DIVISION_NAMES.items():
        if name == wanted_name and country == wanted_country:
            return code
    return None


def _event_row(event: dict) -> dict:
    fixture = event.get("fixture") or {}
    teams = event.get("teams") or {}
    score = event.get("score") or {}
    return {
        "date": str(fixture.get("date", ""))[:10],
        "status": str((fixture.get("status") or {}).get("short", "")),
        "home": str((teams.get("home") or {}).get("name", "")),
        "away": str((teams.get("away") or {}).get("name", "")),
        "div": division_for(event.get("league") or {}),
        "ht": (score.get("halftime") or {}).get("home") is not None and (score.get("halftime") or {}).get("away") is not None,
        "ft": (score.get("fulltime") or {}).get("home") is not None and (score.get("fulltime") or {}).get("away") is not None,
    }


def summarise(pages: list[dict], events: list[dict]) -> dict:
    rows = [_event_row(event) for event in events]
    final = [row for row in rows if row["status"] in ("FT", "AET", "PEN") and row["ft"]]
    fixtures_path = RAW_DIR / "fixtures.csv"
    v2_all = parse_fixtures(fixtures_path) if fixtures_path.exists() else []
    v2_fixtures = [
        fixture for fixture in v2_all
        if fixture.date.isoformat() in DATES and fixture.div in DIVISION_NAMES
    ]
    by_date_div = {code: 0 for code in DIVISION_NAMES}
    with_ht = 0
    for row in final:
        with_ht += int(row["ht"])
        if row["div"]:
            by_date_div[row["div"]] += 1

    pairs = []
    for fixture in v2_fixtures:
        for event in rows:
            if event["date"] != fixture.date.isoformat():
                continue
            if event["div"] != fixture.div:
                continue
            home_score = similarity(fixture.home, event["home"])
            away_score = similarity(fixture.away, event["away"])
            if min(home_score, away_score) >= 0.86:
                exact = _key(fixture.home) == _key(event["home"]) and _key(fixture.away) == _key(event["away"])
                pairs.append((min(home_score, away_score), exact, id(fixture), id(event), fixture, event))
    pairs.sort(key=lambda item: item[0], reverse=True)
    used_fixtures, used_events = set(), set()
    exact = alias = ambiguous = 0
    for _score, is_exact, fixture_id, event_id, _fixture, _event in pairs:
        if fixture_id in used_fixtures:
            continue
        if event_id in used_events:
            ambiguous += 1
            continue
        used_fixtures.add(fixture_id)
        used_events.add(event_id)
        exact += int(is_exact)
        alias += int(not is_exact)
    status_errors = [page["errors"] for page in pages if page["errors"]]
    return {
        "requests": len(pages),
        "pages": [{key: page[key] for key in ("date", "page", "status", "quota", "errors", "paging")} for page in pages],
        "provider_error_responses": status_errors,
        "events_returned": len(rows),
        "final_with_ft": len(final),
        "final_with_ht_and_ft": with_ht,
        "coverage_by_v2_division": {code: count for code, count in by_date_div.items() if count},
        "v2_fixtures": len(v2_fixtures),
        "exact_matches": exact,
        "alias_matches": alias,
        "ambiguous_matches": ambiguous,
        "unmatched": len(v2_fixtures) - exact - alias,
        "licensing_note": "Current API-Football licensing could not be verified because its documentation returned HTTP 403.",
        "settlement_activated": False,
    }


def run(probe: Probe, dates: tuple[str, ...] = DATES) -> dict:
    events = []
    for date in dates:
        if probe.calls >= MAX_REQUESTS:
            break
        events.extend(probe.fetch_date(date))
    return summarise(probe.pages, events)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    args = parser.parse_args(argv)
    if args.max_requests > MAX_REQUESTS:
        print(f"Refusing more than {MAX_REQUESTS} requests")
        return 2
    key = load_api_key()
    if not key:
        print("API_FOOTBALL_KEY is required for this diagnostic; zero requests made.")
        return 2
    result = run(Probe(key=key))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
