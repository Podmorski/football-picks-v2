"""API-Football diagnostic: five-request cap, page omission, conservative matching."""
from __future__ import annotations

from pipeline import api_football_probe as probe


def test_first_request_omits_page_and_pagination_stops_at_the_cap() -> None:
    calls = []

    def transport(url, params, headers):
        calls.append(dict(params))
        page = params.get("page", 1)
        return 200, {}, {"paging": {"current": page, "total": 9}, "response": [], "errors": []}

    worker = probe.Probe(key="not-printed", transport=transport)
    result = probe.run(worker)
    assert "page" not in calls[0]
    assert [params.get("page", 1) for params in calls] == [1, 2, 3, 4, 5]
    assert worker.calls == 5
    assert result["requests"] == 5
    assert result["settlement_activated"] is False


def test_documented_pagination_is_followed_when_fewer_pages_exist() -> None:
    calls = []

    def transport(url, params, headers):
        calls.append(params.get("page", 1))
        return 200, {}, {"paging": {"current": params.get("page", 1), "total": 2}, "response": [], "errors": []}

    worker = probe.Probe(key="not-printed", transport=transport)
    probe.run(worker)
    assert calls == [1, 2]
    assert worker.calls == 2


def test_no_retry_on_provider_error_and_no_second_page() -> None:
    calls = []

    def transport(url, params, headers):
        calls.append(params["date"])
        return 403, {"x-ratelimit-requests-remaining": "0"}, {"errors": {"plan": "date gate"}, "paging": {}, "response": []}

    worker = probe.Probe(key="not-printed", transport=transport)
    result = probe.run(worker, ("2026-11-22",))
    assert calls == ["2026-11-22"]
    assert worker.calls == 1
    assert result["provider_error_responses"]
    assert result["pages"][0]["quota"]["x-ratelimit-requests-remaining"] == "0"


def test_summary_does_not_require_a_local_fixtures_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(probe, "RAW_DIR", tmp_path)

    def transport(url, params, headers):
        return 200, {}, {"paging": {}, "response": [], "errors": []}

    result = probe.run(probe.Probe(key="not-printed", transport=transport), ("2026-11-22",))
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
        "fixture": {"date": "2026-11-22T15:00:00+00:00", "status": {"short": "FT"}},
        "league": {"name": "Premier League", "country": "England"},
        "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
        "score": {"halftime": {"home": 1, "away": 0}, "fulltime": {"home": 2, "away": 1}},
    })
    assert row["div"] == "E0" and row["ht"] and row["ft"] and row["status"] == "FT"


def _event(home: str, away: str, status: str = "FT") -> dict:
    return {
        "fixture": {"date": "2026-11-22T15:00:00+00:00", "status": {"short": status}},
        "league": {"name": "Premier League", "country": "England"},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "score": {"halftime": {"home": 1, "away": 0}, "fulltime": {"home": 2, "away": 1}},
    }


def test_conservative_matching_accepts_verified_aliases_and_rejects_fuzzy(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(probe, "RAW_DIR", tmp_path)
    header = "Div,Date,Time,HomeTeam,AwayTeam\n"
    rows = (
        "E0,22/11/2026,15:00,Man United,Wolves\n"
        "E0,22/11/2026,15:00,Brighton,Brentford\n"
    )
    (tmp_path / "fixtures.csv").write_text(header + rows, encoding="utf-8")
    events = [
        _event("Manchester United", "Wolverhampton"),
        _event("Brighton & Hove Albion", "Brentford"),
    ]
    result = probe.summarise([], events, ("2026-11-22",))
    assert result["v2_fixtures"] == 2
    assert result["exact_matches"] == 0
    assert result["alias_matches"] == 1  # Man United/Wolves are evidenced aliases
    assert result["unmatched"] == 1  # Brighton & Hove Albion is not verified as Brighton


def test_near_names_are_left_unmatched_without_a_verified_alias(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(probe, "RAW_DIR", tmp_path)
    (tmp_path / "fixtures.csv").write_text(
        "Div,Date,Time,HomeTeam,AwayTeam\nE0,22/11/2026,15:00,Brighton,Brentford\n", encoding="utf-8"
    )
    result = probe.summarise([], [_event("Brighton & Hove Albion", "Brentford")], ("2026-11-22",))
    assert result["exact_matches"] == 0
    assert result["alias_matches"] == 0
    assert result["unmatched"] == 1


def test_duplicate_provider_events_are_ambiguous(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(probe, "RAW_DIR", tmp_path)
    (tmp_path / "fixtures.csv").write_text(
        "Div,Date,Time,HomeTeam,AwayTeam\nE0,22/11/2026,15:00,Arsenal,Chelsea\n", encoding="utf-8"
    )
    events = [_event("Arsenal", "Chelsea"), _event("Arsenal", "Chelsea")]
    result = probe.summarise([], events, ("2026-11-22",))
    assert result["exact_matches"] == 1
    assert result["ambiguous_matches"] == 1
    assert result["unmatched"] == 0
