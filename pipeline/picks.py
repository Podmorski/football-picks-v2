"""Picker: two views of the best play per match, published rounds, settlement.

Both views share the same model and the same exclusions: never FT home win or FT
away win, probability below the configured maximum, home team >= 8 home games,
away team >= 8 away games, and the counts and goals engines within 0.10.

* most_likely — highest calibrated probability per match.
* stand_out   — highest *lift* per match (probability minus the recency-weighted
                 league base rate), restricted to 0.45 <= p <= 0.65 and lift >= 0.08.

One pick per match in each view, at most three picks of the same play per round.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .fixtures import WEEKDAY_NAMES, Fixture
from .model.goals_engine import extract_targets
from .outcomes import OUTCOMES, OUTCOMES_BY_ID

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

DEFAULT_CONFIG = {
    "max_probability": 0.65,
    "min_lift": 0.08,
    "lift_min_probability": 0.45,
    "top_n": 15,
    "min_samples": 8,
    "agreement": 0.10,
    "min_bin_sample": 100,
    "max_same_play": 3,
}

EXCLUDED = {"ft_1", "ft_2"}
VIEW_LABELS = {"most_likely": "Most likely", "stand_out": "Stand-out"}

PLAY_WORDS = {
    "ft_x": "Draw",
    "ht_1": "Home team leading at half-time",
    "ht_x": "Level at half-time",
    "ht_2": "Away team leading at half-time",
    "htft_11": "Home ahead at half-time and full-time",
    "htft_1x": "Home lead at half-time, draw at full-time",
    "htft_12": "Home lead at half-time, away win at full-time",
    "htft_x1": "Level at half-time, home win at full-time",
    "htft_xx": "Level at half-time and full-time",
    "htft_x2": "Level at half-time, away win at full-time",
    "htft_21": "Away lead at half-time, home win at full-time",
    "htft_2x": "Away lead at half-time, draw at full-time",
    "htft_22": "Away ahead at half-time and full-time",
    "dc_1x": "Home win or draw",
    "dc_x2": "Draw or away win",
    "dc_12": "Home or away win (no draw)",
    "tg_0_1": "0-1 goals in the match",
    "tg_2_3": "2-3 goals in the match",
    "tg_4_6": "4-6 goals in the match",
    "tg_1plus": "1+ goals in the match",
    "tg_2plus": "2+ goals in the match",
    "tg_3plus": "3+ goals in the match",
    "tg_4plus": "4+ goals in the match",
    "tg_5plus": "5+ goals in the match",
    "ou_o15": "Over 1.5 goals",
    "ou_u15": "Under 1.5 goals",
    "ou_o25": "Over 2.5 goals",
    "ou_u25": "Under 2.5 goals",
    "ou_o35": "Over 3.5 goals",
    "ou_u35": "Under 3.5 goals",
    "btts_yes": "Both teams score",
    "btts_no": "At least one team fails to score",
    "btts_1h": "Both teams score in the first half",
    "odd": "Odd number of goals",
    "even": "Even number of goals",
    "mg_1h": "More goals in the first half",
    "mg_eq": "Same number of goals in each half",
    "mg_2h": "More goals in the second half",
    "h1_1plus": "1+ goals in the first half",
    "h1_2plus": "2+ goals in the first half",
    "h2_1plus": "1+ goals in the second half",
    "h2_2plus": "2+ goals in the second half",
    "home_1plus": "Home team scores",
    "home_2plus": "Home team scores 2+",
    "away_1plus": "Away team scores",
    "away_2plus": "Away team scores 2+",
    "home_1h_1plus": "Home team scores in the first half",
    "away_1h_1plus": "Away team scores in the first half",
    "home_both_halves": "Home team scores in both halves",
    "away_both_halves": "Away team scores in both halves",
    "c1": "Home win or draw, and 3+ goals",
    "c2": "A goal in the first half and 2+ in the second half",
    "c3": "Home team 2+ and both teams score",
    "c4": "Both teams score and 3+ goals",
    "c5": "Home win or draw and both teams score",
    "c6": "Draw or away win, and 3+ goals",
    "c7": "A goal in each half",
    "c8": "Away team 2+ and both teams score",
    "c9": "Level at half-time and 2+ goals",
    "c10": "Home team scores in the first half and 3+ goals",
}


def round_label(date) -> str:
    return f"{WEEKDAY_NAMES[date.weekday()]} {date.day} {MONTHS[date.month - 1]}"


def calibration_bin(table: dict, group: str, probability: float) -> dict | None:
    source = (table or {}).get("groups", table) or {}
    rows = source.get(group, {}).get("bins", [])
    index = int((probability - 0.30) / 0.05)
    if 0 <= index < len(rows):
        row = rows[index]
        if row.get("n") and row.get("landed") is not None:
            return row
    return None


def confidence_badge(samples: float, gap: float, row: dict | None, min_bin_sample: int) -> str:
    strong = 0
    weak = 0
    if samples >= 20:
        strong += 1
    elif samples < 12:
        weak += 1

    if gap <= 0.05:
        strong += 1
    elif gap > 0.08:
        weak += 1

    if row is not None and row["n"] >= min_bin_sample:
        error = abs(row["landed"] - row["shown"])
        if error <= 0.03:
            strong += 1
        elif error > 0.06:
            weak += 1

    if weak:
        return "Low"
    if strong == 3:
        return "High"
    return "Medium"


def _make_pick(row: dict, candidate: dict, counts, calibration: dict | None, settings: dict) -> dict:
    probability = candidate["probability"]
    badge = confidence_badge(
        min(candidate["n_home"], candidate["n_away"]),
        candidate["gap"],
        candidate["bin"],
        settings["min_bin_sample"],
    )
    if row["no_odds"] and badge == "High":
        badge = "Medium"

    return {
        "div": row["div"],
        "league": row["league"],
        "kickoff": row["kickoff"],
        "home": row["home"],
        "away": row["away"],
        "outcome": candidate["outcome"].id,
        "label": candidate["outcome"].label,
        "group": candidate["outcome"].group,
        "play": PLAY_WORDS.get(candidate["outcome"].id, candidate["outcome"].label),
        "probability": round(probability, 4),
        "fair_odds": round(1.0 / probability, 2),
        "league_base": round(candidate["league_base"], 4),
        "lift": round(candidate["lift"], 4),
        "confidence": badge,
        "no_odds": bool(row["no_odds"]),
        "why": {
            "home_at_home": [int(counts.home_hits[row["home_index"]][candidate["column"]]), int(counts.home_counts[row["home_index"]])],
            "away_away": [int(counts.away_hits[row["away_index"]][candidate["column"]]), int(counts.away_counts[row["away_index"]])],
            "league_rate": [round(candidate["league_base"], 4), int(counts.league_counts[candidate["column"]])],
            "engines": {
                "counts": round(candidate["counts_p"], 4),
                "goals": round(candidate["odds_p"], 4),
                "gap": round(candidate["gap"], 4),
            },
            "samples": {"home": round(candidate["n_home"], 1), "away": round(candidate["n_away"], 1)},
            "bin": candidate["bin"],
        },
        "settled": False,
        "landed": None,
        "result": None,
    }


def select_views(
    rows: list[dict],
    probabilities: dict,
    counts,
    calibration: dict | None,
    settings: dict,
) -> dict[str, list[dict]]:
    """Apply the shared filters and produce both views for one batch of fixtures."""
    full = probabilities["full"]
    counts_p = probabilities["counts"]
    odds_p = probabilities["odds"]
    n_home = probabilities["n_home"]
    n_away = probabilities["n_away"]
    league_base = counts.league_rates()

    most_likely: list[dict] = []
    stand_out: list[dict] = []

    for index, row in enumerate(rows):
        if float(n_home[index]) < settings["min_samples"] or float(n_away[index]) < settings["min_samples"]:
            continue

        best_probability: dict | None = None
        best_lift: dict | None = None

        for column, outcome in enumerate(OUTCOMES):
            if outcome.id in EXCLUDED:
                continue
            probability = float(full[index][column])
            if probability > settings["max_probability"]:
                continue
            gap = abs(float(counts_p[index][column]) - float(odds_p[index][column]))
            if gap > settings["agreement"]:
                continue

            lift = probability - float(league_base[column])
            candidate = {
                "column": column,
                "outcome": outcome,
                "probability": probability,
                "gap": gap,
                "lift": lift,
                "league_base": float(league_base[column]),
                "counts_p": float(counts_p[index][column]),
                "odds_p": float(odds_p[index][column]),
                "n_home": float(n_home[index]),
                "n_away": float(n_away[index]),
                "bin": calibration_bin(calibration or {}, outcome.group, probability),
            }

            if best_probability is None or probability > best_probability["probability"]:
                best_probability = candidate
            if (
                probability >= settings["lift_min_probability"]
                and lift >= settings["min_lift"]
                and (best_lift is None or lift > best_lift["lift"])
            ):
                best_lift = candidate

        if best_probability is not None:
            most_likely.append(_make_pick(row, best_probability, counts, calibration, settings))
        if best_lift is not None:
            stand_out.append(_make_pick(row, best_lift, counts, calibration, settings))

    return {"most_likely": most_likely, "stand_out": stand_out}


def finalise(picks: list[dict], sort_key: str, settings: dict) -> list[dict]:
    """Sort, enforce the per-play cap and cut to top_n."""
    ordered = sorted(picks, key=lambda pick: (-pick[sort_key], pick["home"], pick["away"]))
    per_play: dict[str, int] = defaultdict(int)
    kept: list[dict] = []
    for pick in ordered:
        if per_play[pick["outcome"]] >= settings["max_same_play"]:
            continue
        per_play[pick["outcome"]] += 1
        kept.append(pick)
        if len(kept) >= settings["top_n"]:
            break
    return kept


def empty_round(round_date, kind: str, config: dict) -> dict:
    return {
        "date": round_date.isoformat(),
        "label": round_label(round_date),
        "weekday": WEEKDAY_NAMES[round_date.weekday()],
        "kind": kind,
        "config": config,
        "views": {name: {"label": VIEW_LABELS[name], "picks": [], "hits": 0, "settled_count": 0} for name in VIEW_LABELS},
        "picks": [],
        "published": False,
        "fixtures": 0,
    }


def build_round(
    predictors: dict,
    fixtures: list[Fixture],
    league_names: dict[str, str],
    round_date,
    calibration: dict | None = None,
    config: dict | None = None,
    kind: str = "round",
) -> dict:
    settings = {**DEFAULT_CONFIG, **(config or {})}
    if not fixtures:
        return empty_round(round_date, kind, settings)

    grouped: dict[str, list[Fixture]] = defaultdict(list)
    for fixture in fixtures:
        if fixture.div in predictors:
            grouped[fixture.div].append(fixture)

    views: dict[str, list[dict]] = {"most_likely": [], "stand_out": []}

    for div, group in grouped.items():
        predictor = predictors[div]
        probabilities = predictor.probabilities(
            [fixture.home for fixture in group],
            [fixture.away for fixture in group],
            [fixture.odds for fixture in group],
        )
        rows = [
            {
                "div": div,
                "league": league_names.get(div, div),
                "kickoff": fixture.time,
                "home": fixture.home,
                "away": fixture.away,
                "home_index": predictor.team_index.get(fixture.home, predictor.unknown_index),
                "away_index": predictor.team_index.get(fixture.away, predictor.unknown_index),
                "no_odds": extract_targets(fixture.odds) is None,
            }
            for fixture in group
        ]
        selected = select_views(rows, probabilities, predictor.counts, calibration, settings)
        views["most_likely"].extend(selected["most_likely"])
        views["stand_out"].extend(selected["stand_out"])

    most = finalise(views["most_likely"], "probability", settings)
    stand = finalise(views["stand_out"], "lift", settings)

    return {
        "date": round_date.isoformat(),
        "label": round_label(round_date),
        "weekday": WEEKDAY_NAMES[round_date.weekday()],
        "kind": kind,
        "cutoff": min(predictor.cutoff for predictor in predictors.values()).isoformat(),
        "config": settings,
        "fixtures": len(fixtures),
        "views": {
            "most_likely": {"label": VIEW_LABELS["most_likely"], "picks": most, "hits": 0, "settled_count": 0},
            "stand_out": {"label": VIEW_LABELS["stand_out"], "picks": stand, "hits": 0, "settled_count": 0},
        },
        "picks": most,
        "published": bool(most or stand),
        "settled": False,
        "hits": 0,
        "settled_count": 0,
    }


def settle_document(document: dict, results: dict) -> bool:
    changed = False
    views = document.get("views")
    pick_lists = [view.get("picks", []) for view in views.values()] if views else [document.get("picks", [])]

    for picks in pick_lists:
        for pick in picks:
            if pick.get("settled"):
                continue
            result = results.get((document["date"], pick["home"], pick["away"]))
            if result is None:
                continue
            fthg, ftag, hthg, htag = result
            outcome = OUTCOMES_BY_ID[pick["outcome"]]
            if outcome.needs_ht and (hthg is None or htag is None):
                continue
            pick["landed"] = bool(outcome.fn(fthg, ftag, hthg, htag))
            pick["settled"] = True
            pick["result"] = f"{fthg}-{ftag}" + (f" ({hthg}-{htag} HT)" if hthg is not None else "")
            changed = True

    total_hits = 0
    total_settled = 0
    total_picks = 0
    if views:
        for view in views.values():
            picks = view.get("picks", [])
            view["hits"] = sum(1 for pick in picks if pick.get("landed"))
            view["settled_count"] = sum(1 for pick in picks if pick.get("settled"))
            total_hits += view["hits"]
            total_settled += view["settled_count"]
            total_picks += len(picks)
    else:
        picks = document.get("picks", [])
        total_hits = sum(1 for pick in picks if pick.get("landed"))
        total_settled = sum(1 for pick in picks if pick.get("settled"))
        total_picks = len(picks)

    document["hits"] = total_hits
    document["settled_count"] = total_settled
    document["settled"] = bool(total_picks) and total_settled == total_picks
    return changed


def read_results(matches: list) -> dict:
    """(iso date, home, away) -> (fthg, ftag, hthg, htag)."""
    return {
        (match.date.isoformat(), match.home, match.away): (match.fthg, match.ftag, match.hthg, match.htag)
        for match in matches
    }


def publish(document: dict, picks_dir: Path, web_dir: Path) -> None:
    picks_dir.mkdir(parents=True, exist_ok=True)
    web_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    (picks_dir / f"{document['date']}.json").write_text(text, encoding="utf-8")
    (web_dir / f"{document['date']}.json").write_text(text, encoding="utf-8")


def document_views(document: dict) -> dict:
    """Views with a fallback for round files written before views existed."""
    views = document.get("views")
    if views:
        return views
    legacy = document.get("picks", [])
    return {"most_likely": {"label": VIEW_LABELS["most_likely"], "picks": legacy, "hits": document.get("hits", 0), "settled_count": document.get("settled_count", 0)}}


def rebuild_index(picks_dir: Path, web_dir: Path) -> dict:
    rounds = []
    for path in sorted(picks_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        views = document_views(document)
        most = views.get("most_likely", {}).get("picks", [])
        stand = views.get("stand_out", {}).get("picks", [])
        if not most and not stand:
            continue
        rounds.append(
            {
                "date": document["date"],
                "label": document["label"],
                "weekday": document["weekday"],
                "kind": document.get("kind", "round"),
                "picks": len(most),
                "stand_out": len(stand),
                "hits": document.get("hits", 0),
                "settled_count": document.get("settled_count", 0),
                "settled": document.get("settled", False),
            }
        )
    index = {"rounds": rounds}
    (web_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return index
