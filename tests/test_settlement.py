"""Next-day settlement: due dates, idempotence, companions, sources and reports."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from pipeline import alerts, ranking
from pipeline.run import existing_upcoming
from pipeline.run_model import (
    log_settlement,
    parse_args,
    rebuild_round_reports,
    settle_round_files,
    settlement_due_date,
    settlement_eligible,
)

ROOT = Path(__file__).resolve().parents[1]
SAT = dt.date(2026, 11, 21)
SUN = dt.date(2026, 11, 22)
MON = dt.date(2026, 11, 23)
TUE = dt.date(2026, 11, 24)
WED = dt.date(2026, 11, 25)


def row(market: str = "RESULT:1", home: str = "A", away: str = "B") -> dict:
    return {
        "d": "E0", "k": "15:00", "h": home, "a": away, "m": market,
        "p": 0.60, "pc": 0.60, "pl": 0.60, "pp": 0.60,
        "lr": 0.45, "ln": 1000, "hr": 0.55, "hn": 20,
        "ar": 0.55, "an": 20, "c": "Medium", "s": 0.0,
        "st": "pending", "ht": None, "ft": None,
    }


def document(rows: list[dict], date: dt.date = SAT) -> dict:
    return {
        "date": date.isoformat(), "label": date.isoformat(), "weekday": date.strftime("%A"),
        "kind": "round", "fixtures": len({(item["h"], item["a"]) for item in rows}),
        "leagues": 1, "markets": 178, "rows": rows,
    }


def result(date: dt.date = SAT, home: str = "A", away: str = "B", ht: bool = True) -> dict:
    return {(date.isoformat(), home, away): (2, 1, 1 if ht else None, 0 if ht else None)}


def model_fields(path: Path) -> list[dict]:
    return [
        {key: value for key, value in item.items() if key not in {"st", "ht", "ft"}}
        for item in ranking.load(path)["rows"]
    ]


def test_next_day_due_dates_and_future_exclusion() -> None:
    assert settlement_due_date(SAT) == SUN
    assert settlement_due_date(SUN) == MON
    assert settlement_due_date(TUE) == WED
    assert settlement_eligible(SAT, SUN) is True
    assert settlement_eligible(SUN, MON) is True
    assert settlement_eligible(TUE, WED) is True
    assert settlement_eligible(SAT, SAT) is False
    assert settlement_eligible(SUN, SAT) is False
    assert settlement_eligible(dt.date(2026, 11, 20), SAT) is False


def test_repeated_settlement_is_idempotent_and_preserves_predictions_and_companion(tmp_path: Path) -> None:
    picks = tmp_path / "picks"
    web = tmp_path / "web"
    main = document([row("RESULT:1"), row("RESULT:2")])
    full = document([row("HALF_RESULT:I1")])
    ranking.publish(main, picks, web)
    ranking.publish_full(full, picks, web)
    main_before = model_fields(picks / "2026-11-21.json")
    full_before = model_fields(picks / "2026-11-21.full.json")

    first = settle_round_files(SAT, result(), SUN, picks, web)
    assert first and first["changed"] is True
    assert (first["main"]["landed"], first["main"]["lost"], first["main"]["void"]) == (1, 1, 0)
    assert (first["full"]["landed"], first["full"]["lost"], first["full"]["void"]) == (1, 0, 0)
    assert first["pending"] == 0
    assert model_fields(picks / "2026-11-21.json") == main_before
    assert model_fields(picks / "2026-11-21.full.json") == full_before

    index, best = rebuild_round_reports(picks, web)
    assert index["rounds"][0]["settled_count"] == 2
    assert index["rounds"][0]["hits"] == 1
    assert (web / "rounds" / "index.json").exists()
    assert not (web / "index.json").exists()
    assert best["cumulative"]["passing"] == 1
    assert best["cumulative"]["settled"] == 1
    assert best["cumulative"]["landed"] == 1

    main_bytes = (picks / "2026-11-21.json").read_bytes()
    full_bytes = (picks / "2026-11-21.full.json").read_bytes()
    second = settle_round_files(SAT, result(), SUN, picks, web)
    assert second and second["changed"] is False
    assert (second["landed"], second["lost"], second["void"]) == (0, 0, 0)
    assert (picks / "2026-11-21.json").read_bytes() == main_bytes
    assert (picks / "2026-11-21.full.json").read_bytes() == full_bytes


def test_missing_source_stays_pending_but_available_ft_can_void_ht_market(tmp_path: Path, capsys) -> None:
    picks = tmp_path / "picks"
    web = tmp_path / "web"
    main = document([row("RESULT:1"), row("HALF_RESULT:I1"), row("RESULT:1", "C", "D")])
    ranking.publish(main, picks, web)
    outcome = settle_round_files(SAT, result(ht=False), SUN, picks, web)
    assert outcome and outcome["changed"] is True
    assert (outcome["main"]["landed"], outcome["main"]["void"]) == (1, 1)
    assert outcome["pending_without_results"] == 1
    assert outcome["pending_with_results"] == 0
    assert outcome["missing_fixtures"] == 1
    statuses = [item["st"] for item in ranking.load(picks / "2026-11-21.json")["rows"]]
    assert statuses == ["landed", "void", "pending"]
    log_settlement(SAT, outcome)
    assert "SOURCE PENDING" in capsys.readouterr().out
    assert alerts.stale_settle(SAT, 1, outcome["changed"], outcome["pending_with_results"]) is None


def test_no_source_result_changes_nothing_and_never_marks_void(tmp_path: Path) -> None:
    picks = tmp_path / "picks"
    web = tmp_path / "web"
    ranking.publish(document([row("RESULT:1"), row("HALF_RESULT:I1")]), picks, web)
    before = (picks / "2026-11-21.json").read_bytes()
    outcome = settle_round_files(SAT, {}, SUN, picks, web)
    assert outcome and outcome["changed"] is False
    assert outcome["void"] == 0
    assert outcome["pending_without_results"] == 2
    assert outcome["missing_fixtures"] == 1
    assert (picks / "2026-11-21.json").read_bytes() == before


def test_future_round_is_not_settled_even_if_a_result_key_exists(tmp_path: Path) -> None:
    picks = tmp_path / "picks"
    web = tmp_path / "web"
    ranking.publish(document([row()], date=SUN), picks, web)
    outcome = settle_round_files(SUN, result(date=SUN), SUN, picks, web)
    assert outcome == {"eligible": False, "changed": False}
    assert ranking.load(picks / "2026-11-22.json")["rows"][0]["st"] == "pending"


def test_settle_only_cli_and_workflow_retries_use_normal_report_commit_deploy_path() -> None:
    assert parse_args(["--settle-only"]).settle_only is True
    source = (ROOT / ".github" / "workflows" / "update.yml").read_text(encoding="utf-8")
    for cron in ("0 12 * * 0", "0 18 * * 0", "0 6 * * 1", "0 12 * * 1", "0 6 * * 3", "0 12 * * 3"):
        assert f"cron: '{cron}'" in source
    assert "python -m pipeline.run_model --settle-only --skip-backtest --skip-picker-backtest" in source
    ordered = (
        "python -m pipeline.run\n",
        "python -m pipeline.run_model --settle-only",
        "python -m pipeline.mozzart.value_record",
        "Commit changed data",
        "Trigger Vercel deploy hook",
    )
    positions = [source.index(needle) for needle in ordered]
    assert positions == sorted(positions)
    for existing in ("0 10 * * 2", "0 15 * * 5", "0 5 * * 6", "0 8 * * 0"):
        assert f"cron: '{existing}'" in source


def test_data_refresh_preserves_upcoming_predictions_for_settle_only(tmp_path: Path) -> None:
    path = tmp_path / "E0.json"
    path.write_text('{"upcoming":[{"date":"2026-11-22"}]}', encoding="utf-8")
    assert existing_upcoming(path) == [{"date": "2026-11-22"}]
    source = (ROOT / "pipeline" / "run.py").read_text(encoding="utf-8")
    assert source.count('"upcoming": existing_upcoming(') == 2


def test_real_round_is_never_rebuilt_as_an_example() -> None:
    source = (ROOT / "pipeline" / "run_model.py").read_text(encoding="utf-8")
    assert 'published_example.get("kind", "round") == "round"' in source
    assert "using the already published round without rebuilding" in source
    assert "if not settle_only:" in source
