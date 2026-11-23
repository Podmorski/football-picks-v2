"""Phase 3: daily-best-v1 parity, freezing, settlement and public record."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from pipeline import daily_best

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
TS_MODULE = (ROOT / "web" / "lib" / "dailyBest.ts").resolve().as_uri()
NODE_SCRIPT = r"""
import fs from 'node:fs';
const m = await import(process.env.DAILY_BEST_TS);
const input = JSON.parse(fs.readFileSync(process.env.DAILY_BEST_INPUT, 'utf8'));
const selection = m.selectDaily(input.candidates, m.parseBand('1.70-2.30'));
console.log(JSON.stringify({
  rows: m.visibleDailyRows(selection, false),
  eligibleFixtures: selection.eligibleFixtures,
  inBandFixtures: selection.inBandFixtures,
  outside: selection.outside.length,
  rejected: selection.rejected,
}));
"""


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def run_ts(candidates: list[dict]) -> dict:
    if NODE is None:
        pytest.skip("node is required for the Daily-best parity check")
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump({"candidates": candidates}, handle)
        handle.close()
        env = dict(os.environ, DAILY_BEST_TS=TS_MODULE, DAILY_BEST_INPUT=handle.name)
        result = subprocess.run(
            [NODE, "--input-type=module", "-e", NODE_SCRIPT],
            env=env, capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
    finally:
        Path(handle.name).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def candidate(div: str, home: str, away: str, market: str, pc: float, odds: float) -> dict:
    return {"d": div, "h": home, "a": away, "m": market, "pc": pc, "odds": odds}


def row(market: str, home: str, away: str, pc: float, div: str = "E0") -> dict:
    return {"d": div, "k": "20:00", "h": home, "a": away, "m": market, "p": pc, "pc": pc}


def fixture(home: str, away: str, prices: dict, div: str = "E0") -> dict:
    return {"div": div, "home": home, "away": away, "kickoff": "20:00", "prices": prices}


def snapshot(fixtures: list[dict], fetched_at: str = "2026-11-24T13:00:00+00:00") -> dict:
    return {"round_date": "2026-11-24", "fetched_at": fetched_at, "fixtures": fixtures, "started_not_priced": []}


def document(rows: list[dict], date: str = "2026-11-24") -> dict:
    return {"date": date, "rows": rows}


def parity_candidates() -> list[dict]:
    candidates = []
    # 8 in-band fixtures plus the tie/band cases stay inside the 12 cap.
    for index in range(8):
        candidates.append(candidate("E0", f"H{index}", f"A{index}", "M", 0.60 - index * 0.01, 1.90))
    # Preferred band beats a shorter, higher-pc candidate on the same fixture.
    candidates.append(candidate("E0", "Band", "Choice", "SHORT", 0.90, 1.30))
    candidates.append(candidate("E0", "Band", "Choice", "BAND", 0.55, 1.85))
    # Outside-band nearest boundary (1.31 is closer than 4.50 on the same fixture).
    candidates.append(candidate("E0", "Near", "Boundary", "M", 0.50, 1.31))
    candidates.append(candidate("E0", "Near", "Boundary", "M2", 0.60, 4.50))
    # pc/EV tie-break inside the band.
    candidates.append(candidate("E1", "Tie", "Ev", "LOW", 0.50, 1.80))
    candidates.append(candidate("E1", "Tie", "Ev", "HIGH", 0.50, 2.00))
    # Rejected candidates.
    candidates.append(candidate("E1", "Too", "Short", "M", 0.95, 1.05))
    return candidates


def test_python_and_typescript_selection_are_identical() -> None:
    candidates = parity_candidates()
    python_selection = daily_best.select_daily(candidates)
    python_rows = daily_best.visible_rows(python_selection)
    typescript = run_ts(candidates)
    assert [(r["d"], r["h"], r["a"], r["m"]) for r in python_rows] == [
        (r["d"], r["h"], r["a"], r["m"]) for r in typescript["rows"]
    ]
    assert python_selection["eligible_fixtures"] == typescript["eligibleFixtures"]
    assert python_selection["in_band_fixtures"] == typescript["inBandFixtures"]
    assert len(python_selection["outside"]) == typescript["outside"]
    assert python_selection["rejected"] == typescript["rejected"]
    # Preferred band wins and the nearest outside boundary comes before the far one.
    by_fixture = {(r["h"], r["m"]) for r in python_rows}
    assert ("Band", "BAND") in by_fixture and ("Band", "SHORT") not in by_fixture
    assert ("Tie", "HIGH") in by_fixture and ("Tie", "LOW") not in by_fixture
    assert ("Near", "M") in by_fixture and ("Near", "M2") not in by_fixture


def test_twelve_fixture_cap_matches_typescript() -> None:
    candidates = [candidate("E0", f"H{index}", f"A{index}", "M", 0.60, 1.90) for index in range(15)]
    python_rows = daily_best.visible_rows(daily_best.select_daily(candidates))
    typescript = run_ts(candidates)
    assert len(python_rows) == len(typescript["rows"]) == 12
    assert len({(r["d"], r["h"], r["a"]) for r in python_rows}) == 12
    assert [(r["h"], r["a"]) for r in python_rows] == [(r["h"], r["a"]) for r in typescript["rows"]]


def test_candidate_menu_excludes_started_correct_score_and_unpriced() -> None:
    doc = document([
        row("M", "A", "B", 0.60), row("CORRECT_SCORE:1:0", "A", "B", 0.99),
        row("M", "C", "D", 0.60), row("M", "E", "F", 0.60), row("M", "G", "H", 0.60),
    ])
    snap = snapshot([
        fixture("A", "B", {"M": 2.0, "CORRECT_SCORE:1:0": 9.0}),
        fixture("C", "D", {"M": 1.05}),
        fixture("E", "F", {}),
        fixture("G", "H", {"M": 2.0}),
    ])
    snap["started_not_priced"] = [{"div": "E0", "home": "G", "away": "H"}]
    pool = daily_best.daily_pool(daily_best.candidate_menu(doc, snap))
    assert {(item["h"], item["m"]) for item in pool} == {("A", "M")}


def test_freeze_is_pre_activation_exempt_then_immutable(tmp_path: Path) -> None:
    prices = tmp_path / "prices"
    first_rows = [row("M", "A", "B", 0.60), row("M", "C", "D", 0.60)]
    first_snap = snapshot([fixture("A", "B", {"M": 1.90}), fixture("C", "D", {"M": 1.90})])
    assert daily_best.ensure_daily_best("2026-11-22", document(first_rows, "2026-11-22"), first_snap, prices) is None
    assert not (prices / "daily-best").exists()

    frozen = daily_best.ensure_daily_best("2026-11-24", document(first_rows), first_snap, prices)
    assert frozen is not None and frozen["selected"] == 2
    path = prices / "daily-best" / "2026-11-24.json"
    before = path.read_bytes()
    changed = snapshot([fixture("A", "B", {"M": 3.0}), fixture("C", "D", {"M": 3.0})], "2026-11-24T17:00:00+00:00")
    again = daily_best.ensure_daily_best("2026-11-24", document(first_rows), changed, prices)
    assert again == frozen
    assert path.read_bytes() == before
    activation = json.loads((prices / "daily-best" / "activation.json").read_text(encoding="utf-8"))
    assert activation["marker"] == "daily-best-v1"
    assert activation["activated_round"] == "2026-11-24"
    assert activation["activation_date"] == daily_best.ACTIVATION_DATE


def test_missing_post_activation_file_is_actionable(tmp_path: Path) -> None:
    prices = tmp_path / "prices"
    (prices / "rounds").mkdir(parents=True)
    (prices / "daily-best").mkdir()
    (prices / "rounds" / "2026-11-24.json").write_text(json.dumps({
        "round_date": "2026-11-24", "fixtures": [{"div": "E0"}], "started_not_priced": [],
    }), encoding="utf-8")
    (prices / "daily-best" / "activation.json").write_text(json.dumps({
        "marker": "daily-best-v1", "rule_version": "daily-best-v1",
        "activation_date": "2026-11-23", "activated_round": "2026-11-24",
    }), encoding="utf-8")
    assert daily_best.missing_daily_best(prices) == ["2026-11-24"]
    with pytest.raises(daily_best.DailyBestReadinessError, match="2026-11-24"):
        daily_best.validate_daily_best(prices)
    code = daily_best.main([
        "aggregate", "--prices-dir", str(prices), "--picks-dir", str(tmp_path / "picks"),
        "--web-dir", str(tmp_path / "web"),
    ])
    assert code == 4


def _write_activation(prices: Path, activated_round: str = "2026-11-24") -> None:
    directory = prices / "daily-best"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "activation.json").write_text(json.dumps({
        "schema_version": 1, "marker": "daily-best-v1", "rule_version": "daily-best-v1",
        "activation_date": daily_best.ACTIVATION_DATE, "activated_round": activated_round,
    }), encoding="utf-8")


def _frozen_round(date: str, rows: list[dict], fetched_at: str = "2026-11-24T13:00:00+00:00") -> dict:
    return {
        "schema_version": 1, "rule_version": "daily-best-v1", "activation_marker": "daily-best-v1",
        "round_date": date, "snapshot_identity": {"round_date": date, "fetched_at": fetched_at},
        "band": {"low": 1.70, "high": 2.30}, "min_odds": 1.20, "limit": 12,
        "eligible_counts": {"fixtures": len(rows), "in_band": len(rows), "outside": 0, "rejected": 0},
        "selected": len(rows), "in_band_selected": len(rows), "fallback_selected": 0, "rows": rows,
    }


def _write_picks(picks: Path, date: str, statuses: dict[tuple, str]) -> None:
    picks.mkdir(parents=True, exist_ok=True)
    rows = [
        {"d": d, "h": h, "a": a, "m": m, "st": status}
        for (d, h, a, m), status in statuses.items()
    ]
    (picks / f"{date}.json").write_text(json.dumps({"date": date, "rows": rows}), encoding="utf-8")


def test_settlement_arithmetic_excludes_pending(tmp_path: Path) -> None:
    prices = tmp_path / "prices"; picks = tmp_path / "picks"
    (prices / "daily-best").mkdir(parents=True)
    _write_activation(prices)
    frozen_rows = [
        {"d": "E0", "h": "A", "a": "B", "m": "M", "pc": 0.5, "odds": 2.0, "fair": 2.0, "group": "Result"},
        {"d": "E0", "h": "C", "a": "D", "m": "M", "pc": 0.4, "odds": 2.5, "fair": 2.5, "group": "Goals"},
        {"d": "E0", "h": "E", "a": "F", "m": "M", "pc": 0.6, "odds": 1.8, "fair": 1.8, "group": "Goals"},
        {"d": "E0", "h": "G", "a": "H", "m": "M", "pc": 0.3, "odds": 3.0, "fair": 3.0, "group": "BTTS"},
    ]
    (prices / "daily-best" / "2026-11-24.json").write_text(json.dumps(_frozen_round("2026-11-24", frozen_rows)), encoding="utf-8")
    _write_picks(picks, "2026-11-24", {
        ("E0", "A", "B", "M"): "landed",
        ("E0", "C", "D", "M"): "lost",
        ("E0", "E", "F", "M"): "void",
        ("E0", "G", "H", "M"): "pending",
    })
    web = tmp_path / "web"
    payload = daily_best.write(prices, picks, web)
    cumulative = payload["cumulative"]
    assert (cumulative["selected"], cumulative["settled"], cumulative["landed"], cumulative["lost"], cumulative["void"], cumulative["pending"]) == (4, 3, 1, 1, 1, 1)
    assert cumulative["staked"] == pytest.approx(3.0)
    assert cumulative["returned"] == pytest.approx(3.0)
    assert cumulative["net"] == pytest.approx(0.0)
    assert cumulative["roi"] == pytest.approx(0.0)
    assert cumulative["pending_exposure"] == pytest.approx(1.0)
    assert payload["rounds"][0]["source_pending"] is True
    assert payload["rounds"][0]["state"] == "partial"
    assert cumulative["interval_state"] == "insufficient forward rounds for an interval"
    assert cumulative["return_ci"] == [None, None]
    text = (web / "daily-best-record.json").read_text(encoding="utf-8")
    assert '"odds":' not in text and '"prices"' not in text
    assert "forward frozen-price paper return" in text.lower()


def test_thirty_settled_rounds_produce_a_whole_round_interval(tmp_path: Path) -> None:
    prices = tmp_path / "prices"; picks = tmp_path / "picks"
    (prices / "daily-best").mkdir(parents=True)
    _write_activation(prices)
    for day in range(1, 31):
        date = f"2026-12-{day:02d}" if day <= 31 else ""
        rows = [{"d": "E0", "h": f"H{day}", "a": f"A{day}", "m": "M", "pc": 0.5, "odds": 2.0, "fair": 2.0, "group": "Result"}]
        (prices / "daily-best" / f"{date}.json").write_text(json.dumps(_frozen_round(date, rows)), encoding="utf-8")
        _write_picks(picks, date, {("E0", f"H{day}", f"A{day}", "M"): "landed"})
    payload = daily_best.aggregate(prices, picks)
    assert payload["cumulative"]["settled_rounds"] == 30
    assert payload["cumulative"]["interval_state"] == "available"
    assert payload["cumulative"]["return_ci"][0] is not None
    assert payload["cumulative"]["mean_actual_odds"] == pytest.approx(2.0)
    assert payload["cumulative"]["median_actual_odds"] == pytest.approx(2.0)


def test_interactive_exploration_cannot_change_the_frozen_record() -> None:
    source = read("web/components/VettedList.tsx")
    assert "frozenDefault ? frozenItems : isAny ? interactiveDaily : refined.rows" in source
    assert "Frozen Daily-best-v1 list" in source
    assert "Exploration view — not part of the frozen Daily-best record." in source
    assert "Pre-activation preview; not part of the forward record." in source
    aggregate = read("pipeline/daily_best.py")
    assert 'daily_dir.glob("*.json")' in aggregate
    assert "selectDaily(" not in aggregate


def test_public_record_has_no_actual_prices_or_combinations(tmp_path: Path) -> None:
    prices = tmp_path / "prices"; picks = tmp_path / "picks"
    (prices / "daily-best").mkdir(parents=True)
    _write_activation(prices)
    rows = [{"d": "E0", "h": "A", "a": "B", "m": "M", "pc": 0.5, "odds": 2.0, "fair": 2.0, "group": "Result"}]
    (prices / "daily-best" / "2026-11-24.json").write_text(json.dumps(_frozen_round("2026-11-24", rows)), encoding="utf-8")
    _write_picks(picks, "2026-11-24", {("E0", "A", "B", "M"): "landed"})
    payload = daily_best.aggregate(prices, picks)
    text = json.dumps(payload, sort_keys=True)
    assert '"odds":' not in text
    assert '"price"' not in text and '"prices"' not in text
    assert '"combined' not in text
    assert payload["prices_published"] is False


def test_activation_marker_and_missing_validation_are_separate(tmp_path: Path) -> None:
    prices = tmp_path / "prices"
    (prices / "rounds").mkdir(parents=True)
    (prices / "rounds" / "2026-11-22.json").write_text(json.dumps({
        "round_date": "2026-11-22", "fixtures": [{"div": "E0"}], "started_not_priced": [],
    }), encoding="utf-8")
    assert daily_best.missing_daily_best(prices) == []
    assert daily_best.load_activation(prices) is None


def test_report_rounds_and_preload_contracts() -> None:
    report = read("web/app/report/page.tsx")
    assert "Daily best — forward actual-price record" in report
    assert "Legacy research · STRICT_checks TYPE_RULE cohort" in report
    rounds = read("web/app/rounds/page.tsx")
    assert "Frozen Daily best" in rounds
    assert "Legacy 58% cohort" in rounds
    preload = read("web/scripts/fetch-prices.mjs")
    assert "daily-best-private.json" in preload
    assert "required frozen Daily best data missing" in preload
    ignored = read(".gitignore")
    assert "web/public/data/daily-best-private.json" in ignored
    workflow = read(".github/workflows/update.yml")
    assert "pipeline.daily_best aggregate" in workflow
