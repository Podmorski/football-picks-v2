"""Next-day API-Football result fallback.

football-data.co.uk stays authoritative. This module only fills a missing
eligible past result on the next day (Saturday->Sunday, Sunday->Monday,
Tuesday->Wednesday), from provider-final 90-minute fixtures with both HT and FT
scores. Matching is exact after the evidenced alias table; there is no fuzzy
threshold. Responses are cached as normalized fixtures (never raw provider
payloads), and at most five requests per UTC day are made, pagination included.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import ranking
from .api_football_probe import BASE_URL, division_for, load_api_key
from .config import RAW_DIR
from .mozzart.teams import similarity

DAILY_REQUEST_CAP = 5
CACHE_DIR = RAW_DIR / "api_football"
USAGE_FILE = RAW_DIR / "api_football_usage.json"
FINAL_STATUS = "FT"
ROUND_WEEKDAYS = {1, 5, 6}  # Tuesday, Saturday, Sunday


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")


def usage_for(day: dt.date) -> int:
    return int(_read_json(USAGE_FILE).get(day.isoformat(), 0))


def record_usage(day: dt.date, requests: int) -> int:
    usage = _read_json(USAGE_FILE)
    total = int(usage.get(day.isoformat(), 0)) + int(requests)
    usage[day.isoformat()] = total
    _write_json(USAGE_FILE, usage)
    return total


def cache_path(date: dt.date) -> Path:
    return CACHE_DIR / f"{date.isoformat()}.json"


def load_cache(date: dt.date) -> dict | None:
    payload = _read_json(cache_path(date))
    return payload or None


def eligible_fallback_date(today: dt.date) -> dt.date | None:
    """Yesterday's round when today is its next-day window, else None."""
    yesterday = today - dt.timedelta(days=1)
    if today.weekday() not in (6, 0, 2):  # Sunday, Monday, Wednesday
        return None
    if yesterday.weekday() not in ROUND_WEEKDAYS:
        return None
    return yesterday


def _event_row(event: dict) -> dict | None:
    fixture = event.get("fixture") or {}
    status = str((fixture.get("status") or {}).get("short", ""))
    if status != FINAL_STATUS:
        return None
    league = event.get("league") or {}
    div = division_for(league)
    if div is None:
        return None
    score = event.get("score") or {}
    half = score.get("halftime") or {}
    full = score.get("fulltime") or {}
    if None in (half.get("home"), half.get("away"), full.get("home"), full.get("away")):
        return None
    teams = event.get("teams") or {}
    home = str((teams.get("home") or {}).get("name", ""))
    away = str((teams.get("away") or {}).get("name", ""))
    if not home or not away:
        return None
    return {
        "div": div,
        "home": home,
        "away": away,
        "ht": [int(half["home"]), int(half["away"])],
        "ft": [int(full["home"]), int(full["away"])],
        "status": status,
    }


def _request_page(date: dt.date, page: int, key: str, transport):
    url = f"{BASE_URL}/fixtures"
    params: dict[str, str | int] = {"date": date.isoformat()}
    if page > 1:
        params["page"] = page
    headers = {
        "x-apisports-key": key,
        "User-Agent": "football-picks-v2 fallback (+https://github.com/Podmorski/football-picks-v2)",
    }
    if transport is not None:
        status, response_headers, data = transport(url, params, headers)
    else:
        request = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers=headers)
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
    return status, response_headers, data


def fetch_date(
    date: dt.date, *, key: str, today: dt.date | None = None, transport=None, force: bool = False,
) -> dict:
    """Fetch and cache one date. A cache with finals is never re-fetched."""
    cached = load_cache(date)
    if cached and int(cached.get("final_count", 0)) > 0 and not force:
        return {**cached, "cached": True, "requests": 0}
    today = today or dt.date.today()
    remaining = DAILY_REQUEST_CAP - usage_for(today)
    if remaining <= 0:
        return {"cached": False, "requests": 0, "error": "daily request cap reached"}

    pages = []
    events = []
    errors = []
    requests = 0
    page = 1
    total = 1
    while page <= total and requests < remaining:
        status, headers, data = _request_page(date, page, key, transport)
        requests += 1
        page_errors = data.get("errors") if isinstance(data, dict) else None
        paging = (data.get("paging") if isinstance(data, dict) else None) or {}
        pages.append({"page": page, "status": status, "paging": paging,
                      "quota": {name: headers.get(name) for name in (
                          "x-ratelimit-requests-limit", "x-ratelimit-requests-remaining") if headers.get(name) is not None},
                      "errors": page_errors})
        if page_errors:
            errors.append(page_errors)
        if status != 200 or page_errors:
            break
        for event in (data.get("response") or []):
            row = _event_row(event)
            if row is not None:
                events.append(row)
        total = int(paging.get("total", 1) or 1)
        page += 1

    used_today = record_usage(today, requests)
    payload = {
        "date": date.isoformat(),
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "requests": requests,
        "usage_today": used_today,
        "pages": pages,
        "errors": errors,
        "final_count": len(events),
        "events": events,
    }
    if status == 200 and not errors:
        _write_json(cache_path(date), payload)
    return {"cached": False, **payload}


