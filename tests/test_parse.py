"""CSV parsing: dates, encodings, missing half-time data, junk rows."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from pipeline.outcomes import OUTCOMES_BY_ID, evaluate
from pipeline.parse import (
    MissingColumns,
    parse_date,
    parse_season_csv,
    read_text,
    tuesday_or_saturday,
)

HEADER = "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,PSH,PSD,PSA,P>2.5,P<2.5"
BODY = "\n".join(
    [
        HEADER,
        "E1,07/08/2015,19:45,Team A,Team B,2,1,H,1,0,H,2.1,3.4,3.9,1.8,2.0",
        "E1,08/08/15,,Team C,Team D,0,0,D,,,D,2.5,3.1,2.9,,",
        "",
        ",,,,,,,,,,,,,,,",
        "",
    ]
)


def write(tmp_path: Path, body: str, name: str = "E1.csv", encoding: str = "utf-8") -> Path:
    path = tmp_path / name
    path.write_bytes(body.encode(encoding))
    return path


def test_parse_date_both_formats() -> None:
    assert parse_date("07/08/2015") == dt.date(2015, 8, 7)
    assert parse_date("07/08/15") == dt.date(2015, 8, 7)
    assert parse_date("7/8/15") == dt.date(2015, 8, 7)
    assert parse_date("2015-08-07") == dt.date(2015, 8, 7)
    assert parse_date(" 07/08/2015 ") == dt.date(2015, 8, 7)


def test_parse_date_rejects_junk_and_impossible_dates() -> None:
    assert parse_date("") is None
    assert parse_date(None) is None
    assert parse_date("31/02/2015") is None
    assert parse_date("not a date") is None


def test_season_file_parses_rows_dates_odds_and_weekday(tmp_path: Path) -> None:
    result = parse_season_csv(write(tmp_path, BODY), "2015-16")

    assert len(result.matches) == 2
    assert result.rows_total == 2
    assert result.rows_invalid == 0

    first, second = result.matches
    assert first.date == dt.date(2015, 8, 7)
    assert first.weekday == 4  # Friday
    assert first.time == "19:45"
    assert first.odds["PSH"] == pytest.approx(2.1)
    assert first.odds["P>2.5"] == pytest.approx(1.8)

    # dd/mm/yy is day-first, not 2008-... and not month-first.
    assert second.date == dt.date(2015, 8, 8)
    assert second.weekday == 5  # Saturday
    assert second.time is None


def test_rows_without_half_time_are_kept_for_ft_but_dropped_for_ht(tmp_path: Path) -> None:
    result = parse_season_csv(write(tmp_path, BODY), "2015-16")
    second = result.matches[1]

    assert result.ht_missing == 1
    assert second.hthg is None and second.htag is None
    assert evaluate(OUTCOMES_BY_ID["ft_x"], second) is True
    assert evaluate(OUTCOMES_BY_ID["ht_x"], second) is None


def test_blank_rows_and_trailing_columns_are_ignored(tmp_path: Path) -> None:
    result = parse_season_csv(write(tmp_path, BODY), "2015-16")
    assert result.rows_total == 2
    assert result.columns[0] == "Div"
    assert result.columns[-1] == "P<2.5"


def test_row_without_full_time_goals_is_invalid(tmp_path: Path) -> None:
    body = "\n".join(
        [
            "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG",
            "E1,07/08/2015,A,B,1,0,0,0",
            "E1,08/08/2015,C,D,,,,0",
        ]
    )
    result = parse_season_csv(write(tmp_path, body, "partial.csv"), "2015-16")
    assert len(result.matches) == 1
    assert result.rows_total == 2
    assert result.rows_invalid == 1


def test_cp1252_encoding_fallback(tmp_path: Path) -> None:
    body = "\n".join(
        [
            "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG",
            "E1,07/08/2015,München,Team B,1,0,0,0",
        ]
    )
    path = write(tmp_path, body, "cp.csv", encoding="cp1252")
    assert read_text(path) == body
    assert parse_season_csv(path, "2015-16").matches[0].home == "München"


def test_missing_half_time_columns_raise(tmp_path: Path) -> None:
    body = "\n".join(
        [
            "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG",
            "E1,07/08/2015,A,B,1,0",
        ]
    )
    with pytest.raises(MissingColumns) as raised:
        parse_season_csv(write(tmp_path, body, "no_ht.csv"), "2015-16")
    assert raised.value.missing == ["HTHG", "HTAG"]


def test_tuesday_or_saturday_buckets(tmp_path: Path) -> None:
    result = parse_season_csv(write(tmp_path, BODY), "2015-16")
    assert [tuesday_or_saturday(match) for match in result.matches] == ["other", "sat"]

    tuesday = parse_season_csv(write(tmp_path, BODY), "2015-16").matches[0]
    assert tuesday.date.weekday() == 4
