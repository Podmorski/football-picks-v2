"""One-off provenance builder for Task 22 published-pick reconstructions.

Reads the historical publication commits from git, reproduces each round's
displayed pick pool under the rule that was live then, and writes
``pipeline/provenance/<date>.json``. It never reads settlement status for the
pool. Not used at app build time.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pipeline" / "provenance"

COMMITS = {
    "2026-11-14": {
        "commit": "5c59bf3", "time": "2026-11-18T16:26:10+01:00", "kind": "example",
        "rule_version": "picks-build-round-v1", "rule_source": "pipeline/picks.py@5c59bf3 + pipeline/run_model.py@5c59bf3",
        "pre_match": False,
    },
    "2026-11-21": {
        "commit": "8650c95", "time": "2026-11-20T11:12:47+00:00", "kind": "round",
        "rule_version": "dashboard-lean-top15-v1", "rule_source": "web/components/Dashboard.tsx@8650c95",
        "pre_match": True,
    },
    "2026-11-22": {
        "commit": "8650c95", "time": "2026-11-20T11:12:47+00:00", "kind": "round",
        "rule_version": "dashboard-lean-top15-v1", "rule_source": "web/components/Dashboard.tsx@8650c95",
        "pre_match": True,
    },
}


def git_show(commit: str, path: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), "show", f"{commit}:{path}"], text=True)


def canon(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return "sha256:" + hashlib.sha256(canon(value).encode("utf-8")).hexdigest()


def decode_compact(document: dict) -> list[dict]:
    fields = document["fields"]
    fixtures = document["fixture_list"]
    rows = []
    for values in document["rows"]:
        fixture = fixtures[values[0]]
        row = {"d": fixture["d"], "k": fixture.get("k"), "h": fixture["h"], "a": fixture["a"]}
        for index, name in enumerate(fields):
            if index < len(values):
                row[name] = values[index]
        rows.append(row)
    return rows


def lean_pool(rows: list[dict]) -> list[dict]:
    """Dashboard.tsx@8650c95 default: Any bet, any league, Lean, Show all, no Mozzart filter."""
    filtered = []
    for row in rows:
        fair = 1.0 / max(float(row["pl"]), 1e-4)
        if not (1.5 <= fair <= 4.0):
            continue
        if float(row["ln"]) < 200 or float(row["s"]) < 0.2:
            continue
        filtered.append(row)
    filtered.sort(key=lambda row: (-float(row["s"]), -float(row["pl"]), row["d"], row["h"], row["a"], row["m"]))
    seen = set()
    picks = []
    for row in filtered:
        key = (row["h"], row["a"])
        if key in seen:
            continue
        seen.add(key)
        picks.append(row)
        if len(picks) >= 15:
            break
    return picks


def prediction_inputs(rows: list[dict]) -> list[dict]:
    fields = ("d", "k", "h", "a", "m", "p", "pl", "pp", "lr", "ln", "hr", "hn", "ar", "an", "c", "s")
    return [{name: row.get(name) for name in fields} for row in sorted(rows, key=lambda r: (r["d"], r["h"], r["a"], r["m"]))]


def pool_legs_21(row: dict, markets: dict) -> dict:
    probability = float(row["pl"])
    meta = markets.get(row["m"], {})
    return {
        "d": row["d"], "k": row.get("k"), "h": row["h"], "a": row["a"], "m": row["m"],
        "label": meta.get("plain", row["m"]), "group": meta.get("group", ""),
        "pc": round(probability, 10), "fair": round(1.0 / probability, 6),
    }


def current_comparison(date: str, source_rows: list[dict], fields: tuple[str, ...]) -> dict:
    current = json.loads((ROOT / "picks" / f"{date}.json").read_text(encoding="utf-8"))
    rows = decode_compact(current)
    by_key = {(row["d"], row["h"], row["a"], row["m"]): row for row in rows}
    differences = []
    for source in source_rows:
        row = by_key.get((source["d"], source["h"], source["a"], source["m"]))
        if row is None:
            differences.append({"fixture": f"{source['h']} v {source['a']}", "market": source["m"], "field": "missing"})
            continue
        for field in fields:
            if source.get(field) != row.get(field):
                differences.append({
                    "fixture": f"{source['h']} v {source['a']}", "market": source["m"], "field": field,
                })
    return {"current_file": f"picks/{date}.json", "checked_fields": list(fields),
            "match": not differences, "differences": differences[:20]}


def build_21(date: str) -> dict:
    config = COMMITS[date]
    historical = json.loads(git_show(config["commit"], f"picks/{date}.json"))
    rows = decode_compact(historical)
    markets_payload = json.loads(git_show(config["commit"], "web/public/data/markets.json"))
    markets = {item["id"]: item for item in markets_payload.get("markets", [])}
    picks = lean_pool(rows)
    pool = [pool_legs_21(row, markets) for row in picks]
    comparison = current_comparison(date, picks, ("p", "pl", "pp", "lr", "ln", "hr", "hn", "ar", "an", "c", "s", "k"))
    return {
        "schema_version": 1,
        "date": date,
        "kind": config["kind"],
        "publication_commit": config["commit"],
        "publication_time": config["time"],
        "pre_match_publication": config["pre_match"],
        "publication_precedes_fixtures": config["pre_match"],
        "rule_version": config["rule_version"],
        "rule_source": config["rule_source"],
        "rule_parameters": {
            "view": "Any bet / any league / Lean / Show all / no Mozzart filter",
            "fair_min": 1.5, "fair_max": 4.0, "min_league_n": 200, "min_lift": 0.2,
            "sort": "lift desc, lean probability desc", "one_per_match": True, "top_n": 15,
        },
        "source_fields": historical["fields"],
        "prediction_input_hash": digest(prediction_inputs(rows)),
        "pool_hash": digest(pool),
        "current_comparison": comparison,
        "actual_price_snapshot": {
            "available": False,
            "note": "No verified usable pre-match actual snapshot was available to this worker; the private store was not checked out.",
        },
        "pricing_mode": "model-fair",
        "pool": pool,
    }


OUTCOME_TO_CURRENT = {
    "away_1plus": "TEAM_GOALS:I2 1+",
    "h1_1plus": "GOAL_RANGE_1H:I1+",
    "ou_u35": "GOAL_RANGE_FT:0-3",
    "tg_3plus": "GOAL_RANGE_FT:3+",
    "dc_1x": "DOUBLE_CHANCE:1X",
}


def build_14() -> dict:
    config = COMMITS["2026-11-14"]
    historical = json.loads(git_show(config["commit"], "picks/2026-11-14.json"))
    picks = historical["picks"]
    pool = [
        {
            "d": pick["div"], "k": pick.get("kickoff"), "h": pick["home"], "a": pick["away"],
            "m": pick["outcome"], "label": pick["play"], "group": pick["group"],
            "pc": round(float(pick["probability"]), 10), "fair": round(1.0 / float(pick["probability"]), 6),
        }
        for pick in picks
    ]
    current = json.loads((ROOT / "picks" / "2026-11-14.json").read_text(encoding="utf-8"))
    by_key = {(row["d"], row["h"], row["a"], row["m"]): row for row in decode_compact(current)}
    differences = []
    for pick, leg in zip(picks, pool):
        market = OUTCOME_TO_CURRENT.get(pick["outcome"])
        if market is None:
            differences.append({"fixture": f"{pick['home']} v {pick['away']}", "market": pick["outcome"], "field": "no current catalogue mapping"})
            continue
        row = by_key.get((pick["div"], pick["home"], pick["away"], market))
        if row is None:
            differences.append({"fixture": f"{pick['home']} v {pick['away']}", "market": market, "field": "missing"})
            continue
        if abs(float(row["p"]) - float(pick["probability"])) > 1e-9:
            differences.append({"fixture": f"{pick['home']} v {pick['away']}", "market": market,
                                "field": "p", "published": pick["probability"], "current": row["p"]})
    comparison = {
        "current_file": "picks/2026-11-14.json",
        "match": False,
        "note": "The first example publication used the pre-catalogue outcome schema. The pool is taken directly from that commit; current rows differ for some mapped picks and c7 has no current equivalent.",
        "differences": differences,
    }
    inputs = [
        {name: pick.get(name) for name in ("div", "home", "away", "kickoff", "outcome", "group", "label", "play", "probability", "fair_odds")}
        for pick in sorted(picks, key=lambda item: (item["div"], item["home"], item["away"], item["outcome"]))
    ]
    return {
        "schema_version": 1,
        "date": "2026-11-14",
        "kind": "example",
        "publication_commit": config["commit"],
        "publication_time": config["time"],
        "pre_match_publication": False,
        "publication_precedes_fixtures": False,
        "rule_version": config["rule_version"],
        "rule_source": config["rule_source"],
        "rule_parameters": historical.get("config", {}),
        "source_fields": sorted(picks[0]) if picks else [],
        "prediction_input_hash": digest(inputs),
        "pool_hash": digest(pool),
        "current_comparison": comparison,
        "actual_price_snapshot": {
            "available": False,
            "note": "No verified usable pre-match actual snapshot was available to this worker; the private store was not checked out.",
        },
        "pricing_mode": "model-fair",
        "pool": pool,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for date in ("2026-11-14", "2026-11-21", "2026-11-22"):
        payload = build_14() if date == "2026-11-14" else build_21(date)
        (OUT / f"{date}.json").write_text(canon(payload) + "\n", encoding="utf-8")
        print(date, payload["rule_version"], len(payload["pool"]), payload["pool_hash"], payload["current_comparison"]["match"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
