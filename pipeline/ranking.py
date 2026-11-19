"""Ranking: every fixture x every implemented market, price range applied first.

Plain FT home/away wins are never offered as a single bet and nothing with fair odds
below 1.70 is stored. Each row carries the model probability plus two calibrated
values (one per ranking strategy); the dashboard shows, prices and filters on the
calibrated value for the strategy in use.
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
STRATEGIES = ("lean", "probability")

PRICE_BANDS = (
    {"key": "1.70-2.00", "label": "1.70–2.00", "low": 1.70, "high": 2.00},
    {"key": "2.00-3.00", "label": "2.00–3.00", "low": 2.00, "high": 3.00},
    {"key": "3.00-5.00", "label": "3.00–5.00", "low": 3.00, "high": 5.00},
    {"key": "5.00-10.00", "label": "5.00–10.00", "low": 5.00, "high": 10.00},
    {"key": "10.00+", "label": "10.00+", "low": 10.00, "high": float("inf")},
)

ROW_FIELDS = [
    "fi", "m", "p", "pl", "pp", "lr", "ln", "hr", "hn", "ar", "an",
    "c", "s", "st", "ht", "ft",
]


def band_for(fair_odds: float) -> str | None:
    for band in PRICE_BANDS:
        if band["low"] <= fair_odds < band["high"]:
            return band["key"]
    return None


def round_label(date) -> str:
    return f"{WEEKDAY_NAMES[date.weekday()]} {date.day} {MONTHS[date.month - 1]}"


def shown(row: dict, strategy: str = "lean") -> float:
    """The percentage the dashboard prints for this strategy."""
    key = "pl" if strategy == "lean" else "pp"
    return float(row.get(key) or row["p"])


def row_band(row: dict, strategy: str = "lean") -> str | None:
    probability = shown(row, strategy)
    return band_for(1.0 / probability) if probability > 0 else None


def build_ranking(
    predictors: dict,
    fixtures: list[Fixture],
    round_date,
    calibration: dict | None = None,
) -> dict:
    grouped: dict[str, list[Fixture]] = defaultdict(list)
    for fixture in fixtures:
        if fixture.div in predictors:
            grouped[fixture.div].append(fixture)

    factors = calibration or {}
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
                lean_factor = factors.get(f"lean|{market.group}|{band}", 1.0)
                prob_factor = factors.get(f"probability|{market.group}|{band}", 1.0)
                p_lean = min(0.999, max(0.001, probability * lean_factor))
                p_prob = min(0.999, max(0.001, probability * prob_factor))
                if band_for(1.0 / p_lean) != band and band_for(1.0 / p_prob) != band:
                    continue

                bin_row = (calibration or {}).get("__bands__", {}).get(f"{market.group}|{band}")
                badge = confidence_badge(min(home_n, away_n), 0.0, bin_row, 100)
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
                        "pl": round(p_lean, 4),
                        "pp": round(p_prob, 4),
                        "lr": round(league_rate, 4),
                        "ln": league_n,
                        "hr": round(float(home_rate[position]), 4),
                        "hn": int(home_n),
                        "ar": round(float(away_rate[position]), 4),
                        "an": int(away_n),
                        "c": badge,
                        "s": round(p_lean / league_rate, 4) if league_rate > 0 else 0.0,
                        "st": "pending",
                        "ht": None,
                        "ft": None,
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


def settle_document(document: dict, results: dict, today=None) -> bool:
    """Fill st / ht / ft for rows whose fixture is known. Returns True on change."""
    changed = False
    by_id = {market.id: market for market in MARKETS}
    iso = document["date"]
    past = bool(today is not None and iso < today.isoformat())

    for row in document.get("rows", []):
        if row.get("st") not in (None, "pending"):
            continue
        result = results.get((iso, row["h"], row["a"]))
        if result is None:
            if past:
                row["st"] = "void"
                changed = True
            continue
        fthg, ftag, hthg, htag = result
        row["ft"] = f"{fthg}-{ftag}"
        row["ht"] = f"{hthg}-{htag}" if hthg is not None and htag is not None else None
        outcome = settle(by_id[row["m"]], fthg, ftag, hthg, htag)
        if outcome is None:
            row["st"] = "void"
        else:
            row["st"] = "landed" if outcome else "lost"
        changed = True
    return changed


def rank_rows(
    rows: list[dict],
    league: str = "all",
    group: str = "any",
    market: str = "all",
    band: str = DEFAULT_BAND,
    strategy: str = "lean",
    show: str = "all",
) -> list[dict]:
    """Filter, rank, top 15. One pick per match unless a single market is chosen."""
    filtered = [row for row in rows if row_band(row, strategy) == band]
    if league != "all":
        filtered = [row for row in filtered if row["d"] == league]
    if market != "all":
        filtered = [row for row in filtered if row["m"] == market]
    elif group != "any":
        filtered = [row for row in filtered if MARKET_BY_ID[row["m"]].group == group]

    if strategy == "lean":
        filtered = [
            row for row in filtered if row["ln"] >= 200 and row["lr"] > 0 and shown(row, "lean") >= 1.10 * row["lr"]
        ]
        filtered.sort(key=lambda row: (-row["s"], -shown(row, "lean"), row["h"]))
    else:
        filtered.sort(key=lambda row: (-shown(row, "probability"), row["h"]))

    if show == "landed":
        filtered = [row for row in filtered if row.get("st") == "landed"]
    elif show == "lost":
        filtered = [row for row in filtered if row.get("st") == "lost"]

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


def tally(rows: list[dict]) -> dict:
    """Landed / lost counts and the summed shown probability; void and pending excluded."""
    landed = sum(1 for row in rows if row.get("st") == "landed")
    lost = sum(1 for row in rows if row.get("st") == "lost")
    expected = sum(shown(row, "lean") for row in rows if row.get("st") in ("landed", "lost"))
    return {"landed": landed, "lost": lost, "settled": landed + lost, "expected": round(expected, 4)}


def market_catalogue() -> dict:
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


def encode(document: dict) -> dict:
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
            row["m"], row["p"], row["pl"], row["pp"], row["lr"], row["ln"],
            row["hr"], row["hn"], row["ar"], row["an"], row["c"], row["s"],
            row.get("st"), row.get("ht"), row.get("ft"),
        ]
        for row in document.get("rows", [])
    ]

    return {
        "date": document["date"],
        "label": document["label"],
        "weekday": document["weekday"],
        "kind": document.get("kind", "round"),
        "fixtures": document.get("fixtures", len(fixtures)),
        "leagues": document.get("leagues", 0),
        "markets": document.get("markets", len(MARKETS)),
        "bands": document.get("bands", []),
        "market_bands": document.get("market_bands", {}),
        "fields": ROW_FIELDS,
        "fixture_list": fixtures,
        "rows": rows,
    }


def decode(document: dict) -> dict:
    if not document.get("rows") or not isinstance(document["rows"][0], list):
        return document
    fixture_list = document.get("fixture_list", [])
    rows = []
    for values in document["rows"]:
        fixture = fixture_list[values[0]]
        rows.append(
            {
                "d": fixture["d"], "k": fixture["k"], "h": fixture["h"], "a": fixture["a"],
                "m": values[1], "p": values[2], "pl": values[3], "pp": values[4],
                "lr": values[5], "ln": values[6], "hr": values[7], "hn": values[8],
                "ar": values[9], "an": values[10], "c": values[11], "s": values[12],
                "st": values[13], "ht": values[14], "ft": values[15],
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
        stats = tally(rows)
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
                "settled_count": stats["settled"],
                "hits": stats["landed"],
                "settled": stats["settled"] == len(rows),
            }
        )
    index = {"rounds": rounds}
    (web_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return index
