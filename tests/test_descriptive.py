"""Descriptive statistics: cutoffs, windows, streaks, H2H and deterministic sidecars."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import cast

import pytest

from pipeline import descriptive, ranking
from pipeline.parse import Match

ROOT = Path(__file__).resolve().parents[1]
START = dt.date(2026, 1, 1)
UNSET = object()


def match(
    day: int, home: str, away: str, fthg: int | None, ftag: int | None,
    hthg: int | None | object = UNSET, htag: int | None | object = UNSET,
) -> Match:
    if hthg is UNSET:
        hthg = None if fthg is None else fthg // 2
    if htag is UNSET:
        htag = None if ftag is None else ftag // 2
    return Match(
        season="2026-27", date=START + dt.timedelta(days=day),
        home=home, away=away, fthg=cast(int, fthg), ftag=cast(int, ftag),
        hthg=cast(int | None, None if hthg is UNSET else hthg),
        htag=cast(int | None, None if htag is UNSET else htag),
    )


def window(matches: list[Match], team: str) -> dict:
    return descriptive.window_stats(matches, team)


def test_strict_before_date_cutoff_excludes_same_day_and_later_results() -> None:
    rows = [
        match(0, "A", "B", 2, 1),
        match(1, "A", "C", 1, 0),
        match(4, "D", "A", 0, 2),  # same day as the fixture: excluded
        match(5, "A", "D", 5, 0),  # later: excluded
    ]
    cutoff = START + dt.timedelta(days=4)
    index = descriptive.build_history(rows)
    block = descriptive.team_block(index, "A", cutoff, "home")
    assert block["windows"]["overall6"]["n"] == 2
    assert block["windows"]["overall6"]["w"] == 2
    first = descriptive.round_sidecar({"date": cutoff.isoformat(), "fixture_list": [
        {"d": "E0", "k": "15:00", "h": "A", "a": "B"},
    ], "rows": [{}]}, index)
    second = descriptive.round_sidecar({"date": cutoff.isoformat(), "fixture_list": [
        {"d": "E0", "k": "15:00", "h": "A", "a": "B"},
    ], "rows": [{}]}, descriptive.build_history(rows + [match(8, "A", "E", 9, 0)]))
    assert first == second


def test_last_six_last_twelve_ordering_and_short_history_are_not_padded() -> None:
    rows = []
    for day in range(13):
        if day % 2 == 0:
            rows.append(match(day, "A", f"O{day}", 2, 0))
        else:
            rows.append(match(day, f"O{day}", "A", 1, 0))
    index = descriptive.build_history(rows)
    block = descriptive.team_block(index, "A", START + dt.timedelta(days=13), "home")
    last6 = block["windows"]["overall6"]
    last12 = block["windows"]["overall12"]
    assert (last6["n"], last6["w"], last6["d"], last6["l"]) == (6, 3, 0, 3)
    assert (last6["gf"], last6["ga"], last6["points"], last6["points_pm"]) == (6, 3, 9, 1.5)
    assert (last12["n"], last12["w"], last12["l"], last12["points"]) == (12, 6, 6, 18)
    short = descriptive.team_block(
        descriptive.build_history(rows[:3]), "A", START + dt.timedelta(days=3), "home",
    )
    assert short["windows"]["overall6"]["n"] == 3
    assert short["windows"]["overall12"]["n"] == 3


def test_team_and_venue_perspective_with_reversed_fixtures() -> None:
    rows = [
        match(0, "B", "A", 1, 3),  # A away win
        match(1, "A", "C", 0, 2),  # A home loss
    ]
    index = descriptive.build_history(rows)
    block = descriptive.team_block(index, "A", START + dt.timedelta(days=2), "away")
    away = block["windows"]["venue6"]
    assert (away["n"], away["w"], away["l"], away["gf"], away["ga"]) == (1, 1, 0, 3, 1)
    assert block["windows"]["overall6"]["n"] == 2
    assert block["windows"]["overall6"]["gf"] == 3


def test_wdl_goals_points_and_all_frequency_arithmetic() -> None:
    rows = [
        match(0, "A", "B", 2, 1, 1, 0),
        match(1, "B", "A", 1, 1, 0, 0),
        match(2, "C", "A", 0, 3, 0, 1),
        match(3, "D", "A", 2, 2, None, None),
    ]
    stats = window(rows, "A")
    assert (stats["n"], stats["w"], stats["d"], stats["l"]) == (4, 2, 2, 0)
    assert (stats["gf"], stats["ga"], stats["points"], stats["points_pm"]) == (8, 4, 8, 2.0)
    assert stats["btts"] == {"count": 3, "rate": 0.75}
    assert stats["over25"] == {"count": 3, "rate": 0.75}
    assert stats["ft"] == {"n": 4, "1": 0.25, "X": 0.5, "2": 0.25}
    assert stats["ht"]["n"] == 3
    assert stats["ht"]["1"] == pytest.approx(1 / 3, abs=1e-4)
    assert stats["ht"]["X"] == pytest.approx(1 / 3, abs=1e-4)
    assert stats["ht"]["2"] == pytest.approx(1 / 3, abs=1e-4)
    assert stats["htft"]["n"] == 3
    assert stats["htft"]["1-1"] == pytest.approx(1 / 3, abs=1e-4)
    assert stats["htft"]["X-X"] == pytest.approx(1 / 3, abs=1e-4)
    assert stats["htft"]["2-2"] == pytest.approx(1 / 3, abs=1e-4)


def test_zero_history_has_null_rates_not_zero_probability() -> None:
    stats = window([], "Nobody")
    assert stats["n"] == 0
    assert stats["gf_pm"] is None
    assert stats["points_pm"] is None
    assert stats["btts"] == {"count": 0, "rate": None}
    assert stats["ft"] == {"n": 0, "1": None, "X": None, "2": None}
    assert stats["htft"]["n"] == 0 and stats["htft"]["1-1"] is None


def test_streak_definitions_zero_length_and_missing_result_skipping() -> None:
    cases = {
        "win": ([match(0, "A", "B", 0, 1), match(1, "A", "C", 2, 1)], 1),
        "unbeaten": ([match(0, "A", "B", 0, 1), match(1, "A", "C", 1, 1)], 1),
        "winless": ([match(0, "A", "B", 2, 0), match(1, "A", "C", 1, 1)], 1),
        "losing": ([match(0, "A", "B", 2, 0), match(1, "A", "C", 0, 1)], 1),
        "drawing": ([match(0, "A", "B", 1, 1), match(1, "A", "C", 2, 2)], 2),
        "btts": ([match(0, "A", "B", 1, 0), match(1, "A", "C", 2, 1), match(2, "A", "D", 3, 2)], 2),
        "no_btts": ([match(0, "A", "B", 2, 1), match(1, "A", "C", 1, 0), match(2, "A", "D", 2, 0)], 2),
        "over25": ([match(0, "A", "B", 1, 1), match(1, "A", "C", 2, 1), match(2, "A", "D", 3, 0)], 2),
        "under25": ([match(0, "A", "B", 3, 1), match(1, "A", "C", 1, 0), match(2, "A", "D", 2, 0)], 2),
    }
    for name, (rows, expected) in cases.items():
        assert descriptive.compute_streaks(rows, "A")[name] == expected, name

    zero = descriptive.compute_streaks([match(0, "A", "B", 2, 0), match(1, "A", "C", 1, 1)], "A")
    assert zero["win"] == 0 and zero["losing"] == 0 and zero["drawing"] == 1
    missing = [match(0, "A", "B", 2, 0), match(1, "A", "C", None, None)]
    index = descriptive.build_history(missing)
    streaks = descriptive.compute_streaks(list(index.by_team["A"]), "A")
    assert streaks["win"] == 1
    assert len(index.by_team["A"]) == 1


def test_venue_specific_streak_uses_only_that_venue() -> None:
    rows = [match(0, "A", "B", 0, 1), match(1, "B", "A", 0, 2)]
    block = descriptive.team_block(
        descriptive.build_history(rows), "A", START + dt.timedelta(days=2), "home",
    )
    assert block["streaks"]["overall"]["win"] == 1
    assert block["streaks"]["overall"]["losing"] == 0
    assert block["streaks"]["venue"]["losing"] == 1
    assert block["streaks"]["venue"]["win"] == 0


def test_h2h_reversed_perspective_total_sample_and_recent_limit() -> None:
    rows = [
        match(0, "A", "B", 2, 1),
        match(1, "B", "A", 3, 0),
        match(2, "A", "B", 0, 0),
        match(3, "A", "B", 1, 0),
        match(4, "B", "A", 0, 1),
        match(5, "A", "B", 1, 0),
        match(6, "A", "B", 1, 0),
    ]
    h2h = descriptive.head_to_head(
        descriptive.build_history(rows), "A", "B", START + dt.timedelta(days=7),
    )
    assert h2h["n"] == 7
    assert (h2h["w"], h2h["d"], h2h["l"]) == (5, 1, 1)
    assert (h2h["gf"], h2h["ga"]) == (6, 4)
    assert h2h["btts"] == {"count": 1, "rate": 0.1429}
    assert h2h["over25"] == {"count": 2, "rate": 0.2857}
    assert len(h2h["meetings"]) == 6
    assert [meeting["date"] for meeting in h2h["meetings"]] == [
        (START + dt.timedelta(days=day)).isoformat() for day in (6, 5, 4, 3, 2, 1)
    ]


def test_missing_h2h_is_an_available_data_state() -> None:
    h2h = descriptive.head_to_head(
        descriptive.build_history([match(0, "C", "D", 1, 0)]), "A", "B", START + dt.timedelta(days=1),
    )
    assert h2h["n"] == 0
    assert h2h["meetings"] == []
    assert h2h["btts"] == {"count": 0, "rate": None}
    assert h2h["over25"] == {"count": 0, "rate": None}


def _document(date: dt.date) -> dict:
    return {
        "date": date.isoformat(), "label": date.isoformat(), "weekday": date.strftime("%A"),
        "kind": "round", "fixtures": 1, "leagues": 1, "markets": 2,
        "rows": [{
            "d": "E0", "k": "15:00", "h": "A", "a": "B", "m": "RESULT:1",
            "p": 0.5, "pc": 0.5, "pl": 0.5, "pp": 0.5, "lr": 0.4, "ln": 100,
            "hr": 0.4, "hn": 10, "ar": 0.4, "an": 10, "c": "Medium", "s": 0.0,
            "st": "pending", "ht": None, "ft": None,
        }],
    }


def test_sidecar_backfill_is_deterministic_and_never_touches_round_bytes(tmp_path: Path) -> None:
    picks = tmp_path / "picks"
    rounds = tmp_path / "rounds"
    out = tmp_path / "descriptive"
    date = START + dt.timedelta(days=4)
    document = _document(date)
    ranking.publish(document, picks, rounds)
    ranking.publish_full(document, picks, rounds)
    main = picks / f"{date.isoformat()}.json"
    full = picks / f"{date.isoformat()}.full.json"
    before = (main.read_bytes(), full.read_bytes())
    history = [match(0, "A", "B", 2, 1), match(1, "B", "A", 1, 1)]

    first = descriptive.backfill_rounds(picks, {"E0": history}, out)
    assert first == [{"date": date.isoformat(), "fixtures": 1}]
    sidecar = out / f"{date.isoformat()}.json"
    first_bytes = sidecar.read_bytes()
    assert (main.read_bytes(), full.read_bytes()) == before

    later = history + [
        match(4, "A", "B", 9, 0),  # same day
        match(5, "A", "C", 8, 0),  # later
    ]
    descriptive.backfill_rounds(picks, {"E0": later}, out)
    assert sidecar.read_bytes() == first_bytes
    assert (main.read_bytes(), full.read_bytes()) == before

    payload = json.loads(first_bytes)
    assert payload["schema_version"] == 1
    assert payload["definitions_version"] == descriptive.DEFINITIONS_VERSION
    assert payload["fixtures"][0]["d"] == "E0"
    assert payload["fixtures"][0]["cutoff"] == date.isoformat()
    text = first_bytes.decode("utf-8").lower()
    for forbidden in ("mozzart", "correct_score", "b365", "odds"):
        assert forbidden not in text


def test_committed_sidecars_cover_every_indexed_round_and_fixture() -> None:
    picks = ROOT / "picks"
    out = ROOT / "web" / "public" / "data" / "descriptive"
    indexed = []
    for path in sorted(picks.glob("*.json")):
        if path.name.endswith(".full.json"):
            continue
        document = ranking.load(path)
        if not document.get("rows"):
            continue
        indexed.append(document)
        sidecar_path = out / f"{document['date']}.json"
        assert sidecar_path.exists(), sidecar_path
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == descriptive.SCHEMA_VERSION
        assert payload["cutoff_date"] == document["date"]
        want = {(fixture["d"], fixture["h"], fixture["a"]) for fixture in descriptive._round_fixtures(document)}
        got = {(fixture["d"], fixture["h"], fixture["a"]) for fixture in payload["fixtures"]}
        assert got == want
        assert all(fixture["cutoff"] == document["date"] for fixture in payload["fixtures"])
        text = sidecar_path.read_text(encoding="utf-8").lower()
        for forbidden in ("mozzart", "correct_score", "b365", "odds", "probability"):
            assert forbidden not in text
    assert len(indexed) >= 3
    assert {document["date"] for document in indexed} >= {"2026-11-14", "2026-11-21", "2026-11-22"}


def test_run_model_generates_descriptive_sidecars_on_the_trusted_path() -> None:
    source = (ROOT / "pipeline" / "run_model.py").read_text(encoding="utf-8")
    assert 'descriptive.backfill_rounds(' in source
    assert 'WEB_DATA_DIR / "descriptive"' in source
    assert 'descriptive sidecars: ' in source
