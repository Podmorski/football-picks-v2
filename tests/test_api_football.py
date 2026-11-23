"""Next-day API-Football fallback: cap, cache, conservative matching, merge."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from pipeline import api_football as af
from pipeline import run_model, ranking


def event(home: str, away: str, status: str = "FT", division: str = "Premier League", country: str = "England", ht=(1, 0), ft=(2, 1)) -> dict:
    return {
        "fixture": {"date": "2026-11-22T15:00:00+00:00", "status": {"short": status}},
        "league": {"name": division, "country": country},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "score": {
            "halftime": {"home": ht[0], "away": ht[1]},
            "fulltime": {"home": ft[0], "away": ft[1]},
        },
    }


def setup_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(af, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(af, "USAGE_FILE", tmp_path / "usage.json")
    return tmp_path


def test_first_request_omits_page_and_pagination_respects_daily_cap(monkeypatch, tmp_path):
    setup_storage(monkeypatch, tmp_path)
    calls = []

    def transport(url, params, headers):
        calls.append(dict(params))
        page = params.get("page", 1)
        return 200, {}, {"paging": {"current": page, "total": 9}, "response": [], "errors": []}

    result = af.fetch_date(dt.date(2026, 11, 22), key="not-printed", today=dt.date(2026, 11, 23), transport=transport)
    assert "page" not in calls[0]
    assert [params.get("page", 1) for params in calls] == [1, 2, 3, 4, 5]
    assert result["requests"] == 5
    assert af.usage_for(dt.date(2026, 11, 23)) == 5
    second = af.fetch_date(dt.date(2026, 11, 22), key="not-printed", today=dt.date(2026, 11, 23), transport=transport)
    assert second["requests"] == 0
    assert len(calls) == 5


def test_cache_with_finals_is_never_refetched(monkeypatch, tmp_path):
    setup_storage(monkeypatch, tmp_path)
    calls = []

    def transport(url, params, headers):
        calls.append(params)
        return 200, {}, {"paging": {"current": 1, "total": 1}, "response": [event("Arsenal", "Chelsea")], "errors": []}

    first = af.fetch_date(dt.date(2026, 11, 22), key="not-printed", today=dt.date(2026, 11, 23), transport=transport)
    assert first["final_count"] == 1 and first["requests"] == 1
    second = af.fetch_date(dt.date(2026, 11, 22), key="not-printed", today=dt.date(2026, 11, 23), transport=transport)
    assert second["cached"] is True and second["requests"] == 0
    assert len(calls) == 1


def test_only_ft_with_both_ht_and_ft_is_cached(monkeypatch, tmp_path):
    setup_storage(monkeypatch, tmp_path)

    def transport(url, params, headers):
        return 200, {}, {"paging": {"current": 1, "total": 1}, "response": [
            event("A", "B", status="FT"),
            event("C", "D", status="NS"),
            event("E", "F", status="2H"),
            event("G", "H", ht=(None, None)),
        ], "errors": []}

    result = af.fetch_date(dt.date(2026, 11, 22), key="not-printed", today=dt.date(2026, 11, 23), transport=transport)
    assert result["final_count"] == 1
    cached = af.load_cache(dt.date(2026, 11, 22))
    assert cached["events"] == [{"div": "E0", "home": "A", "away": "B", "ht": [1, 0], "ft": [2, 1], "status": "FT"}]
    assert "response" not in cached and "fixture" not in json.dumps(cached)


def test_conservative_matching_exact_alias_ambiguous_and_fuzzy() -> None:
    fixtures = [("E0", "Man United", "Wolves"), ("E0", "Brighton", "Brentford"), ("E0", "Arsenal", "Chelsea")]
    events = [
        {"div": "E0", "home": "Manchester United", "away": "Wolverhampton", "ht": [1, 0], "ft": [2, 1], "status": "FT"},
        {"div": "E0", "home": "Brighton & Hove Albion", "away": "Brentford", "ht": [0, 0], "ft": [0, 0], "status": "FT"},
        {"div": "E0", "home": "Arsenal", "away": "Chelsea", "ht": [1, 1], "ft": [1, 1], "status": "FT"},
        {"div": "E0", "home": "Arsenal", "away": "Chelsea", "ht": [0, 1], "ft": [0, 2], "status": "FT"},
    ]
    results, diagnostics = af.match_events(events, fixtures)
    assert results[("E0", "Man United", "Wolves")] == (2, 1, 1, 0)
    assert ("E0", "Brighton", "Brentford") not in results
    assert ("E0", "Arsenal", "Chelsea") not in results  # duplicate -> ambiguous
    assert diagnostics == {"fixtures": 3, "events": 4, "matched": 1, "ambiguous": 1, "unmatched": 1}


def test_eligible_fallback_is_next_day_only() -> None:
    assert af.eligible_fallback_date(dt.date(2026, 11, 22)) == dt.date(2026, 11, 21)  # Sun <- Sat
    assert af.eligible_fallback_date(dt.date(2026, 11, 23)) == dt.date(2026, 11, 22)  # Mon <- Sun
    assert af.eligible_fallback_date(dt.date(2026, 11, 25)) == dt.date(2026, 11, 24)  # Wed <- Tue
    for day in (dt.date(2026, 11, 21), dt.date(2026, 11, 24), dt.date(2026, 11, 26), dt.date(2026, 11, 27)):
        assert af.eligible_fallback_date(day) is None


def test_football_data_always_wins_and_fallback_fills_missing() -> None:
    football = {("2026-11-22", "A", "B"): (9, 9, 9, 9)}
    fallback = {("2026-11-22", "A", "B"): (1, 1, 1, 1), ("2026-11-22", "C", "D"): (2, 0, 1, 0)}
    merged = af.merge_results(football, fallback)
    assert merged[("2026-11-22", "A", "B")] == (9, 9, 9, 9)
    assert merged[("2026-11-22", "C", "D")] == (2, 0, 1, 0)


def test_out_of_window_and_missing_cache_return_no_results(monkeypatch, tmp_path):
    setup_storage(monkeypatch, tmp_path)
    result = af.cached_fallback(tmp_path, dt.date(2026, 11, 26))
    assert result["date"] is None and result["results"] == {}
    result = af.cached_fallback(tmp_path, dt.date(2026, 11, 23))
    assert result["results"] == {}


def test_settlement_is_idempotent_and_only_st_ht_ft_change(monkeypatch, tmp_path):
    setup_storage(monkeypatch, tmp_path)
    picks = tmp_path / "picks"
    picks.mkdir()
    document = {
        "date": "2026-11-22",
        "label": "Sunday 22 Nov",
        "weekday": "Sunday",
        "rows": [{"d": "E0", "k": "15:00", "h": "A", "a": "B", "m": "BTTS:GG", "p": 0.6, "pc": 0.6, "pl": 0.6, "pp": 0.6, "lr": 0.5, "ln": 100, "hr": 0.5, "hn": 10, "ar": 0.5, "an": 10, "c": "Medium", "s": 0.1, "st": "pending", "ht": None, "ft": None}],
    }
    (picks / "2026-11-22.json").write_text(json.dumps(ranking.encode(document)), encoding="utf-8")
    results = {("2026-11-22", "A", "B"): (2, 1, 1, 0)}
    first = run_model.settle_round_files(dt.date(2026, 11, 22), results, dt.date(2026, 11, 23), picks, tmp_path / "web", write=True)
    assert first["changed"] is True
    loaded = ranking.load(picks / "2026-11-22.json")
    row = loaded["rows"][0]
    assert (row["st"], row["ht"], row["ft"]) == ("landed", "1-0", "2-1")
    second = run_model.settle_round_files(dt.date(2026, 11, 22), results, dt.date(2026, 11, 23), picks, tmp_path / "web", write=True)
    assert second["changed"] is False


def test_cli_without_key_makes_zero_requests(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(af, "load_api_key", lambda: None)
    monkeypatch.setattr(af, "USAGE_FILE", tmp_path / "usage.json")
    assert af.main(["ensure", "--today", "2026-11-23"]) == 0
    out = capsys.readouterr().out
    assert "zero requests made" in out
    assert not (tmp_path / "usage.json").exists()
