"""Mozzart mapping, paging, budget, matching, returns and privacy guards."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

import pytest

from pipeline.mozzart import client, mapping, record, snapshot, teams

ROOT = Path(__file__).resolve().parents[1]


def test_mapping_known_samples() -> None:
    assert mapping.resolve("Konačan ishod", "FULL_TIME", "1") == "RESULT:1"
    assert mapping.resolve("Prvo poluvreme", "FIRST_HALF", "1") == "HALF_RESULT:I1"
    assert mapping.resolve("Drugo poluvreme", "SECOND_HALF", "X") == "SECOND_HALF_RESULT:IIX"
    assert mapping.resolve("Oba tima daju gol", "FIRST_HALF", "GG") == "BTTS_1H:IGG"
    assert mapping.resolve("Tim 1 daje gol", "FULL_TIME", "1+") == "TEAM_GOALS:I1 1+"
    assert mapping.resolve("Ukupno golova - Par/Nepar", "FULL_TIME", "PAR") == "PARITY:PAR"
    assert mapping.resolve("Hendikep pobeda", "FULL_TIME", "1") == "MARGIN:HP 1"
    assert mapping.resolve("Poluvreme - Kraj kombinazzije", "FULL_TIME", "1-1&gg") == "HTFT_COMBO:1-1&gg"


def test_mapping_unmapped_is_none() -> None:
    assert mapping.resolve("Konačan ishod", "FULL_TIME", "3") is None
    assert mapping.resolve("Winner", "FULL_TIME", "W1") is None
    assert mapping.resolve("Unknown section", "FULL_TIME", "1") is None


def test_mapping_covers_most_markets() -> None:
    samples = [
        ("Konačan ishod", "FULL_TIME", "1"),
        ("Dupla šansa", "FULL_TIME", "1X"),
        ("Ukupno golova na meču", "FULL_TIME", "3+"),
        ("Prvo poluvreme", "FIRST_HALF", "1"),
        ("Dupla šansa prvo poluvreme", "FIRST_HALF", "1X"),
        ("Ukupno golova prvo poluvreme", "FIRST_HALF", "2+"),
        ("Drugo poluvreme", "SECOND_HALF", "1"),
        ("Ukupno golova drugo poluvreme", "SECOND_HALF", "2+"),
        ("Poluvreme - Kraj", "FULL_TIME", "1-1"),
        ("Poluvreme- Kraj / Dupla šansa", "FULL_TIME", "1X-1X"),
        ("Poluvreme - Kraj kombinazzije", "FULL_TIME", "1-1&gg"),
        ("Poluvreme sa više golova", "FULL_TIME", "I>II"),
        ("Oba tima daju gol", "FULL_TIME", "GG"),
        ("Oba tima daju gol", "FIRST_HALF", "GG"),
        ("Oba tima daju gol", "SECOND_HALF", "NG"),
        ("Ukupno golova - Par/Nepar", "FULL_TIME", "NEPAR"),
        ("Dupla pobeda", "FULL_TIME", "DP1"),
        ("Sigurna pobeda", "FULL_TIME", "SP1"),
        ("Hendikep pobeda", "FULL_TIME", "2"),
        ("Tim 1 daje gol", "FULL_TIME", "2+"),
        ("Tim 2 daje gol", "FULL_TIME", "0"),
        ("Tim 1 golovi prvo poluvreme", "FIRST_HALF", "1+"),
        ("Tim 2 golovi prvo poluvreme", "FIRST_HALF", "0"),
        ("Tim 1 golovi drugo poluvreme", "SECOND_HALF", "2+"),
        ("Tim 2 golovi drugo poluvreme", "SECOND_HALF", "1+"),
        ("Tačan rezultat", "FULL_TIME", "2:1"),
        ("Konačan ishod + Golovi", "FULL_TIME", "1&2+"),
        ("Dupla šansa + Golovi", "FULL_TIME", "1X&0-2"),
        ("Poluvreme - Kraj + Golovi", "FULL_TIME", "1-1&2+"),
        ("Broj golova u prvom i drugom poluvremenu", "SECOND_HALF", "I1+&II1+"),
    ]
    coverage = mapping.coverage(
        [{"section": s, "period": p, "code": c} for s, p, c in samples]
    )
    assert sum(coverage.values()) >= 28


def test_fixture_match_with_alias() -> None:
    fixtures = [{"d": "E2", "k": "15:00", "h": "Burton", "a": "Plymouth"}]
    event = {
        "league": "Engleska 3",
        "home": "Burton Albion",
        "away": "Plymouth Argyle",
        "startTime": "2026-11-21T15:00:00Z",
    }
    match, score = snapshot.match_event(event, fixtures, dt.date(2026, 11, 21))
    assert match is not None
    assert match["h"] == "Burton"
    assert score >= teams.MATCH_SIMILARITY


def test_fixture_match_rejects_non_merge() -> None:
    fixtures = [{"d": "SP2", "k": "15:00", "h": "Celta Vigo", "a": "Girona"}]
    event = {
        "league": "Španija 2",
        "home": "Celta Vigo II",
        "away": "Girona",
        "startTime": "2026-11-21T15:00:00Z",
    }
    match, _score = snapshot.match_event(event, fixtures, dt.date(2026, 11, 21))
    assert match is None


def test_fixture_match_respects_kickoff_window() -> None:
    fixtures = [{"d": "E0", "k": "15:00", "h": "Arsenal", "a": "Chelsea"}]
    event = {
        "league": "Engleska 1",
        "home": "Arsenal",
        "away": "Chelsea",
        "startTime": "2026-11-23T15:00:00Z",
    }
    match, _score = snapshot.match_event(event, fixtures, dt.date(2026, 11, 21))
    assert match is None


def test_paging_stops_at_window_end(monkeypatch) -> None:
    base = dt.datetime(2026, 11, 21, tzinfo=dt.timezone.utc)
    pages = []

    def fake_get(key, path, params, budget, remaining, sleep=None):
        page = params["page"]
        pages.append(page)
        events = [
            {"startTime": (base + dt.timedelta(minutes=(page - 1) * 30 + index)).isoformat().replace("+00:00", "Z")}
            for index in range(30)
        ]
        return {"events": events, "totalPages": 10}, 400

    monkeypatch.setattr(client, "_get", fake_get)
    budget = client.Budget("2026-11")
    until = base + dt.timedelta(minutes=60)
    events, used = client.fetch_events("key", until, budget, sleep=lambda _seconds: None)
    assert used == 3
    assert len(events) == 60
    assert pages == [1, 2, 3]


def test_budget_cap_refuses() -> None:
    budget = client.Budget("2026-11", used=90)
    with pytest.raises(client.BudgetExceeded):
        budget.check()


def test_budget_reserve_refuses() -> None:
    budget = client.Budget("2026-11")
    with pytest.raises(client.BudgetExceeded):
        budget.check(59)
    budget.check(60)


def test_return_at_mozzart_price() -> None:
    snapshot_doc = {
        "round_date": "2026-11-21",
        "fetched_at": "2026-11-21T08:00:00+00:00",
        "fixtures": [
            {
                "div": "E0",
                "home": "A",
                "away": "B",
                "prices": {"BTTS:GG": 2.0, "RESULT:1": 3.0, "GOAL_RANGE_FT:2+": 1.5},
            }
        ],
    }
    round_doc = {
        "date": "2026-11-21",
        "kind": "round",
        "rows": [
            {"d": "E0", "h": "A", "a": "B", "m": "BTTS:GG", "pl": 0.5, "pp": 0.5, "st": "landed"},
            {"d": "E0", "h": "A", "a": "B", "m": "RESULT:1", "pl": 0.4, "pp": 0.4, "st": "lost"},
            {"d": "E0", "h": "A", "a": "B", "m": "GOAL_RANGE_FT:2+", "pl": 0.6, "pp": 0.6, "st": "pending"},
        ],
    }
    result = record.aggregate([round_doc], [snapshot_doc])
    assert result["priced_picks"] == 2
    by_key = {(row["strategy"], row["level"]): row for row in result["summary"]}
    any_lean = by_key[("lean", "any")]
    assert any_lean["picks"] == 2
    assert any_lean["mean_return"] == pytest.approx(0.0)
    assert by_key[("lean", "2.50+")]["mean_return"] == pytest.approx(-1.0)
    assert ("lean", "3.00+") not in by_key


def test_freeze_maps_published_picks() -> None:
    snapshot_doc = {
        "round_date": "2026-11-21",
        "fixtures": [{"div": "E0", "home": "A", "away": "B", "prices": {"BTTS:GG": 2.1}}],
    }
    round_doc = {"date": "2026-11-21", "rows": [{"d": "E0", "h": "A", "a": "B", "m": "BTTS:GG"}]}
    assert record.freeze(snapshot_doc, round_doc) == {"E0|A|B|BTTS:GG": 2.1}


def test_price_files_are_gitignored() -> None:
    for path in ("web/public/data/mozzart-prices.json", "web/public/data/mozzart-record.json"):
        result = subprocess.run(
            ["git", "check-ignore", "-q", path], cwd=ROOT, capture_output=True
        )
        assert result.returncode == 0, f"{path} must be gitignored"


def test_prebuild_is_gated_on_priced() -> None:
    script = (ROOT / "web" / "scripts" / "fetch-prices.mjs").read_text(encoding="utf-8")
    assert "process.env.PRICED !== '1'" in script
    assert "mozzart-prices.json" in script


def test_snapshot_build_joins_event_to_fixture() -> None:
    fixture = {"d": "E0", "k": "15:00", "h": "Arsenal", "a": "Chelsea"}
    event = {
        "league": "Engleska 1",
        "home": "Arsenal",
        "away": "Chelsea",
        "startTime": "2026-11-21T15:00:00Z",
        "markets": [
            {
                "rawName": "Konačan ishod",
                "period": "FULL_TIME",
                "selections": [{"rawName": "1", "odds": 2.1, "isActive": True}],
            },
            {
                "rawName": "Oba tima daju gol",
                "period": "FULL_TIME",
                "selections": [{"rawName": "GG", "odds": 1.9, "isActive": True}],
            },
        ],
    }
    snap = snapshot.build(
        dt.date(2026, 11, 21),
        [fixture],
        [event],
        dt.datetime(2026, 11, 21, 8, 0, tzinfo=dt.timezone.utc),
    )
    assert snap["fixtures"][0]["prices"] == {"RESULT:1": 2.1, "BTTS:GG": 1.9}
    assert snap["unmatched_fixtures"] == []


def test_cli_without_fixtures_is_a_noop(tmp_path, monkeypatch, capsys) -> None:
    from pipeline.mozzart import cli

    monkeypatch.setattr(cli, "PICKS_DIR", tmp_path)
    (tmp_path / "2026-11-21.json").write_text(
        '{"date":"2026-11-21","kind":"round","picks":[]}', encoding="utf-8"
    )
    assert cli.main(["--date", "2026-11-21", "--prices-dir", str(tmp_path / "prices")]) == 0
    assert "no fixtures" in capsys.readouterr().out


def test_started_fixtures_are_skipped() -> None:
    fetched = dt.datetime(2026, 11, 21, 10, 0, tzinfo=dt.timezone.utc)
    fixtures = [
        {"d": "T1", "k": "10:10", "h": "Genclerbirligi", "a": "Gaziantep"},
        {"d": "E0", "k": "12:30", "h": "Man City", "a": "Fulham"},
    ]

    def event(league, home, away, kickoff):
        return {
            "league": league, "home": home, "away": away, "startTime": kickoff,
            "markets": [{
                "rawName": "Konačan ishod", "period": "FULL_TIME",
                "selections": [{"rawName": "1", "odds": 2.1, "isActive": True}],
            }],
        }

    events = [
        event("Turska 1", "Genclerbirligi", "Gaziantep", "2026-11-21T10:10:00Z"),
        event("Engleska 1", "Man City", "Fulham", "2026-11-21T12:30:00Z"),
    ]
    snap = snapshot.build(dt.date(2026, 11, 21), fixtures, events, fetched, min_lead_minutes=20)
    assert [row["home"] for row in snap["fixtures"]] == ["Man City"]
    assert [row["home"] for row in snap["started_not_priced"]] == ["Genclerbirligi"]
    assert snap["unmatched_fixtures"] == []


def test_second_run_makes_no_requests(tmp_path, monkeypatch) -> None:
    from pipeline.mozzart import cli

    monkeypatch.setattr(cli, "PICKS_DIR", tmp_path)
    (tmp_path / "2026-11-21.json").write_text(
        json.dumps({
            "date": "2026-11-21", "kind": "round",
            "fixture_list": [{"d": "E0", "k": "15:00", "h": "A", "a": "B"}],
            "rows": [],
        }),
        encoding="utf-8",
    )
    prices = tmp_path / "prices"
    (prices / "rounds").mkdir(parents=True)
    (prices / "rounds" / "2026-11-21.json").write_text(
        json.dumps({"round_date": "2026-11-21", "fetched_at": "2026-11-21T10:00:00+00:00", "fixtures": []}),
        encoding="utf-8",
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("must not fetch when a snapshot exists")

    monkeypatch.setattr(client, "fetch_events", boom)
    assert cli.main(["--date", "2026-11-21", "--prices-dir", str(prices)]) == 0


def test_rate_limit_header_is_not_the_monthly_quota() -> None:
    assert "x-ratelimit-remaining" not in client._REMAINING_HEADERS

    class RateLimited:
        headers = {"x-ratelimit-remaining": "0"}

    class Quota:
        headers = {"x-quota-remaining": "300"}

    assert client._remaining(RateLimited(), {}) is None
    assert client._remaining(Quota(), {}) == 300


def test_rate_limit_backoff(monkeypatch) -> None:
    calls = {"n": 0}

    class FakeResponse:
        status = 200
        headers = {"x-ratelimit-remaining": "0"}

        def read(self):
            return b'{"events": [], "totalPages": 1}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout=30):
        calls["n"] += 1
        if calls["n"] == 1:
            raise client.urllib.error.HTTPError(
                request.full_url, 429, "rate", {"Retry-After": "2"}, None
            )
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    sleeps: list[float] = []
    budget = client.Budget("2026-11")
    body, _remaining_value = client._get(
        "k", "/soccer/events", {"page": 1}, budget, None, sleep=lambda seconds: sleeps.append(seconds)
    )
    assert sleeps == [2.0]
    assert body["totalPages"] == 1
    assert len(budget.entries) == 2


def test_snapshot_merge_keeps_existing_price() -> None:
    existing = {
        "round_date": "2026-11-21", "fetched_at": "2026-11-21T09:51:32+00:00",
        "fixtures": [{"div": "E0", "home": "A", "away": "B", "prices": {"BTTS:GG": 2.0}}],
        "unmatched_fixtures": [{"div": "E0", "home": "C", "away": "D", "kickoff": "15:00"}],
    }
    new = {
        "round_date": "2026-11-21", "fetched_at": "2026-11-21T10:10:00+00:00",
        "fixtures": [
            {"div": "E0", "home": "A", "away": "B", "prices": {"BTTS:GG": 9.9}},
            {"div": "E0", "home": "C", "away": "D", "prices": {"BTTS:GG": 1.8}},
        ],
        "unmatched_fixtures": [], "started_not_priced": [],
    }
    fixtures = [
        {"d": "E0", "k": "15:00", "h": "A", "a": "B"},
        {"d": "E0", "k": "15:00", "h": "C", "a": "D"},
    ]
    merged = snapshot.merge(existing, new, fixtures)
    prices = {(row["home"], row["away"]): row["prices"]["BTTS:GG"] for row in merged["fixtures"]}
    assert prices == {("A", "B"): 2.0, ("C", "D"): 1.8}
    assert merged["fixtures"][0]["fetched_at"] == "2026-11-21T09:51:32+00:00"
    assert merged["completion_fetched_at"] == "2026-11-21T10:10:00+00:00"
