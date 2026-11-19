"""Ranking: every fixture x every implemented market, price range applied first.

Plain FT home/away wins are never offered as a single bet, and nothing with fair
odds below 1.70 is stored.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .fixtures import Fixture, WEEKDAY_NAMES
from .markets import MARKETS, settle
from .model.goals_engine import extract_targets
from .picks import MONTHS, confidence_badge

MIN_FAIR_ODDS = 1.70
DEFAULT_BAND = "2.00-3.00"
EXCLUDED_MARKETS = {"RESULT:1", "RESULT:2"}
TOP_N = 15

PRICE_BANDS = (
    {"key": "1.70-2.00", "label": "1.70–2.00", "low": 1.70, "high": 2.00},
    {"key": "2.00-3.00", "label": "2.00–3.00", "low": 2.00, "high": 3.00},
    {"key": "3.00-5.00", "label": "3.00–5.00", "low": 3.00, "high": 5.00},
    {"key": "5.00-10.00", "label": "5.00–10.00", "low": 5.00, "high": 10.00},
    {"key": "10.00+", "label": "10.00+", "low": 10.00, "high": float("inf")},
)


def band_for(fair_odds: float) -> str | None:
    for band in PRICE_BANDS:
        if band["low"] <= fair_odds < band["high"]:
            return band["key"]
    return None


def round_label(date) -> str:
    return f"{WEEKDAY_NAMES[date.weekday()]} {date.day} {MONTHS[date.month - 1]}"


def build_ranking(
    predictors: dict,
    fixtures: list[Fixture],
    league_names: dict[str, str],
    round_date,
    market_bands: dict | None = None,
) -> dict:
    """All rows with fair odds >= 1.70 for one round."""
    grouped: dict[str, list[Fixture]] = defaultdict(list)
    for fixture in fixtures:
        if fixture.div in predictors:
            grouped[fixture.div].append(fixture)

    rows: list[dict] = []
    for div, group in grouped.items():
        predictor = predictors[div]
        probabilities, baseline = predictor.market_probabilities(
            [fixture.home for fixture in group],
            [fixture.away for fixture in group],
            [fixture.odds for fixture in group],
        )
        samples = predictor.counts
        for index, fixture in enumerate(group):
            no_odds = extract_targets(fixture.odds) is None
            for position, market in enumerate(MARKETS):
                if market.id in EXCLUDED_MARKETS:
                    continue
                probability = float(probabilities[index][position])
                if probability <= 0:
                    continue
                fair = 1.0 / probability
                if fair < MIN_FAIR_ODDS:
                    continue
                band = band_for(fair)
                if band is None:
                    continue
                league_base = float(baseline[position])
                bin_row = (market_bands or {}).get(f"{market.group}|{band}")
                badge = confidence_badge(
                    float(min(samples.n_home[predictor.team_index.get(fixture.home, predictor.unknown_index)],
                              samples.n_away[predictor.team_index.get(fixture.away, predictor.unknown_index)])),
                    abs(probability - league_base),
                    bin_row,
                    100,
                )
                if no_odds and badge == "High":
                    badge = "Medium"

                rows.append(
                    {
                        "div": div,
                        "league": league_names.get(div, div),
                        "kickoff": fixture.time,
                        "home": fixture.home,
                        "away": fixture.away,
                        "market": market.id,
                        "family": market.family,
                        "group": market.group,
                        "mozzart": market.mozzart_label,
                        "plain": market.plain,
                        "probability": round(probability, 4),
                        "fair_odds": round(fair, 2),
                        "league_rate": round(league_base, 4),
                        "band": band,
                        "confidence": badge,
                        "no_odds": no_odds,
                        "landed": None,
                    }
                )

    return {
        "date": round_date.isoformat(),
        "label": round_label(round_date),
        "weekday": WEEKDAY_NAMES[round_date.weekday()],
        "fixtures": len(fixtures),
        "leagues": len({fixture.div for fixture in fixtures}),
        "bands": [{"key": band["key"], "label": band["label"]} for band in PRICE_BANDS],
        "markets": len(MARKETS),
        "rows": rows,
    }


def settle_document(document: dict, results: dict) -> bool:
    """Fill in landed for rows whose fixture has a result. Returns True on change."""
    changed = False
    by_id = {market.id: market for market in MARKETS}
    for row in document.get("rows", []):
        if row.get("landed") is not None:
            continue
        result = results.get((document["date"], row["home"], row["away"]))
        if result is None:
            continue
        fthg, ftag, hthg, htag = result
        outcome = settle(by_id[row["market"]], fthg, ftag, hthg, htag)
        if outcome is None:
            continue
        row["landed"] = bool(outcome)
        row["result"] = f"{fthg}-{ftag}" + (f" ({hthg}-{htag} HT)" if hthg is not None else "")
        changed = True
    return changed


def rank_rows(
    rows: list[dict],
    league: str = "all",
    group: str = "any",
    market: str = "all",
    band: str = DEFAULT_BAND,
) -> list[dict]:
    """Apply the dashboard filters, then rank by probability, top 15.

    One pick per match unless a single market is selected.
    """
    filtered = [row for row in rows if row["band"] == band]
    if league != "all":
        filtered = [row for row in filtered if row["div"] == league]
    if market != "all":
        filtered = [row for row in filtered if row["market"] == market]
    elif group != "any":
        filtered = [row for row in filtered if row["group"] == group]

    filtered.sort(key=lambda row: (-row["probability"], row["home"]))
    if market != "all":
        return filtered[:TOP_N]

    seen: set[tuple[str, str]] = set()
    picks: list[dict] = []
    for row in filtered:
        key = (row["home"], row["away"])
        if key in seen:
            continue
        seen.add(key)
        picks.append(row)
        if len(picks) >= TOP_N:
            break
    return picks


def publish(document: dict, picks_dir: Path, web_dir: Path) -> None:
    picks_dir.mkdir(parents=True, exist_ok=True)
    web_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    (picks_dir / f"{document['date']}.json").write_text(text, encoding="utf-8")
    (web_dir / f"{document['date']}.json").write_text(text, encoding="utf-8")


def rebuild_index(picks_dir: Path, web_dir: Path) -> dict:
    rounds = []
    for path in sorted(picks_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        rows = document.get("rows", [])
        if not rows:
            continue
        settled = [row for row in rows if row.get("landed") is not None]
        rounds.append(
            {
                "date": document["date"],
                "label": document["label"],
                "weekday": document["weekday"],
                "kind": document.get("kind", "round"),
                "fixtures": document.get("fixtures", 0),
                "leagues": document.get("leagues", 0),
                "rows": len(rows),
                "picks": len(rows),
                "settled_count": len(settled),
                "hits": sum(1 for row in settled if row.get("landed")),
                "settled": bool(rows) and len(settled) == len(rows),
            }
        )
    index = {"rounds": rounds}
    (web_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return index
