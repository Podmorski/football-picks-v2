"""Ranking: every fixture x every implemented market, price range applied first.

Plain FT home/away wins are never offered as a single bet and nothing with fair odds
below 1.70 is stored. Each row carries the model probability plus two calibrated
values (one per ranking strategy); the dashboard shows, prices and filters on the
calibrated value for the strategy in use.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .fixtures import Fixture, WEEKDAY_NAMES
from .markets import MARKETS, MARKET_BY_ID, settle
from .model.goals_engine import extract_targets
from .picks import MONTHS, confidence_badge

MIN_FAIR_ODDS = 1.50
MAX_FAIR_ODDS = 4.00
DEFAULT_LEVEL = "any"
EXCLUDED_MARKETS = {"RESULT:1", "RESULT:2"}
TOP_N = 15
STRATEGIES = ("lean", "probability")
LEAN_MIN_LIFT = 0.20
LEAN_MIN_LEAGUE_N = 200

# Minimum-odds levels (fair odds = 1 / probability).
LEVELS = (
    {"key": "any", "label": "Any", "low": 1.50},
    {"key": "2.00+", "label": "2.00+", "low": 2.00},
    {"key": "2.50+", "label": "2.50+", "low": 2.50},
    {"key": "3.00+", "label": "3.00+", "low": 3.00},
)
LEVEL_BY_KEY = {level["key"]: level for level in LEVELS}

# Markets the goal ladder shows whatever their price.
LADDER_MARKETS = (
    "GOAL_RANGE_FT:1+", "GOAL_RANGE_FT:2+", "GOAL_RANGE_FT:3+",
    "GOAL_RANGE_FT:4+", "GOAL_RANGE_FT:5+",
    "GOAL_RANGE_FT:0-1", "GOAL_RANGE_FT:0-2", "GOAL_RANGE_FT:0-3",
    "GOAL_RANGE_1H:I1+", "GOAL_RANGE_1H:I2+", "BTTS:GG",
)

ROW_FIELDS = [
    "fi", "m", "p", "pc", "pl", "pp", "lr", "ln", "hr", "hn", "ar", "an",
    "c", "s", "st", "ht", "ft",
]

# Picker calibration bands (shown probability). Above 80% is not calibrated and
# is skipped by the "Any bet" picker.
PICKER_BANDS = (
    ("20-30", 0.20, 0.30), ("30-40", 0.30, 0.40), ("40-50", 0.40, 0.50),
    ("50-60", 0.50, 0.60), ("60-70", 0.60, 0.70), ("70-80", 0.70, 0.80),
)


def picker_band(probability: float) -> str | None:
    """The 20-30 ... 70-80 band for a raw probability, or None outside it."""
    for label, low, high in PICKER_BANDS:
        if low <= probability < high:
            return label
    return None


def band_for(fair_odds: float) -> str | None:
    """Highest minimum-odds level this price satisfies."""
    chosen = None
    for level in LEVELS:
        if fair_odds >= level["low"]:
            chosen = level["key"]
    return chosen


def in_price_window(probability: float) -> bool:
    if probability <= 0:
        return False
    fair = 1.0 / probability
    return MIN_FAIR_ODDS <= fair <= MAX_FAIR_ODDS


def logit(probability: float) -> float:
    p = min(max(probability, 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


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
    min_fair: float = MIN_FAIR_ODDS,
    excluded: set[str] | None = None,
    picker_factors: dict | None = None,
) -> dict:
    excluded = EXCLUDED_MARKETS if excluded is None else excluded
    grouped: dict[str, list[Fixture]] = defaultdict(list)
    for fixture in fixtures:
        if fixture.div in predictors:
            grouped[fixture.div].append(fixture)

    factors = calibration or {}
    shrink_k = float(factors.get("__k__", 20.0))

    # Pooled all-league empirical rate per market, weighted by league sample size.
    pooled_num = np.zeros(len(MARKETS))
    pooled_den = np.zeros(len(MARKETS))
    for predictor in predictors.values():
        empirical = predictor.empirical
        pooled_num += empirical.league_rate * empirical.league_n
        pooled_den += empirical.league_n
    pooled = np.divide(pooled_num, np.where(pooled_den > 0, pooled_den, 1.0))

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
                if market.id in excluded:
                    continue
                probability = float(probabilities[index][position])
                if probability <= 0:
                    continue
                fair = 1.0 / probability
                ladder = market.id in LADDER_MARKETS
                if fair < min_fair and not ladder:
                    continue

                level = band_for(fair) or "any"
                league_rate = float(empirical.league_rate[position])
                league_n = int(empirical.league_n[position])
                lean_factor = factors.get(f"lean|{market.group}|{level}", 1.0)
                prob_factor = factors.get(f"probability|{market.group}|{level}", 1.0)
                p_lean = min(0.999, max(0.001, probability * lean_factor))
                p_prob = min(0.999, max(0.001, probability * prob_factor))
                band = picker_band(probability)
                picker_factor = (picker_factors or {}).get(f"{market.group}|{band}", 1.0) if band else 1.0
                p_picker = min(0.999, max(0.001, probability * picker_factor))

                # League rate shrunk toward the pooled all-league rate.
                shrunk = (league_n * league_rate + shrink_k * float(pooled[position])) / (league_n + shrink_k) if league_n + shrink_k > 0 else league_rate
                lift = logit(p_lean) - logit(shrunk)

                bin_row = factors.get("__bands__", {}).get(f"{market.group}|{level}")
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
                        "pc": round(p_picker, 4),
                        "pl": round(p_lean, 4),
                        "pp": round(p_prob, 4),
                        "lr": round(league_rate, 4),
                        "ln": league_n,
                        "hr": round(float(home_rate[position]), 4),
                        "hn": int(home_n),
                        "ar": round(float(away_rate[position]), 4),
                        "an": int(away_n),
                        "c": badge,
                        "s": round(lift, 4),
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
        "levels": [{"key": level["key"], "label": level["label"]} for level in LEVELS],
        "ladder": list(LADDER_MARKETS),
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
    level: str = DEFAULT_LEVEL,
    strategy: str = "lean",
    show: str = "all",
) -> list[dict]:
    """Filter, rank, top 15. One pick per match unless a single market is chosen."""
    floor = LEVEL_BY_KEY.get(level, LEVEL_BY_KEY[DEFAULT_LEVEL])["low"]
    filtered = []
    for row in rows:
        probability = shown(row, strategy)
        if probability <= 0:
            continue
        fair = 1.0 / probability
        if fair < max(MIN_FAIR_ODDS, floor) or fair > MAX_FAIR_ODDS:
            continue
        filtered.append(row)
    if league != "all":
        filtered = [row for row in filtered if row["d"] == league]
    if market != "all":
        filtered = [row for row in filtered if row["m"] == market]
    elif group != "any":
        filtered = [row for row in filtered if MARKET_BY_ID[row["m"]].group == group]

    if strategy == "lean":
        filtered = [row for row in filtered if row["ln"] >= LEAN_MIN_LEAGUE_N and row["s"] >= LEAN_MIN_LIFT]
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


def round_action(existing: dict | None, fixtures: list) -> str:
    """'settle' when a round already has rows, 'publish' when fixtures exist, else 'skip'."""
    if existing and existing.get("rows"):
        return "settle"
    return "publish" if fixtures else "skip"


def encode(document: dict, fields: list[str] | None = None) -> dict:
    field_list = list(fields or ROW_FIELDS)
    fixtures: list[dict] = []
    index: dict[tuple, int] = {}
    for row in document.get("rows", []):
        key = (row["d"], row["k"], row["h"], row["a"])
        if key not in index:
            index[key] = len(fixtures)
            fixtures.append({"d": row["d"], "k": row["k"], "h": row["h"], "a": row["a"]})

    rows = [
        [index[(row["d"], row["k"], row["h"], row["a"])] if name == "fi" else row.get(name)
         for name in field_list]
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
        "levels": document.get("levels", []),
        "ladder": document.get("ladder", []),
        "market_bands": document.get("market_bands", {}),
        "fields": field_list,
        "fixture_list": fixtures,
        "rows": rows,
    }


def decode(document: dict) -> dict:
    if not document.get("rows") or not isinstance(document["rows"][0], list):
        return document
    fixture_list = document.get("fixture_list", [])
    fields = document.get("fields") or ROW_FIELDS
    rows = []
    for values in document["rows"]:
        fixture = fixture_list[values[0]]
        row = {name: values[index] for index, name in enumerate(fields) if index < len(values)}
        row.update({"d": fixture["d"], "k": fixture["k"], "h": fixture["h"], "a": fixture["a"]})
        row.setdefault("pc", row.get("p"))
        rows.append(row)
    decoded = dict(document)
    decoded["rows"] = rows
    return decoded


def publish(document: dict, picks_dir: Path, web_dir: Path, fields: list[str] | None = None) -> None:
    picks_dir.mkdir(parents=True, exist_ok=True)
    web_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(encode(document, fields), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    (picks_dir / f"{document['date']}.json").write_text(text, encoding="utf-8")
    (web_dir / f"{document['date']}.json").write_text(text, encoding="utf-8")


def publish_full(document: dict, picks_dir: Path, web_dir: Path, fields: list[str] | None = None) -> None:
    """Write the all-market companion without touching the published main file."""
    picks_dir.mkdir(parents=True, exist_ok=True)
    web_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(encode(document, fields), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    (picks_dir / f"{document['date']}.full.json").write_text(text, encoding="utf-8")
    (web_dir / f"{document['date']}.full.json").write_text(text, encoding="utf-8")


def load(path: Path) -> dict:
    return decode(json.loads(path.read_text(encoding="utf-8")))


def rebuild_index(picks_dir: Path, web_dir: Path) -> dict:
    rounds = []
    for path in sorted(picks_dir.glob("*.json")):
        if path.name.endswith(".full.json"):
            continue
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
    index = {
        "rounds": rounds,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (web_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return index
