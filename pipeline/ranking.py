"""Ranking: every fixture x every implemented market, price range applied first.

Plain FT home/away wins are never offered as a single bet, and nothing with fair
odds below 1.70 is stored.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .fixtures import Fixture, WEEKDAY_NAMES
from .markets import MARKETS, MARKET_BY_ID, settle
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
    round_date,
    market_bands: dict | None = None,
) -> dict:
    """All rows with fair odds >= 1.70 for one round, with empirical rates attached."""
    grouped: dict[str, list[Fixture]] = defaultdict(list)
    for fixture in fixtures:
        if fixture.div in predictors:
            grouped[fixture.div].append(fixture)

    rows: list[dict] = []
    for div, group in sorted(grouped.items()):
        predictor = predictors[div]
        probabilities, _baseline = predictor.market_probabilities(
            [fixture.home for fixture in group],
            [fixture.away for fixture in group],
            [fixture.odds for fixture in group],
        )
        empirical = predictor.empirical
        for index, fixture in enumerate(group):
            home_index = predictor.team_index.get(fixture.home, predictor.unknown_index)
            away_index = predictor.team_index.get(fixture.away, predictor.unknown_index)
            no_odds = extract_targets(fixture.odds) is None
            home_rate = empirical.home_rate[home_index]
            away_rate = empirical.away_rate[away_index]
            home_n = float(empirical.home_n[home_index])
            away_n = float(empirical.away_n[away_index])

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

                league_rate = float(empirical.league_rate[position])
                league_n = int(empirical.league_n[position])
                lean = probability / league_rate if league_rate > 0 else 0.0
                bin_row = (market_bands or {}).get(f"{market.group}|{band}")
                badge = confidence_badge(
                    min(home_n, away_n), abs(probability - league_rate), bin_row, 100
                )
                if no_odds and badge == "High":
                    badge = "Medium"

                rows.append(
                    {
                        "d": div,
                        "k": fixture.time,
                        "h": fixture.home,
                        "a": fixture.away,
                        "m": market.id,
                        "p": round(probability, 4),
                        "f": round(fair, 2),
                        "lr": round(league_rate, 4),
                        "ln": league_n,
                        "hr": round(float(home_rate[position]), 4),
                        "hn": int(home_n),
                        "ar": round(float(away_rate[position]), 4),
                        "an": int(away_n),
                        "c": badge,
                        "s": round(lean, 4),
                        "o": 1 if no_odds else 0,
                        "ld": None,
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


def market_catalogue() -> dict:
    """Compact market metadata the dashboard joins rows against."""
    return {
        "markets": [
            {
                "id": market.id,
                "code": market.code,
                "mozzart": market.mozzart_label,
                "plain": market.plain,
                "group": market.group,
                "family": market.family,
                "needs_ht": market.needs_ht,
            }
            for market in MARKETS
        ]
    }


def settle_document(document: dict, results: dict) -> bool:
    """Fill in ld for rows whose fixture has a result. Returns True on change."""
    changed = False
    by_id = {market.id: market for market in MARKETS}
    for row in document.get("rows", []):
        if row.get("ld") is not None:
            continue
        result = results.get((document["date"], row["h"], row["a"]))
        if result is None:
            continue
        fthg, ftag, hthg, htag = result
        outcome = settle(by_id[row["m"]], fthg, ftag, hthg, htag)
        if outcome is None:
            continue
        row["ld"] = bool(outcome)
        row["rs"] = f"{fthg}-{ftag}" + (f" ({hthg}-{htag} HT)" if hthg is not None else "")
        changed = True
    return changed


def rank_rows(
    rows: list[dict],
    league: str = "all",
    group: str = "any",
    market: str = "all",
    band: str = DEFAULT_BAND,
    strategy: str = "lean",
) -> list[dict]:
    """Apply the dashboard filters, then rank, top 15.

    * lean — score = p / league rate, requires p >= 1.10 x league rate and league n >= 200.
    * probability — plain ranking by calibrated probability.

    One pick per match unless a single market is selected.
    """
    filtered = [row for row in rows if band_for(row["f"]) == band]
    if league != "all":
        filtered = [row for row in filtered if row["d"] == league]
    if market != "all":
        filtered = [row for row in filtered if row["m"] == market]
    elif group != "any":
        filtered = [row for row in filtered if MARKET_BY_ID[row["m"]].group == group]

    if strategy == "lean":
        filtered = [
            row for row in filtered if row["ln"] >= 200 and row["lr"] > 0 and row["p"] >= 1.10 * row["lr"]
        ]
        filtered.sort(key=lambda row: (-row["s"], -row["p"], row["h"]))
    else:
        filtered.sort(key=lambda row: (-row["p"], row["h"]))

    if market != "all":
        return filtered[:TOP_N]

    seen: set[tuple[str, str]] = set()
    picks: list[dict] = []
    for row in filtered:
        key = (row["h"], row["a"])
        if key in seen:
            continue
        seen.add(key)
        picks.append(row)
        if len(picks) >= TOP_N:
            break
    return picks


def encode(document: dict) -> dict:
    """Compact on-disk form: fixtures once, rows as arrays."""
    fixtures: list[dict] = []
    index: dict[tuple, int] = {}
    for row in document.get("rows", []):
        key = (row["d"], row["k"], row["h"], row["a"])
        if key not in index:
            index[key] = len(fixtures)
            fixtures.append({"d": row["d"], "k": row["k"], "h": row["h"], "a": row["a"]})

    rows = [
        [
            index[(row["d"], row["k"], row["h"], row["a"])],
            row["m"],
            row["p"],
            row["f"],
            row["lr"],
            row["ln"],
            row["hr"],
            row["hn"],
            row["ar"],
            row["an"],
            row["c"],
            row["s"],
            row["ld"],
            row.get("rs"),
        ]
        for row in document.get("rows", [])
    ]

    encoded = {
        "date": document["date"],
        "label": document["label"],
        "weekday": document["weekday"],
        "kind": document.get("kind", "round"),
        "fixtures": document.get("fixtures", len(fixtures)),
        "leagues": document.get("leagues", 0),
        "markets": document.get("markets", len(MARKETS)),
        "bands": document.get("bands", []),
        "market_bands": document.get("market_bands", {}),
        "fields": ["fi", "m", "p", "f", "lr", "ln", "hr", "hn", "ar", "an", "c", "s", "ld", "rs"],
        "fixture_list": fixtures,
        "rows": rows,
    }
    return encoded


def decode(document: dict) -> dict:
    """Expand the compact form back to dict rows."""
    if not document.get("rows") or not isinstance(document["rows"][0], list):
        return document
    fixture_list = document.get("fixture_list", [])
    rows = []
    for values in document["rows"]:
        fixture = fixture_list[values[0]]
        rows.append(
            {
                "d": fixture["d"],
                "k": fixture["k"],
                "h": fixture["h"],
                "a": fixture["a"],
                "m": values[1],
                "p": values[2],
                "f": values[3],
                "lr": values[4],
                "ln": values[5],
                "hr": values[6],
                "hn": values[7],
                "ar": values[8],
                "an": values[9],
                "c": values[10],
                "s": values[11],
                "ld": values[12],
                "rs": values[13],
            }
        )
    decoded = dict(document)
    decoded["rows"] = rows
    return decoded


def publish(document: dict, picks_dir: Path, web_dir: Path) -> None:
    picks_dir.mkdir(parents=True, exist_ok=True)
    web_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(encode(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    (picks_dir / f"{document['date']}.json").write_text(text, encoding="utf-8")
    (web_dir / f"{document['date']}.json").write_text(text, encoding="utf-8")


def load(path: Path) -> dict:
    return decode(json.loads(path.read_text(encoding="utf-8")))


def rebuild_index(picks_dir: Path, web_dir: Path) -> dict:
    rounds = []
    for path in sorted(picks_dir.glob("*.json")):
        document = load(path)
        rows = document.get("rows", [])
        if not rows:
            continue
        settled = [row for row in rows if row.get("ld") is not None]
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
                "hits": sum(1 for row in settled if row.get("ld")),
                "settled": bool(rows) and len(settled) == len(rows),
            }
        )
    index = {"rounds": rounds}
    (web_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return index
