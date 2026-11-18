"""Build the model, publish rounds, settle them and refresh the site data.

Usage: python -m pipeline.run_model [--today DATE] [--skip-backtest] [--no-publish]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

from .config import FIRST_SEASON_START, RAW_DIR, WEB_DATA_DIR, load_leagues, season_code, season_label
from .fixtures import fixtures_for_date, last_saturday, next_round_date, parse_fixtures
from .model import backtest, live
from .model.blend import GROUP_NAMES
from .parse import parse_season_csv
from .picks import build_round, publish, read_results, rebuild_index, settle_document
from .run import cached_seasons

PICKS_DIR = Path(__file__).resolve().parents[1] / "picks"
MODEL_DIR = Path(__file__).resolve().parent / "model"
DECISIONS_FILE = MODEL_DIR / "decisions.json"
MODEL_JSON = WEB_DATA_DIR / "model.json"
RECORD_JSON = WEB_DATA_DIR / "record.json"
ROUNDS_DIR = WEB_DATA_DIR / "rounds"
TEAMS_DIR = WEB_DATA_DIR / "teams"

PICK_CONFIG = {"max_probability": 0.65, "top_n": 15, "min_samples": 8, "agreement": 0.10}
UPCOMING_DAYS = 21


def season_start(match) -> int:
    return int(str(match.season).split("-")[0])


def load_by_division(raw_dir: Path, leagues, current_start: int) -> dict[str, list]:
    by_division: dict[str, list] = defaultdict(list)
    for league in leagues:
        for start in range(FIRST_SEASON_START, current_start + 1):
            path = raw_dir / season_code(start) / f"{league.code}.csv"
            if not path.exists():
                continue
            parsed = parse_season_csv(path, season_label(start))
            by_division[league.code].extend(parsed.matches)
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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="pipeline.run_model", description="Build model and publish rounds")
    parser.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    parser.add_argument("--skip-backtest", action="store_true", help="reuse decisions.json / model.json")
    parser.add_argument("--no-publish", action="store_true", help="compute but do not write round files")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    current_start = cached_seasons(RAW_DIR)
    if current_start is None:
        print("STOP: no cached season files; run python -m pipeline.run first")
        return 2

    leagues = load_leagues()
    league_names = {league.code: league.name for league in leagues}
    by_division = load_by_division(RAW_DIR, leagues, current_start)
    all_matches = [match for matches in by_division.values() for match in matches]
    print(f"loaded {len(all_matches)} matches across {len(by_division)} divisions")

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
            "decisions": {group: {key: entry[key] for key in ("keep_counts", "keep_goals", "keep_odds", "keep_calibration", "live_component")} for group, entry in groups.items()},
            "full_worse_than_base_count": decisions["full_worse_than_base_count"],
        }
        write_json(DECISIONS_FILE, decisions)
        write_json(MODEL_JSON, model_payload)
        print(f"backtest fixtures: {decisions['fixtures']:,}")
        print(f"outcomes where full model is worse than base on Brier: {decisions['full_worse_than_base_count']} / {len(decisions['outcomes'])}")

    hyper = decisions["hyperparameters"]["best"]
    half_life = float(hyper["half_life_days"])
    k = float(hyper["k"])

    fixtures = parse_fixtures(RAW_DIR / "fixtures.csv")
    divisions_set = set(league_names)
    results = read_results(all_matches)

    round_date = next_round_date(today)
    round_fixtures = fixtures_for_date(fixtures, round_date, divisions_set)
    predictor = live.build_predictor(all_matches, round_date, half_life, k, decisions)

    round_path = PICKS_DIR / f"{round_date.isoformat()}.json"
    if round_path.exists():
        document = json.loads(round_path.read_text(encoding="utf-8"))
        print(f"round {round_date} already published ({len(document['picks'])} picks) — not regenerated")
    else:
        document = build_round(predictor, round_fixtures, league_names, round_date, calibration, PICK_CONFIG, kind="round")
        print(f"round {round_date}: {len(document['picks'])} picks from {len(round_fixtures)} fixtures")
    settle_document(document, results)
    if not args.no_publish:
        publish(document, PICKS_DIR, ROUNDS_DIR)

    example_date = last_saturday(today)
    example_fixtures = fixtures_for_date(fixtures, example_date, divisions_set)
    example_predictor = live.build_predictor(all_matches, example_date, half_life, k, decisions)
    example = build_round(example_predictor, example_fixtures, league_names, example_date, calibration, PICK_CONFIG, kind="example")
    settle_document(example, results)
    print(f"example round {example_date}: {len(example['picks'])} picks ({example['settled_count']} settled, {example['hits']} hits)")
    if not args.no_publish:
        publish(example, PICKS_DIR, ROUNDS_DIR)

    for path in sorted(PICKS_DIR.glob("*.json")):
        stored = json.loads(path.read_text(encoding="utf-8"))
        if stored.get("kind") == "example" or stored["date"] == round_date.isoformat():
            continue
        if settle_document(stored, results) and not args.no_publish:
            publish(stored, PICKS_DIR, ROUNDS_DIR)

    if args.no_publish:
        return 0

    index = rebuild_index(PICKS_DIR, ROUNDS_DIR)

    upcoming = [fixture for fixture in fixtures if fixture.div in divisions_set and today <= fixture.date <= today + dt.timedelta(days=UPCOMING_DAYS)]
    by_div: dict[str, list] = defaultdict(list)
    for fixture in upcoming:
        by_div[fixture.div].append(fixture)

    for code, items in by_div.items():
        teams_path = TEAMS_DIR / f"{code}.json"
        if not teams_path.exists():
            continue
        teams_document = json.loads(teams_path.read_text(encoding="utf-8"))
        built = build_round(predictor, items, league_names, round_date, calibration, {**PICK_CONFIG, "top_n": 999}, kind="upcoming")
        by_match = {(pick["home"], pick["away"]): pick for pick in built["picks"]}
        teams_document["upcoming"] = [
            {
                "date": fixture.date.isoformat(),
                "time": fixture.time,
                "home": fixture.home,
                "away": fixture.away,
                "best": by_match.get((fixture.home, fixture.away)),
            }
            for fixture in sorted(items, key=lambda item: (item.date, item.home))
        ]
        write_json(teams_path, teams_document)

    totals = {"rounds": len(index["rounds"]), "picks": sum(row["picks"] for row in index["rounds"]), "hits": sum(row["hits"] for row in index["rounds"]), "settled": sum(row["settled_count"] for row in index["rounds"])}
    totals["hit_rate"] = round(totals["hits"] / totals["settled"], 4) if totals["settled"] else None
    write_json(RECORD_JSON, {"calibration": calibration, "rounds": index["rounds"], "totals": totals})

    print(f"rounds published: {totals['rounds']}, picks: {totals['picks']}, settled: {totals['settled']}, hits: {totals['hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
