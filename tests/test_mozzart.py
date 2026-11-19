"""Mozzart mapping, paging, budget, matching, returns and privacy guards."""
from __future__ import annotations

import datetime as dt
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

    def fake_get(key, path, params, budget, remaining):
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
