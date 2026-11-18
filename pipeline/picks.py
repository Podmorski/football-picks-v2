"""Picker: one best play per match, published rounds and settlement.

Rules: never FT home win / FT away win, probability capped below the configured
maximum, home team needs >= 8 home games and away team >= 8 away games, and the
counts and goals engines must agree within 0.10. One pick per match.
"""
from __future__ import annotations

import json
from pathlib import Path

from .fixtures import WEEKDAY_NAMES, Fixture
from .outcomes import OUTCOMES, OUTCOMES_BY_ID

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

DEFAULT_CONFIG = {
    "max_probability": 0.65,
    "top_n": 15,
    "min_samples": 8,
    "agreement": 0.10,
    "min_bin_sample": 100,
}

EXCLUDED = {"ft_1", "ft_2"}

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


def build_round(
    predictor,
    fixtures: list[Fixture],
    league_names: dict[str, str],
    round_date,
    calibration: dict | None = None,
    config: dict | None = None,
    kind: str = "round",
) -> dict:
    settings = {**DEFAULT_CONFIG, **(config or {})}
    if not fixtures:
        return {
            "date": round_date.isoformat(),
            "label": round_label(round_date),
            "weekday": WEEKDAY_NAMES[round_date.weekday()],
            "kind": kind,
            "cutoff": predictor.cutoff.isoformat(),
            "trained_matches": predictor.trained_matches,
            "picks": [],
            "published": False,
        }

    probabilities = predictor.probabilities(
        [fixture.home for fixture in fixtures],
        [fixture.away for fixture in fixtures],
        [fixture.odds for fixture in fixtures],
    )

    picks: list[dict] = []
    for row, fixture in enumerate(fixtures):
        n_home = float(probabilities["n_home"][row])
        n_away = float(probabilities["n_away"][row])
        if n_home < settings["min_samples"] or n_away < settings["min_samples"]:
            continue

        best = None
        for column, outcome in enumerate(OUTCOMES):
            if outcome.id in EXCLUDED:
                continue
            probability = float(probabilities["full"][row][column])
            if probability > settings["max_probability"]:
                continue
            gap = abs(float(probabilities["counts"][row][column]) - float(probabilities["odds"][row][column]))
            if gap > settings["agreement"]:
                continue
            if best is None or probability > best[0]:
                best = (probability, column, outcome, gap)

        if best is None:
            continue

        probability, column, outcome, gap = best
        bin_row = calibration_bin(calibration or {}, outcome.group, probability)
        home_index = predictor.team_index.get(fixture.home, predictor.unknown_index)
        away_index = predictor.team_index.get(fixture.away, predictor.unknown_index)

        picks.append(
            {
                "div": fixture.div,
                "league": league_names.get(fixture.div, fixture.div),
                "kickoff": fixture.time,
                "home": fixture.home,
                "away": fixture.away,
                "outcome": outcome.id,
                "label": outcome.label,
                "group": outcome.group,
                "play": PLAY_WORDS.get(outcome.id, outcome.label),
                "probability": round(probability, 4),
                "fair_odds": round(1.0 / probability, 2),
                "confidence": confidence_badge(min(n_home, n_away), gap, bin_row, settings["min_bin_sample"]),
                "why": {
                    "home_at_home": [
                        int(predictor.counts.home_hits[home_index][column]),
                        int(predictor.counts.home_counts[home_index]),
                    ],
                    "away_away": [
                        int(predictor.counts.away_hits[away_index][column]),
                        int(predictor.counts.away_counts[away_index]),
                    ],
                    "league_rate": [
                        round(float(predictor.counts.league_rates()[column]), 4),
                        int(predictor.counts.league_counts[column]),
                    ],
                    "engines": {
                        "counts": round(float(probabilities["counts"][row][column]), 4),
                        "goals": round(float(probabilities["odds"][row][column]), 4),
                        "gap": round(gap, 4),
                    },
                    "samples": {"home": round(n_home, 1), "away": round(n_away, 1)},
                    "bin": bin_row,
                },
                "settled": False,
                "landed": None,
                "result": None,
            }
        )

    picks.sort(key=lambda item: (-item["probability"], item["home"]))
    picks = picks[: settings["top_n"]]

    return {
        "date": round_date.isoformat(),
        "label": round_label(round_date),
        "weekday": WEEKDAY_NAMES[round_date.weekday()],
        "kind": kind,
        "cutoff": predictor.cutoff.isoformat(),
        "trained_matches": predictor.trained_matches,
        "config": settings,
        "picks": picks,
        "published": True,
        "settled": False,
        "hits": 0,
        "settled_count": 0,
    }


def settle_document(document: dict, results: dict) -> bool:
    changed = False
    for pick in document.get("picks", []):
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

    picks = document.get("picks", [])
    document["settled_count"] = sum(1 for pick in picks if pick.get("settled"))
    document["hits"] = sum(1 for pick in picks if pick.get("landed"))
    document["settled"] = bool(picks) and all(pick.get("settled") for pick in picks)
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


def rebuild_index(picks_dir: Path, web_dir: Path) -> dict:
    rounds = []
    for path in sorted(picks_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        rounds.append(
            {
                "date": document["date"],
                "label": document["label"],
                "weekday": document["weekday"],
                "kind": document.get("kind", "round"),
                "picks": len(document.get("picks", [])),
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
