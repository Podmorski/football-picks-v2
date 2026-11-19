"""Return at the frozen Mozzart price, aggregated per ranking x minimum odds.

A pick's price is frozen when the round is first matched in the private store;
the aggregate is the only thing that ever leaves the private repo. Returns are
measured per pick: price - 1 when it lands, -1 when it loses. The 95% interval
is bootstrapped over round dates (2000 resamples, seed 20261025), matching the
fair-odds table.
"""
from __future__ import annotations

from collections import defaultdict

from ..model.ranking_backtest import FAIR_MAX, FAIR_MIN, mean_return_ci

STRATEGIES = ("lean", "probability")
LEVELS = (("any", 1.50), ("2.00+", 2.00), ("2.50+", 2.50), ("3.00+", 3.00))


def _fixture_index(snapshot: dict) -> dict[tuple[str, str, str], dict]:
    return {(row["div"], row["home"], row["away"]): row for row in snapshot.get("fixtures", [])}


def freeze(snapshot: dict, round_document: dict) -> dict[str, float]:
    """{pick key -> Mozzart odds} for every published pick the snapshot prices."""
    index = _fixture_index(snapshot)
    frozen: dict[str, float] = {}
    for row in round_document.get("rows", []):
        fixture = index.get((row.get("d"), row.get("h"), row.get("a")))
        if fixture is None:
            continue
        price = (fixture.get("prices") or {}).get(row.get("m"))
        if isinstance(price, (int, float)):
            frozen[f"{row.get('d')}|{row.get('h')}|{row.get('a')}|{row.get('m')}"] = float(price)
    return frozen


def aggregate(rounds: list[dict], snapshots: list[dict]) -> dict:
    """Per strategy x level return at the frozen Mozzart price.

    Only settled outcomes count (landed/lost). A pick is in a level when that
    ranking's fair odds (1/p) is inside the dashboard's 1.50-4.00 window and at
    or above the level's floor.
    """
    by_date = {snapshot["round_date"]: snapshot for snapshot in snapshots}
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    priced_total = 0
    for document in rounds:
        if document.get("kind") == "example":
            continue
        snapshot = by_date.get(document.get("date"))
        if snapshot is None:
            continue
        index = _fixture_index(snapshot)
        for row in document.get("rows", []):
            if row.get("st") not in ("landed", "lost"):
                continue
            fixture = index.get((row.get("d"), row.get("h"), row.get("a")))
            if fixture is None:
                continue
            price = (fixture.get("prices") or {}).get(row.get("m"))
            if not isinstance(price, (int, float)):
                continue
            priced_total += 1
            landed = row.get("st") == "landed"
            result = float(price) - 1.0 if landed else -1.0
            for strategy in STRATEGIES:
                probability = row.get("pl") if strategy == "lean" else row.get("pp")
                if not isinstance(probability, (int, float)) or probability <= 0:
                    continue
                fair = 1.0 / probability
                if fair < FAIR_MIN or fair > FAIR_MAX:
                    continue
                for level, floor in LEVELS:
                    if fair >= max(FAIR_MIN, floor):
                        buckets[(strategy, level)].append(
                            {"date": document.get("date"), "return": result}
                        )

    summary = []
    for strategy in STRATEGIES:
        for level, _floor in LEVELS:
            picks = buckets.get((strategy, level), [])
            if not picks:
                continue
            mean, (low, high) = mean_return_ci(picks)
            summary.append(
                {
                    "strategy": strategy,
                    "level": level,
                    "picks": len(picks),
                    "mean_return": None if mean is None else round(mean, 4),
                    "return_ci": [
                        None if low is None else round(low, 4),
                        None if high is None else round(high, 4),
                    ],
                }
            )
    return {
        "strategies": list(STRATEGIES),
        "levels": [level for level, _floor in LEVELS],
        "priced_picks": priced_total,
        "summary": summary,
    }
