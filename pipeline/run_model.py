"""Build the model, publish rounds in both views, settle them, refresh site data.

Usage: python -m pipeline.run_model [--today DATE] [--skip-backtest] [--no-publish]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

from .config import FIRST_SEASON_START, RAW_DIR, WEB_DATA_DIR, load_divisions, load_extras, season_code, season_label
from .extras import parse_extra_csv
from .fixtures import Fixture, current_or_next_round_date, fixtures_for_date, last_saturday, parse_fixtures
from . import ranking
from .model import backtest, live, ranking_backtest
from .parse import parse_season_csv
from .picks import read_results
from .run import cached_seasons

PICKS_DIR = Path(__file__).resolve().parents[1] / "picks"
MODEL_DIR = Path(__file__).resolve().parent / "model"
DECISIONS_FILE = MODEL_DIR / "decisions.json"
MODEL_JSON = WEB_DATA_DIR / "model.json"
RECORD_JSON = WEB_DATA_DIR / "record.json"
ROUNDS_DIR = WEB_DATA_DIR / "rounds"
BY_PLAY_DIR = WEB_DATA_DIR / "by-play"
TEAMS_DIR = WEB_DATA_DIR / "teams"

PICK_CONFIG = {
    "max_probability": 0.65,
    "min_lift": 0.08,
    "lift_min_probability": 0.45,
    "top_n": 15,
    "min_samples": 8,
    "agreement": 0.10,
    "max_same_play": 3,
}
UPCOMING_DAYS = 21


def season_start(match) -> int:
    return int(str(match.season).split("-")[0])


def load_by_division(raw_dir: Path, divisions, extras, current_start: int) -> dict[str, list]:
    by_division: dict[str, list] = defaultdict(list)
    for league in divisions:
        for start in range(FIRST_SEASON_START, current_start + 1):
            path = raw_dir / season_code(start) / f"{league.code}.csv"
            if not path.exists():
                continue
            parsed = parse_season_csv(path, season_label(start))
            by_division[league.code].extend(parsed.matches)
    for league in extras:
        path = raw_dir / "new" / f"{league.code}.csv"
        if not path.exists():
            continue
        parsed_extra = parse_extra_csv(path)
        by_division[league.code].extend(parsed_extra.matches)
    return by_division


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")


def overall_bins(selected: dict) -> dict:
    rows = []
    for position in range(backtest.BIN_COUNT):
        total = sum(entry["bins"][position]["n"] for entry in selected.values())
        hits = sum(entry["bins"][position]["hits"] for entry in selected.values())
        low = backtest.BIN_LOW + backtest.BIN_WIDTH * position
        rows.append(
            {
                "bin": f"{int(round(low * 100))}-{int(round((low + backtest.BIN_WIDTH) * 100))}",
                "shown": round(low + backtest.BIN_WIDTH / 2, 4),
                "n": total,
                "hits": hits,
                "landed": round(hits / total, 4) if total else None,
            }
        )
    return {"bins": rows}


def overall_ablation(groups: dict[str, dict]) -> dict:
    total = sum(entry["n"] for entry in groups.values())
    output: dict[str, dict] = {}
    for component in backtest.COMPONENTS:
        brier = (
            sum((entry["brier"][component] or 0.0) * entry["n"] for entry in groups.values()) / total if total else None
        )
        logloss = (
            sum((entry["logloss"][component] or 0.0) * entry["n"] for entry in groups.values()) / total if total else None
        )
        output[component] = {
            "brier": round(brier, 6) if brier is not None else None,
            "logloss": round(logloss, 6) if logloss is not None else None,
        }
    return output


def calibration_overall(selected: dict) -> dict:
    return overall_bins(selected)


def historical_fixtures(by_division: dict[str, list], date: dt.date) -> list[Fixture]:
    fixtures: list[Fixture] = []
    for code, matches in by_division.items():
        for match in matches:
            if match.date == date:
                fixtures.append(
                    Fixture(div=code, date=date, time=match.time, home=match.home, away=match.away, odds=match.odds)
                )
    return fixtures


def build_predictors(by_division: dict[str, list], cutoff: dt.date, half_life: float, k: float, decisions: dict) -> dict:
    predictors = {}
    for code, matches in by_division.items():
        if not matches:
            continue
        predictors[code] = live.build_predictor(matches, cutoff, half_life, k, decisions)
    return predictors


def is_settle_only(day: dt.date) -> bool:
    """Monday's run settles results only; it never publishes a new round."""
    return day.weekday() == 0


