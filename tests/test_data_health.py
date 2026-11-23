"""Data health: pending fixtures, source provenance, fallback diagnostics, retry."""
from __future__ import annotations

import datetime as dt
import json

from pipeline import api_football, data_health, ranking


def row(home: str, away: str, status: str = "pending", market: str = "BTTS:GG") -> dict:
    return {
        "d": "E0", "k": "15:00", "h": home, "a": away, "m": market,
        "p": 0.6, "pc": 0.6, "pl": 0.6, "pp": 0.6, "lr": 0.5, "ln": 100,
        "hr": 0.5, "hn": 10, "ar": 0.5, "an": 10, "c": "Medium", "s": 0.1,
        "st": status, "ht": "1-0" if status != "pending" else None, "ft": "2-1" if status != "pending" else None,
    }


def write_round(picks, date: str, rows: list[dict]) -> None:
    document = {
        "date": date, "label": date, "weekday": "Sunday", "kind": "round",
        "fixtures": len({(item["d"], item["h"], item["a"]) for item in rows}), "rows": rows,
    }
    ranking.publish(document, picks, picks)


def test_pending_sources_and_fallback_diagnostics(tmp_path, monkeypatch) -> None:
    picks = tmp_path / "picks"
    picks.mkdir()
    write_round(picks, "2026-11-22", [
        row("Arsenal", "Chelsea", "landed"), row("Everton", "Fulham", "lost"), row("Liverpool", "Man City", "pending"),
    ])
    monkeypatch.setattr(api_football, "CACHE_DIR", tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    cache = {
        "date": "2026-11-22", "fetched_at": "2026-11-23T06:00:00+00:00", "requests": 1,
        "final_count": 1, "events": [
            {"div": "E0", "home": "Arsenal", "away": "Chelsea", "ht": [1, 0], "ft": [2, 1], "status": "FT"},
        ],
    }
    (tmp_path / "cache" / "2026-11-22.json").write_text(json.dumps(cache), encoding="utf-8")
    payload = data_health.build(
        picks, today=dt.date(2026, 11, 23), latest_football_data="2026-11-22",
        football_keys={("2026-11-22", "Everton", "Fulham")}, fallback_keys={("2026-11-22", "Arsenal", "Chelsea")},
        now=dt.datetime(2026, 11, 23, 6, 30, tzinfo=dt.timezone.utc),
    )
    round_row = payload["unsettled_rounds"][0]
    assert round_row["fixtures"] == 3 and round_row["pending_fixtures"] == 1
    assert round_row["sources"] == {
        "football_data_fixtures": 1, "api_football_fixtures": 1, "unknown_fixtures": 1,
        "football_data_rows": 1, "api_football_rows": 1, "unknown_rows": 1,
    }
    assert round_row["fallback"] == {
        "attempted": True, "fetched_at": "2026-11-23T06:00:00+00:00", "requests": 1,
        "final_count": 1, "fixtures": 3, "events": 1, "matched": 1, "ambiguous": 0, "unmatched": 2,
    }
    assert round_row["pending_reasons"]["source_pending_fixtures"] == 1
    assert round_row["next_retry"] == "Mon 12:00 UTC"


def test_no_cache_reports_an_honest_unattempted_state(tmp_path, monkeypatch) -> None:
    picks = tmp_path / "picks"
    picks.mkdir()
    write_round(picks, "2026-11-21", [row("A", "B")])
    monkeypatch.setattr(api_football, "CACHE_DIR", tmp_path / "cache")
    payload = data_health.build(
        picks, today=dt.date(2026, 11, 23), latest_football_data="2026-11-16",
        football_keys=set(), fallback_keys=set(),
        now=dt.datetime(2026, 11, 23, 6, 30, tzinfo=dt.timezone.utc),
    )
    fallback = payload["unsettled_rounds"][0]["fallback"]
    assert fallback["attempted"] is False
    assert "outside the fallback window" in fallback["reason"]
    assert payload["latest_football_data_result_date"] == "2026-11-16"


def test_next_scheduled_retry_skips_thursday() -> None:
    thursday = dt.datetime(2026, 11, 26, 12, 0, tzinfo=dt.timezone.utc)
    assert data_health.next_scheduled_retry(thursday) == "Fri 15:00 UTC"
    sunday = dt.datetime(2026, 11, 22, 19, 0, tzinfo=dt.timezone.utc)
    assert data_health.next_scheduled_retry(sunday) == "Mon 06:00 UTC"
