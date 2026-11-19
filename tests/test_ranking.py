"""Ranking tallies, statuses, the Monday rule and the compact round format."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from pipeline.ranking import decode, encode, rank_rows, round_action, settle_document, tally
from pipeline.model.ranking_backtest import mean_return_ci, pick_return
from pipeline.run_model import is_settle_only


def row(**overrides) -> dict:
    base = {
        "d": "E2",
        "k": "15:00",
        "h": "A",
        "a": "B",
        "m": "BTTS:GG",
        "p": 0.40,
        "pl": 0.38,
        "pp": 0.39,
        "lr": 0.30,
        "ln": 5000,
        "hr": 0.4,
        "hn": 20,
        "ar": 0.3,
        "an": 20,
        "c": "High",
        "s": 1.267,
        "st": "pending",
        "ht": None,
        "ft": None,
    }
    base.update(overrides)
    return base


def test_tally_excludes_pending_and_void() -> None:
    rows = [
        row(st="landed", pl=0.40),
        row(st="lost", pl=0.30),
        row(st="pending", pl=0.90),
        row(st="void", pl=0.90),
    ]
    stats = tally(rows)
    assert stats["landed"] == 1
    assert stats["lost"] == 1
    assert stats["settled"] == 2
    assert stats["expected"] == pytest.approx(0.70)


def test_tally_expected_uses_the_shown_probability() -> None:
    rows = [row(st="landed", pl=0.25, p=0.9), row(st="lost", pl=0.75, p=0.1)]
    assert tally(rows)["expected"] == pytest.approx(1.0)


def test_settle_document_marks_statuses_and_scores() -> None:
    document = {
        "date": "2026-11-14",
        "rows": [
            row(h="A", a="B", m="BTTS:GG"),
            row(h="C", a="D", m="BTTS:GG"),
            row(h="E", a="F", m="BTTS:GG"),
        ],
    }
    results = {
        ("2026-11-14", "A", "B"): (2, 1, 1, 0),
        ("2026-11-14", "C", "D"): (0, 0, 0, 0),
    }
    settle_document(document, results, dt.date(2026, 11, 16))
    first, second, third = document["rows"]
    assert first["st"] == "landed"
    assert (first["ht"], first["ft"]) == ("1-0", "2-1")
    assert second["st"] == "lost"
    assert third["st"] == "void"


def test_pending_round_is_not_voided() -> None:
    document = {"date": "2026-11-21", "rows": [row()]}
    settle_document(document, {}, dt.date(2026, 11, 19))
    assert document["rows"][0]["st"] == "pending"


def test_show_filter() -> None:
    rows = [
        row(h="A", st="landed"),
        row(h="C", st="lost"),
        row(h="E", st="pending"),
    ]
    assert len(rank_rows(rows, show="all")) == 3
    assert [r["h"] for r in rank_rows(rows, show="landed")] == ["A"]
    assert [r["h"] for r in rank_rows(rows, show="lost")] == ["C"]


def test_empty_round_file_is_replaced_but_a_filled_one_is_not() -> None:
    empty = {"date": "2026-11-21", "rows": []}
    filled = {"date": "2026-11-21", "rows": [row()]}
    fixtures = ["fixture"]

    assert round_action(None, fixtures) == "publish"
    assert round_action(empty, fixtures) == "publish"
    assert round_action(empty, []) == "skip"
    assert round_action(filled, fixtures) == "settle"


def test_monday_is_settle_only() -> None:
    assert is_settle_only(dt.date(2026, 11, 23)) is True  # Monday
    assert is_settle_only(dt.date(2026, 11, 21)) is False  # Saturday
    assert is_settle_only(dt.date(2026, 11, 24)) is False  # Tuesday


def test_round_file_round_trips(tmp_path: Path) -> None:
    document = {
        "date": "2026-11-14",
        "label": "Saturday 14 Nov",
        "weekday": "Saturday",
        "fixtures": 1,
        "leagues": 1,
        "markets": 178,
        "bands": [],
        "market_bands": {},
        "rows": [row(st="landed", ht="1-0", ft="2-1")],
    }
    encoded = encode(document)
    assert isinstance(encoded["rows"][0], list)
    decoded_rows = decode(encoded)["rows"]
    assert decoded_rows
    assert decoded_rows[0]["st"] == "landed"
    assert decoded_rows[0]["ft"] == "2-1"
    assert decoded_rows[0]["pl"] == 0.38


def test_pick_return_at_fair_odds() -> None:
    # A winning pick returns fair - 1; a loser returns -1 whatever the price.
    assert pick_return(2.50, True) == pytest.approx(1.50)
    assert pick_return(1.80, False) == pytest.approx(-1.0)


def test_mean_return_ci_on_known_sequence() -> None:
    picks = [
        {"date": "2024-01-06", "return": pick_return(2.0, True)},  # +1.0
        {"date": "2024-01-06", "return": pick_return(4.0, False)},  # -1.0
        {"date": "2024-01-13", "return": pick_return(3.0, True)},  # +2.0
        {"date": "2024-01-13", "return": pick_return(2.0, True)},  # +1.0
    ]
    mean, (low, high) = mean_return_ci(picks, resamples=2000, seed=20261025)
    assert mean == pytest.approx(0.75)
    # With two round dates the bootstrap draws one or both: means 0, 0.75 and 1.5.
    assert low == pytest.approx(0.0, abs=0.01)
    assert high == pytest.approx(1.5, abs=0.01)
    assert low <= mean <= high


def test_mean_return_ci_on_no_picks() -> None:
    assert mean_return_ci([]) == (None, [None, None])