def market_band_map(ranking_bt: dict) -> dict:
    """Group|band -> the row confidence_badge expects (landed, shown, n)."""
    return {
        f"{row['group']}|{row.get('level') or row.get('band')}": {
            "landed": row["hit_rate"],
            "shown": row["mean_probability"],
            "n": row["picks"],
        }
        for row in ranking_bt.get("groups", [])
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="pipeline.run_model", description="Build model and publish rounds")
    parser.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    parser.add_argument("--skip-backtest", action="store_true", help="reuse decisions.json / model.json")
    parser.add_argument("--no-publish", action="store_true", help="compute but do not write round files")
    parser.add_argument("--skip-picker-backtest", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    current_start = cached_seasons(RAW_DIR)
    if current_start is None:
        print("STOP: no cached season files; run python -m pipeline.run first")
        return 2

    divisions = load_divisions()
    extras = load_extras()
    ft_only = {league.code for league in extras}
    league_names = {league.code: league.name for league in divisions + extras}
    by_division = load_by_division(RAW_DIR, divisions, extras, current_start)
    all_matches = [match for matches in by_division.values() for match in matches]
    print(f"loaded {len(all_matches)} matches across {len(by_division)} leagues (incl. {len(extras)} FT-only)")

    if args.skip_backtest and DECISIONS_FILE.exists() and MODEL_JSON.exists():
        decisions = json.loads(DECISIONS_FILE.read_text(encoding="utf-8"))
        model_payload = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
        calibration = model_payload["calibration"]
        print("reused existing decisions.json / model.json")
    else:
        divisions = [backtest.prepare(code, matches, season_start) for code, matches in sorted(by_division.items()) if matches]
        tuning = backtest.tune_hyperparameters(divisions)
        best = tuning["best"]
        print(f"hyperparameters: half-life {best['half_life_days']:.0f}d, k={best['k']:.0f}")
        board = backtest.run(divisions, best["half_life_days"], best["k"])
        decisions = backtest.build_decisions(board, tuning)
        groups = decisions["groups"]
        selected = backtest.selected_bin_table(board, groups)
        calibration = {"overall": calibration_overall(selected), "groups": selected}
        model_payload = {
            "backtest": {"seasons": decisions["backtest_seasons"], "fixtures": decisions["fixtures"]},
            "hyperparameters": tuning,
            "ablation": {"overall": overall_ablation(groups), "groups": groups},
            "calibration": calibration,
            "decisions": {
                group: {
                    key: entry[key]
                    for key in ("keep_counts", "keep_goals", "keep_odds", "keep_calibration", "live_component")
                }
                for group, entry in groups.items()
            },
            "full_worse_than_base_count": decisions["full_worse_than_base_count"],
            "missing_odds": decisions["missing_odds"],
        }
        write_json(DECISIONS_FILE, decisions)
        write_json(MODEL_JSON, model_payload)
        print(f"backtest fixtures: {decisions['fixtures']:,}")
        print(
            "outcomes where full model is worse than base on Brier: "
            f"{decisions['full_worse_than_base_count']} / {len(decisions['outcomes'])}"
        )
        print(f"fixtures without odds: {decisions['missing_odds']['fixtures_without_odds']:,}")

    hyper = decisions["hyperparameters"]["best"]
    half_life = float(hyper["half_life_days"])
    k = float(hyper["k"])
    market_bands = market_band_map(model_payload.get("ranking_backtest", {}))
    market_calibration = dict(model_payload.get("ranking_backtest", {}).get("calibration", {}))
    market_calibration["__k__"] = k
    settle_only = is_settle_only(today)

    fixtures = parse_fixtures(RAW_DIR / "fixtures.csv")
    divisions_set = {league.code for league in divisions}
    results = read_results(all_matches)

    round_date = current_or_next_round_date(today)
    round_fixtures = fixtures_for_date(fixtures, round_date, divisions_set)
    round_path = PICKS_DIR / f"{round_date.isoformat()}.json"

    predictors = build_predictors(by_division, round_date, half_life, k, decisions)

    if round_path.exists():
        existing = ranking.load(round_path)
    else:
        existing = None

    action = ranking.round_action(existing, round_fixtures)
    if settle_only and action == "publish":
        action = "settle"
        existing = None
    if action == "settle" and existing is not None:
        ranking.settle_document(existing, results, today)
        if not args.no_publish:
            ranking.publish(existing, PICKS_DIR, ROUNDS_DIR)
        print(f"round {round_date}: already published, settled only")
    elif action == "settle" and settle_only:
        print(f"round {round_date}: Monday settle-only run, nothing published")
    elif action == "publish":
        document = ranking.build_ranking(predictors, round_fixtures, round_date, {**market_calibration, "__bands__": market_bands})
        document["kind"] = "round"
        document["market_bands"] = market_bands
        ranking.settle_document(document, results, today)
        if not args.no_publish:
            ranking.publish(document, PICKS_DIR, ROUNDS_DIR)
        replaced = " (replaced an empty round file)" if existing is not None else ""
        print(f"round {round_date}: published {len(document['rows'])} rows{replaced}")
    else:
        print(f"round {round_date}: no fixtures published by the source, nothing to publish")

    example_date = last_saturday(today)
    example_fixtures = fixtures_for_date(fixtures, example_date, divisions_set) or historical_fixtures(
        by_division, example_date
    )
    example_predictors = build_predictors(by_division, example_date, half_life, k, decisions)
    example = ranking.build_ranking(example_predictors, example_fixtures, example_date, {**market_calibration, "__bands__": market_bands})
    example["kind"] = "example"
    example["market_bands"] = market_bands
    ranking.settle_document(example, results, today)
    print(f"example round {example_date}: {len(example['rows'])} rows")
    if not args.no_publish and example["rows"]:
        ranking.publish(example, PICKS_DIR, ROUNDS_DIR)

    for path in sorted(PICKS_DIR.glob("*.json")):
        stored = ranking.load(path)
        if stored["date"] in (round_date.isoformat(), example_date.isoformat()):
            continue
        if ranking.settle_document(stored, results, today) and not args.no_publish:
            ranking.publish(stored, PICKS_DIR, ROUNDS_DIR)

    if args.no_publish:
        return 0

    index = ranking.rebuild_index(PICKS_DIR, ROUNDS_DIR)
    write_json(WEB_DATA_DIR / "markets.json", ranking.market_catalogue())

    ranking_bt = None
    if args.skip_backtest and args.skip_picker_backtest and MODEL_JSON.exists():
        existing_model = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
        ranking_bt = existing_model.get("ranking_backtest")
        if ranking_bt:
            print("reused existing ranking backtest")
    else:
        ranking_bt = ranking_backtest.run(
            {code: by_division[code] for code in by_division if code in {league.code for league in divisions}},
            half_life,
            k,
        )
        model_payload["ranking_backtest"] = ranking_bt
        write_json(MODEL_JSON, model_payload)
        ranking_bt = ranking_backtest.run(
            {code: by_division[code] for code in by_division if code in {league.code for league in divisions}},
            half_life,
            k,
        )
        model_payload["ranking_backtest"] = ranking_bt
        write_json(MODEL_JSON, model_payload)
        for row in ranking_bt["groups"]:
            print(
                f"ranking backtest {row['group'][:26]:26s} {row['level']:8s} n={row['picks']:6d} "
                f"pred={row['mean_probability'] * 100:5.1f}% hit={row['hit_rate'] * 100:5.1f}%"
            )

    upcoming = [
        fixture
        for fixture in fixtures
        if fixture.div in divisions_set and today <= fixture.date <= today + dt.timedelta(days=UPCOMING_DAYS)
    ]
    by_div: dict[str, list] = defaultdict(list)
    for fixture in upcoming:
        by_div[fixture.div].append(fixture)

    for code, items in by_div.items():
        teams_path = TEAMS_DIR / f"{code}.json"
        if not teams_path.exists():
            continue
        teams_document = json.loads(teams_path.read_text(encoding="utf-8"))
        built = ranking.build_ranking(predictors, items, round_date, market_bands)
        best: dict[tuple[str, str], dict] = {}
        for row in ranking.rank_rows(built["rows"], band=ranking.DEFAULT_BAND):
            best.setdefault((row["h"], row["a"]), row)
        teams_document["upcoming"] = [
            {
                "date": fixture.date.isoformat(),
                "time": fixture.time,
                "home": fixture.home,
                "away": fixture.away,
                "best": best.get((fixture.home, fixture.away)),
            }
            for fixture in sorted(items, key=lambda item: (item.date, item.home))
        ]
        write_json(teams_path, teams_document)

    totals = {
        "rounds": len(index["rounds"]),
        "picks": sum(row["picks"] for row in index["rounds"]),
        "hits": sum(row["hits"] for row in index["rounds"]),
        "settled": sum(row["settled_count"] for row in index["rounds"]),
    }
    totals["hit_rate"] = round(totals["hits"] / totals["settled"], 4) if totals["settled"] else None
    payload = {"calibration": calibration, "rounds": index["rounds"], "totals": totals}
    if ranking_bt is not None:
        payload["ranking_backtest"] = ranking_bt
    write_json(RECORD_JSON, payload)

    print(f"rounds published: {totals['rounds']}, picks: {totals['picks']}, settled: {totals['settled']}, hits: {totals['hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
