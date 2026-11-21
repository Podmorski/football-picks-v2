"""Companion settling, index dedupe, and extra-league exclusion."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from pipeline import ranking, run_model


def row(**overrides) -> dict:
    base = {
        "d": "E0", "k": "15:00", "h": "A", "a": "B", "m": "BTTS:GG", "p": 0.5, "pc": 0.5,
        "pl": 0.5, "pp": 0.5, "lr": 0.3, "ln": 5000, "hr": 0.4, "hn": 20, "ar": 0.3, "an": 20,
        "c": "High", "s": 0.1, "st": "pending", "ht": None, "ft": None,
    }
    base.update(overrides)
    return base


def document(date: str = "2026-11-21") -> dict:
    return {
        "date": date, "label": "Saturday 21 Nov", "weekday": "Saturday", "kind": "round",
        "fixtures": 1, "leagues": 1, "rows": [row()],
    }


def test_rebuild_index_ignores_full_companions(tmp_path: Path) -> None:
    picks = tmp_path / "picks"
    web = tmp_path / "web"
    picks.mkdir()
    web.mkdir()
    main = document()
    (picks / "2026-11-21.json").write_text(json.dumps(ranking.encode(main)), encoding="utf-8")
    (picks / "2026-11-21.full.json").write_text(json.dumps(ranking.encode(main)), encoding="utf-8")
    index = ranking.rebuild_index(picks, web)
    assert len(index["rounds"]) == 1
    assert index["rounds"][0]["date"] == "2026-11-21"


def test_settled_companion_file_has_statuses(tmp_path: Path) -> None:
    doc = {
        "date": "2026-11-14",
        "label": "Saturday 14 Nov",
        "weekday": "Saturday",
        "kind": "round",
        "fixtures": 1,
        "leagues": 1,
        "rows": [row(st="pending"), row(m="RESULT:X", st="pending")],
    }
    results = {("2026-11-14", "A", "B"): (2, 1, 1, 0)}
    ranking.settle_document(doc, results, dt.date(2026, 11, 16))
    ranking.publish_full(doc, tmp_path / "picks", tmp_path / "web")
    loaded = ranking.load(tmp_path / "picks" / "2026-11-14.full.json")
    assert loaded["rows"][0]["st"] == "landed"
    assert loaded["rows"][1]["st"] == "lost"
    assert not (tmp_path / "picks" / "2026-11-14.json").exists()


def test_publish_full_does_not_touch_main(tmp_path: Path) -> None:
    ranking.publish_full(document(), tmp_path / "picks", tmp_path / "web")
    assert (tmp_path / "picks" / "2026-11-21.full.json").exists()
    assert not (tmp_path / "picks" / "2026-11-21.json").exists()


def test_historical_fixtures_excludes_extras() -> None:
    class Match:
        date = dt.date(2026, 11, 14)
        time = "15:00"
        odds: dict = {}

        def __init__(self, home: str) -> None:
            self.home = home
            self.away = "X"

    by_division = {"E0": [Match("A")], "BRA": [Match("B")]}
    fixtures = run_model.historical_fixtures(by_division, dt.date(2026, 11, 14), {"E0"})
    assert [fixture.div for fixture in fixtures] == ["E0"]
