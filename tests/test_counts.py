"""Counting, Wilson intervals, streaks and Top 10s."""
from __future__ import annotations

import datetime as dt

import pytest

from pipeline.counts import (
    current_streak,
    league_counts,
    summary,
    team_counts,
    top_ten,
    wilson_interval,
)
from pipeline.outcomes import OUTCOMES, OUTCOMES_BY_ID
from pipeline.parse import Match


def make_match(
    day: int,
    home: str,
    away: str,
    fthg: int,
    ftag: int,
    hthg: int | None = 0,
    htag: int | None = 0,
    month: int = 8,
    season: str = "2024-25",
) -> Match:
    return Match(
        season=season,
        date=dt.date(2024, month, day),
        home=home,
        away=away,
        fthg=fthg,
        ftag=ftag,
        hthg=hthg,
        htag=htag,
    )


def test_wilson_known_values() -> None:
    lo, hi = wilson_interval(5, 10)
    assert lo == pytest.approx(0.2366, abs=5e-4)
    assert hi == pytest.approx(0.7634, abs=5e-4)


def test_wilson_at_the_edges() -> None:
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0
    assert hi == pytest.approx(0.2775, abs=5e-4)

    lo, hi = wilson_interval(10, 10)
    assert lo == pytest.approx(0.7225, abs=5e-4)
    assert hi == 1.0

    assert wilson_interval(0, 0) == (None, None)


def test_summary_format() -> None:
    assert summary(0, 0) == [0, 0, None, None, None]
    stat = summary(6, 10)
    assert stat[0] == 10
    assert stat[1] == 6
    assert stat[2] == pytest.approx(0.6)
    assert stat[3] < 0.6 < stat[4]


def test_current_streak() -> None:
    assert current_streak([True, True, True]) == 3
    assert current_streak([True, False, True]) == 1
    assert current_streak([False, True, True]) == 0
    assert current_streak([]) == 0


def test_last_n_and_streak_on_a_known_sequence() -> None:
    # Team A: 2-0 on the three oldest matchdays, then 0-0 afterwards.
    matches = [make_match(day, "A", "X", 2 if day <= 3 else 0, 0) for day in range(1, 13)]
    # Team B: 2-0 in every match.
    matches += [make_match(day, "B", "Y", 2, 0) for day in range(1, 13)]

    teams = team_counts(matches, OUTCOMES, "2024-25", None)
    outcome = "tg_2plus"

    overall = teams["A"]["current"]["overall"][outcome]
    assert overall[0] == 12
    assert overall[1] == 3
    assert overall[2] == pytest.approx(0.25)

    last10 = teams["A"]["current"]["last10"][outcome]
    assert last10[0] == 10
    assert last10[1] == 1

    last6 = teams["A"]["current"]["last6"][outcome]
    assert last6[0] == 6
    assert last6[1] == 0

    assert teams["A"]["streak"][outcome] == 0
    assert teams["B"]["streak"][outcome] == 12
    assert teams["B"]["current"]["last6"][outcome][1] == 6


def test_league_counts_pooled_season_and_weekday() -> None:
    saturday = make_match(3, "A", "B", 2, 0)  # Saturday
    tuesday = make_match(6, "C", "D", 0, 0)  # Tuesday
    assert saturday.weekday == 5
    assert tuesday.weekday == 1

    counts = league_counts([saturday, tuesday], OUTCOMES)
    outcome = "tg_2plus"

    assert counts["pooled"][outcome][:2] == [2, 1]
    assert counts["by_season"]["2024-25"][outcome][:2] == [2, 1]
    assert counts["by_weekday"]["sat"][outcome][:2] == [1, 1]
    assert counts["by_weekday"]["tue"][outcome][:2] == [1, 0]
    assert counts["by_weekday"]["other"][outcome][:2] == [0, 0]


def test_league_counts_excludes_rows_without_half_time() -> None:
    with_ht = make_match(3, "A", "B", 1, 0, 1, 0)
    without_ht = make_match(4, "C", "D", 1, 0, None, None)

    counts = league_counts([with_ht, without_ht], OUTCOMES)
    assert counts["pooled"]["ht_x"][0] == 1
    assert counts["pooled"]["ft_1"][0] == 2
    assert counts["pooled"]["c7"][0] == 1


def test_top_ten_requires_minimum_sample_and_ranks_by_lower_bound() -> None:
    matches = []
    # "A" hits 10/10 at home, "B" hits 5/5, "C" has only 4 home matches (below minimum).
    matches += [make_match(day, "A", "X", 3, 0) for day in range(1, 11)]
    matches += [make_match(day, "B", "Y", 3, 0) for day in range(1, 6)]
    matches += [make_match(day, "C", "Z", 3, 0) for day in range(1, 5)]

    teams = team_counts(matches, OUTCOMES, "2024-25", None)
    ranked = top_ten(teams, OUTCOMES)
    rows = ranked["tg_2plus"]["home"]

    names = [row["team"] for row in rows]
    assert "C" not in names
    assert names[0] == "A"
    assert rows[0]["lo"] == pytest.approx(0.7225, abs=5e-4)
    assert all(row["n"] >= 5 for row in rows)


def test_top_ten_respects_limit() -> None:
    matches = []
    for index in range(14):
        team = f"T{index:02d}"
        matches += [make_match(day, team, "X", 3, 0) for day in range(1, 7)]

    teams = team_counts(matches, OUTCOMES, "2024-25", None)
    rows = top_ten(teams, OUTCOMES)["tg_2plus"]["home"]
    assert len(rows) == 10


def test_current_season_scopes_and_rolling_across_seasons() -> None:
    old = make_match(3, "A", "B", 5, 0, season="2023-24")
    new = make_match(3, "A", "C", 0, 0, season="2024-25")
    teams = team_counts([old, new], OUTCOMES, "2024-25", "2023-24")

    # Season scopes stay inside the focus season.
    assert teams["A"]["current"]["overall"]["tg_4plus"][0] == 1
    assert teams["A"]["current"]["overall"]["tg_4plus"][1] == 0

    # last 10 rolls across the season boundary.
    assert teams["A"]["current"]["last10"]["tg_4plus"][0] == 2
    assert teams["A"]["current"]["last10"]["tg_4plus"][1] == 1
