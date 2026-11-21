"""Value-bet tracking at the Mozzart snapshot price, flat 1 unit.

Settled rounds only. Value = Mozzart price >= ceil_2dp(1.05 / p), team records
and agreement pass, fair <= 6, one per match by highest edge. Lift (t1) is not
required: the web Value selection uses only t3/t4/t6. Prices are keyed by the
snapshot's round_date, so a repeated fixture uses its own round's price. The
output is an aggregate only: no prices are written to the public repository.

Run from update.yml after the settle pass (the workflow checks out the private
price store separately):

    python -m pipeline.mozzart.value_record --prices-dir prices-private --web-dir web/public/data
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from .. import ranking, vetting
from ..config import ROOT_DIR
from ..markets import MARKET_BY_ID
from ..model.ranking_backtest import mean_return_ci

HIDDEN_PREFIX = "CORRECT_SCORE:"
MAX_FAIR = 6.0


def min_play(probability: float) -> float:
    return math.ceil((1.05 / max(probability, 1e-4)) * 100 - 1e-9) / 100


def band_of(price: float) -> str:
    if price < 2:
        return "<2"
    if price < 3:
        return "2-3"
    return "3-6"


def _price_map(snapshots: list[dict]) -> dict[tuple, float]:
    out: dict[tuple, float] = {}
    for snapshot in snapshots:
        round_date = snapshot.get("round_date")
        if not round_date:
            continue
        for fixture in snapshot.get("fixtures", []):
            for market, odds in (fixture.get("prices") or {}).items():
                out[(round_date, fixture["div"], fixture["home"], fixture["away"], market)] = float(odds)
    return out


def _candidate(row: dict, odds: float) -> vetting.Candidate:
    probability = float(row.get("pc", row.get("p", 0.0)))
    return vetting.Candidate(
        probability=probability,
        model_probability=float(row.get("p", probability)),
        league_rate=float(row.get("lr", 0.0)),
        league_n=int(row.get("ln", 0)),
        home_rate=float(row.get("hr", 0.0)),
        home_n=int(row.get("hn", 0)),
        away_rate=float(row.get("ar", 0.0)),
        away_n=int(row.get("an", 0)),
        fair_odds=1.0 / max(probability, 1e-4),
        counts_probability=vetting.team_empirical_values(
            float(row.get("lr", 0.0)), float(row.get("hr", 0.0)), int(row.get("hn", 0)),
            float(row.get("ar", 0.0)), int(row.get("an", 0)),
        ),
        mozzart_odds=odds,
    )


def _value_bets(rounds: list[dict], snapshots: list[dict]) -> dict[str, list[dict]]:
    prices = _price_map(snapshots)
    by_date: dict[str, dict] = {}
    for document in rounds:
        date = document.get("date")
        if not date:
            continue
        if date not in by_date or len(document.get("rows", [])) > len(by_date[date].get("rows", [])):
            by_date[date] = document

    out: dict[str, list[dict]] = {}
    for date, document in sorted(by_date.items()):
        best: dict[tuple, dict] = {}
        for row in document.get("rows", []):
            if str(row.get("m", "")).startswith(HIDDEN_PREFIX):
                continue
            if row.get("st") not in ("landed", "lost"):
                continue
            odds = prices.get((date, row.get("d"), row.get("h"), row.get("a"), row.get("m")))
            if odds is None:
                continue
            probability = float(row.get("pc", row.get("p", 0.0)))
            if odds < min_play(probability) or 1.0 / max(probability, 1e-4) > MAX_FAIR:
                continue
            _, checks = vetting.type_evaluate(_candidate(row, odds))
            by_id = {check["id"]: check["passed"] for check in checks}
            if not (by_id.get("t3") and by_id.get("t4") and by_id.get("t6")):
                continue
            edge = odds * probability - 1.0
            key = (row.get("d"), row.get("h"), row.get("a"))
            current = best.get(key)
            if current is None or edge > current["edge"]:
                best[key] = {
                    "date": date,
                    "label": document.get("label", date),
                    "group": MARKET_BY_ID[row["m"]].group,
                    "band": band_of(odds),
                    "odds": odds,
                    "probability": probability,
                    "edge": edge,
                    "landed": row.get("st") == "landed",
                    "profit": (odds - 1.0) if row.get("st") == "landed" else -1.0,
                    "needed": 1.0 / odds,
                }
        if best:
            out[date] = sorted(best.values(), key=lambda bet: bet["edge"], reverse=True)
    return out


def _summary(bets: list[dict]) -> dict:
    n = len(bets)
    landed = sum(1 for bet in bets if bet["landed"])
    needed = sum(bet["needed"] for bet in bets)
    profit = sum(bet["profit"] for bet in bets)
    mean, (low, high) = mean_return_ci(
        [{"date": bet["date"], "return": bet["profit"]} for bet in bets]
    ) if bets else (None, (None, None))
    return {
        "bets": n,
        "landed": landed,
        "needed": round(needed, 4),
        "profit": round(profit, 4),
        "return": None if mean is None else round(mean, 4),
        "ci": [None if low is None else round(low, 4), None if high is None else round(high, 4)],
    }


def build(rounds: list[dict], snapshots: list[dict]) -> dict:
    by_date = _value_bets(rounds, snapshots)
    round_rows = []
    all_bets: list[dict] = []
    for date in sorted(by_date):
        bets = by_date[date]
        all_bets.extend(bets)
        round_rows.append({"date": date, "label": bets[0].get("label", date), "summary": _summary(bets)})

    groups: dict[str, list[dict]] = defaultdict(list)
    bands: dict[str, list[dict]] = defaultdict(list)
    for bet in all_bets:
        groups[bet["group"]].append(bet)
        bands[bet["band"]].append(bet)

    running = 0.0
    profit_series = []
    for row in round_rows:
        running += row["summary"]["profit"]
        profit_series.append({"date": row["date"], "profit": round(running, 4)})

    return {
        "rounds": round_rows,
        "cumulative": _summary(all_bets),
        "groups": {key: _summary(items) for key, items in sorted(groups.items())},
        "bands": {key: _summary(items) for key, items in sorted(bands.items())},
        "profit_series": profit_series,
        "bootstrap": {"resamples": 2000, "seed": 20261025, "unit": "round date"},
        "note": (
            "Settled rounds only. Value = Mozzart >= min play, team records and agreement pass, "
            "fair <= 6, one per match by highest edge; flat 1 unit at the Mozzart price."
        ),
    }


def write(path: Path, rounds: list[dict], snapshots: list[dict]) -> dict:
    payload = build(rounds, snapshots)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return payload


def _all_rounds() -> list[dict]:
    picks_dir = ROOT_DIR / "picks"
    out = []
    for path in sorted(picks_dir.glob("*.json")):
        if path.name.endswith(".full.json"):
            continue
        date = path.stem
        full = picks_dir / f"{date}.full.json"
        out.append(ranking.load(full if full.exists() else path))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.mozzart.value_record")
    parser.add_argument("--prices-dir", required=True)
    parser.add_argument("--web-dir", required=True)
    args = parser.parse_args(argv)
    snapshots = []
    for path in sorted((Path(args.prices_dir) / "rounds").glob("*.json")):
        try:
            snapshots.append(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    payload = write(Path(args.web_dir) / "value-record.json", _all_rounds(), snapshots)
    print(f"value record: {payload['cumulative']['bets']} settled bets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
