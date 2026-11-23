"""API-Football diagnostic: hard request cap and conservative aggregation."""
from __future__ import annotations

from pipeline import api_football_probe as probe


def test_second_page_only_for_documented_pagination_and_cap_never_exceeds_four() -> None:
    calls = []

    def transport(url, params, headers):
        page = params.get("page", 1)
        calls.append((params["date"], page))
        total = 3 if params["date"] == "2026-11-21" else 2
        return 200, {}, {"paging": {"current": page, "total": total}, "response": [], "errors": []}

    worker = probe.Probe(key="not-printed", transport=transport)
    result = probe.run(worker)
    assert worker.calls == 4
    assert calls == [("2026-11-21", 1), ("2026-11-21", 2), ("2026-11-22", 1), ("2026-11-22", 2)]
    assert result["requests"] == 4
    assert result["settlement_activated"] is False


def test_no_retry_on_provider_error_and_no_second_page() -> None:
    calls = []

    def transport(url, params, headers):
        calls.append(params["date"])
        return 403, {"x-ratelimit-requests-remaining": "0"}, {"errors": {"plan": "date gate"}, "paging": {}, "response": []}

    worker = probe.Probe(key="not-printed", transport=transport)
    result = probe.run(worker, ("2026-11-21",))
    assert calls == ["2026-11-21"]
    assert worker.calls == 1
    assert result["provider_error_responses"]
    assert result["pages"][0]["quota"]["x-ratelimit-requests-remaining"] == "0"


def test_summary_does_not_require_a_local_fixtures_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(probe, "RAW_DIR", tmp_path)

    def transport(url, params, headers):
        return 200, {}, {"paging": {}, "response": [], "errors": []}

    result = probe.run(probe.Probe(key="not-printed", transport=transport), ("2026-11-21",))
    assert result["v2_fixtures"] == 0
    assert result["requests"] == 1


def test_missing_key_makes_zero_requests(monkeypatch, capsys) -> None:
    monkeypatch.setattr(probe, "load_api_key", lambda: None)
    assert probe.main([]) == 2
    assert "zero requests made" in capsys.readouterr().out


def test_division_mapping_and_ht_ft_definition() -> None:
    assert probe.division_for({"name": "Premier League", "country": "England"}) == "E0"
    assert probe.division_for({"name": "League One", "country": "Scotland"}) == "SC2"
    assert probe.division_for({"name": "League One", "country": "England"}) == "E2"
    row = probe._event_row({
        "fixture": {"date": "2026-11-21T15:00:00+00:00", "status": {"short": "FT"}},
        "league": {"name": "Premier League", "country": "England"},
        "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
        "score": {"halftime": {"home": 1, "away": 0}, "fulltime": {"home": 2, "away": 1}},
    })
    assert row["div"] == "E0" and row["ht"] and row["ft"] and row["status"] == "FT"