def _round_fixtures(picks_dir: Path, date: dt.date) -> list[tuple[str, str, str]]:
    for name in (f"{date.isoformat()}.full.json", f"{date.isoformat()}.json"):
        path = picks_dir / name
        if path.exists():
            document = ranking.load(path)
            return sorted({(row["d"], row["h"], row["a"]) for row in document.get("rows", [])})
    return []


def match_events(events: list[dict], fixtures: list[tuple[str, str, str]]) -> tuple[dict, dict]:
    """Conservative exact/verified-alias matching; ambiguous fixtures are skipped."""
    by_fixture: dict[tuple[str, str, str], list[int]] = {fixture: [] for fixture in fixtures}
    event_fixtures: dict[int, list[tuple[str, str, str]]] = {}
    for index, event in enumerate(events):
        matched = [
            fixture for fixture in fixtures
            if fixture[0] == event["div"]
            and similarity(fixture[1], event["home"]) == 1.0
            and similarity(fixture[2], event["away"]) == 1.0
        ]
        event_fixtures[index] = matched
        for fixture in matched:
            by_fixture[fixture].append(index)

    results: dict[tuple[str, str, str], tuple[int, int, int, int]] = {}
    ambiguous = 0
    unmatched = 0
    for fixture, indices in by_fixture.items():
        if len(indices) == 1 and len(event_fixtures[indices[0]]) == 1:
            event = events[indices[0]]
            results[fixture] = (event["ft"][0], event["ft"][1], event["ht"][0], event["ht"][1])
        elif len(indices) > 1 or (len(indices) == 1 and len(event_fixtures[indices[0]]) > 1):
            ambiguous += 1
        else:
            unmatched += 1
    return results, {
        "fixtures": len(fixtures), "events": len(events), "matched": len(results),
        "ambiguous": ambiguous, "unmatched": unmatched,
    }


def cached_fallback(picks_dir: Path, today: dt.date) -> dict:
    """Results for yesterday's round only, with football-data-independent provenance."""
    date = eligible_fallback_date(today)
    if date is None:
        return {"date": None, "results": {}, "diagnostics": {"reason": "not a next-day fallback window"}}
    cache = load_cache(date)
    fixtures = _round_fixtures(picks_dir, date)
    if not cache or not fixtures:
        return {"date": date.isoformat(), "results": {}, "diagnostics": {"reason": "no cache or no round fixtures"}}
    results, diagnostics = match_events(cache.get("events", []), fixtures)
    return {
        "date": date.isoformat(),
        "results": {(date.isoformat(), home, away): score for (div, home, away), score in results.items()},
        "diagnostics": diagnostics,
        "usage": cache.get("requests"), "final_count": cache.get("final_count"),
    }


def merge_results(football_data: dict, fallback: dict) -> dict:
    """football-data always wins; fallback only fills missing keys."""
    merged = dict(fallback)
    merged.update(football_data)
    return merged


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="ensure", choices=("ensure", "fetch"))
    parser.add_argument("--date", help="explicit date for a diagnostic fetch")
    parser.add_argument("--today", help="override today's UTC date")
    args = parser.parse_args(argv)

    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()
    if args.date:
        date = dt.date.fromisoformat(args.date)
    else:
        date = eligible_fallback_date(today)
    if date is None:
        print("api-football: no next-day fallback window; zero requests made")
        return 0
    if not (Path(__file__).resolve().parents[1] / "picks" / f"{date.isoformat()}.json").exists():
        print(f"api-football: no round file for {date.isoformat()}; zero requests made")
        return 0
    key = load_api_key()
    if not key:
        print("api-football: API_FOOTBALL_KEY is not configured; zero requests made")
        return 0
    result = fetch_date(date, key=key, today=today)
    summary = {name: result.get(name) for name in (
        "cached", "date", "requests", "usage_today", "final_count", "errors", "pages")}
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
