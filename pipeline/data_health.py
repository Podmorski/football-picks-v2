"""Data health for unsettled indexed rounds: pending, sources, fallback, retry.

Aggregate only. Football-data provenance comes from the current run; fallback
diagnostics come from the cached API-Football attempt. No raw payloads or
prices are written here.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import api_football, ranking

SCHEMA_VERSION = 1

# update.yml cron slots (UTC). Weekday: 0=Monday.
SCHEDULE = {
    0: (6, 12), 1: (10, 14, 16), 2: (6, 12), 4: (15, 18, 21), 5: (5, 8), 6: (5, 8, 12, 18),
}
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _round_document(picks_dir: Path, date: str) -> dict:
    full = picks_dir / f"{date}.full.json"
    return ranking.load(full if full.exists() else picks_dir / f"{date}.json")


def next_scheduled_retry(now: dt.datetime) -> str:
    """The next update.yml slot after ``now`` (UTC), as a stable label."""
    cursor = now.replace(second=0, microsecond=0)
    for offset in range(0, 8):
        day = (cursor + dt.timedelta(days=offset)).date()
        for hour in SCHEDULE.get(day.weekday(), ()):
            slot = dt.datetime.combine(day, dt.time(hour), tzinfo=dt.timezone.utc)
            if slot > cursor:
                return f"{WEEKDAYS[day.weekday()]} {hour:02d}:00 UTC"
    return "next scheduled update"


def _fixture_sources(
    rows: list[dict], date: str, football_keys: set[tuple], fallback_keys: set[tuple],
) -> dict:
    fixtures = {(row["d"], row["h"], row["a"]) for row in rows}
    counts = {
        "football_data_fixtures": 0, "api_football_fixtures": 0, "unknown_fixtures": 0,
        "football_data_rows": 0, "api_football_rows": 0, "unknown_rows": 0,
    }
    for div, home, away in fixtures:
        key = (date, home, away)
        if key in football_keys:
            counts["football_data_fixtures"] += 1
        elif key in fallback_keys:
            counts["api_football_fixtures"] += 1
        else:
            counts["unknown_fixtures"] += 1
    for row in rows:
        key = (date, row["h"], row["a"])
        if key in football_keys:
            counts["football_data_rows"] += 1
        elif key in fallback_keys:
            counts["api_football_rows"] += 1
        else:
            counts["unknown_rows"] += 1
    return counts


def build(
    picks_dir: Path, *, today: dt.date, latest_football_data: str | None,
    football_keys: set[tuple], fallback_keys: set[tuple],
    now: dt.datetime | None = None,
) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    rounds = []
    for path in sorted(picks_dir.glob("*.json")):
        if path.name.endswith(".full.json"):
            continue
        date = path.name[:-5]
        document = _round_document(picks_dir, date)
        rows = document.get("rows", [])
        fixtures = {(row["d"], row["h"], row["a"]) for row in rows}
        settled_fixtures = {
            (row["d"], row["h"], row["a"]) for row in rows
            if row.get("st") in ("landed", "lost", "void")
        }
        pending_rows = [row for row in rows if row.get("st") in (None, "pending")]
        pending_fixtures = {(row["d"], row["h"], row["a"]) for row in pending_rows}
        sources = _fixture_sources(rows, date, football_keys, fallback_keys)

        cache = api_football.load_cache(dt.date.fromisoformat(date))
        fallback = {"attempted": cache is not None}
        if cache is not None:
            _results, diagnostics = api_football.match_events(cache.get("events", []), sorted(fixtures))
            fallback.update({
                "fetched_at": cache.get("fetched_at"), "requests": cache.get("requests"),
                "final_count": cache.get("final_count"), **diagnostics,
            })
        else:
            fallback.update({
                "reason": "no cached next-day attempt (outside the fallback window or not requested)",
                "ambiguous": 0, "unmatched": len(pending_fixtures),
            })

        source_pending = sorted(
            home + " v " + away for _div, home, away in pending_fixtures
            if (date, home, away) not in football_keys and (date, home, away) not in fallback_keys
        )
        rounds.append({
            "date": date,
            "label": document.get("label", date),
            "kind": document.get("kind", "round"),
            "fixtures": len(fixtures),
            "settled_fixtures": len(settled_fixtures),
            "pending_fixtures": len(pending_fixtures),
            "rows": {
                "total": len(rows),
                "settled": len(rows) - len(pending_rows),
                "pending": len(pending_rows),
            },
            "sources": sources,
            "fallback": fallback,
            "pending_reasons": {
                "source_pending_fixtures": len(source_pending),
                "ambiguous_fixtures": int(fallback.get("ambiguous", 0) or 0),
                "unmatched_fixtures": int(fallback.get("unmatched", 0) or 0),
                "source_pending_sample": source_pending[:3],
            },
            "next_retry": next_scheduled_retry(now),
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "latest_football_data_result_date": latest_football_data,
        "unsettled_rounds": [row for row in rounds if row["pending_fixtures"] > 0],
    }


def write(picks_dir: Path, web_dir: Path, **kwargs) -> dict:
    payload = build(picks_dir, **kwargs)
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "data-health.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return payload
