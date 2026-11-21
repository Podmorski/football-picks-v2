"""Record at Mozzart prices for settled rounds.

Three scopes, cumulative and per round date:
  all            every passing vetting pick with a price
  passing_value  passing picks where Mozzart >= fair
  any_value      every priced bet where Mozzart >= fair (any rule)

Prices are keyed by (round_date, div, home, away, market), so a repeated
fixture uses only its own round's snapshot. Historical snapshots are used as-is.
"""
from __future__ import annotations

from .. import vetting
from ..model.ranking_backtest import mean_return_ci


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


def _summary(rows: list[dict]) -> dict:
    n = len(rows)
    hits = sum(1 for row in rows if row["landed"])
    mean, (low, high) = mean_return_ci(
        [{"date": row["date"], "return": row["return"]} for row in rows]
    ) if rows else (None, (None, None))
    return {
        "n": n,
        "landed": None if n == 0 else round(hits / n, 4),
        "return": None if mean is None else round(mean, 4),
        "ci": [None if low is None else round(low, 4), None if high is None else round(high, 4)],
    }


def aggregate(rounds: list[dict], snapshots: list[dict], rule: dict | None = None) -> dict:
    prices = _price_map(snapshots)
    by_date: dict[str, dict] = {}
    for document in rounds:
        if document.get("kind") == "example":
            continue
        date = document.get("date")
        if date not in by_date or len(document.get("rows", [])) > len(by_date[date].get("rows", [])):
            by_date[date] = document

    buckets = {"all": [], "passing_value": [], "any_value": []}
    per_round: dict[str, dict] = {}
    for date, document in sorted(by_date.items()):
        local = {"all": [], "passing_value": [], "any_value": []}
        for row in document.get("rows", []):
            if row.get("st") not in ("landed", "lost"):
                continue
            odds = prices.get((date, row.get("d"), row.get("h"), row.get("a"), row.get("m")))
            if odds is None:
                continue
            candidate = _candidate(row, odds)
            passed, _checks = vetting.evaluate(candidate, rule)
            value = odds >= candidate.fair_odds
            record = {"date": date, "landed": row["st"] == "landed", "return": (odds - 1.0) if row["st"] == "landed" else -1.0}
            if passed:
                buckets["all"].append(record)
                local["all"].append(record)
            if passed and value:
                buckets["passing_value"].append(record)
                local["passing_value"].append(record)
            if value:
                buckets["any_value"].append(record)
                local["any_value"].append(record)
        per_round[date] = {scope: _summary(items) for scope, items in local.items()}

    return {
        "cumulative": {scope: _summary(items) for scope, items in buckets.items()},
        "rounds": [{"date": date, **stats} for date, stats in sorted(per_round.items())],
    }
