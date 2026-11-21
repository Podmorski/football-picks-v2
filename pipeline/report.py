"""Best bets record for /report: ANY_RULE passing picks per settled round.

Rebuilt after every run_model pass (including the Monday settle) so the report is
automatic. Aggregates only; no Mozzart prices are involved.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import ranking, vetting

MIN_FAIR = 1.70
HIDDEN_PREFIX = "CORRECT_SCORE:"
STRONG_PROBABILITY = 0.55


def _probability(row: dict) -> float:
    return float(row.get("pc", row.get("p", 0.0)))


def _candidate(row: dict) -> vetting.Candidate:
    probability = _probability(row)
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
    )


def passing_picks(rows: list[dict]) -> list[dict]:
    """ANY_RULE, fair >= 1.70, one passing pick per match, highest probability."""
    best: dict[tuple, dict] = {}
    for row in rows:
        if str(row.get("m", "")).startswith(HIDDEN_PREFIX):
            continue
        probability = _probability(row)
        if 1.0 / max(probability, 1e-4) < MIN_FAIR:
            continue
        passed, _checks = vetting.evaluate(_candidate(row), vetting.DEFAULT_RULE)
        if not passed:
            continue
        key = (row.get("d"), row.get("h"), row.get("a"))
        current = best.get(key)
        if current is None or probability > _probability(current):
            best[key] = row
    return sorted(best.values(), key=_probability, reverse=True)


def summarise(rows: list[dict]) -> dict:
    picks = passing_picks(rows)
    settled = [row for row in picks if row.get("st") in ("landed", "lost")]
    landed = sum(1 for row in settled if row.get("st") == "landed")
    strong = [row for row in settled if _probability(row) >= STRONG_PROBABILITY]
    possible = [row for row in settled if _probability(row) < STRONG_PROBABILITY]
    return {
        "passing": len(picks),
        "settled": len(settled),
        "landed": landed,
        "pending": len(picks) - len(settled),
        "expected": round(sum(_probability(row) for row in settled), 4),
        "strong": {
            "settled": len(strong),
            "landed": sum(1 for row in strong if row.get("st") == "landed"),
        },
        "possible": {
            "settled": len(possible),
            "landed": sum(1 for row in possible if row.get("st") == "landed"),
        },
    }


def build(picks_dir: Path, web_dir: Path) -> dict:
    by_date: dict[str, dict] = {}
    for path in sorted(picks_dir.glob("*.json")):
        if path.name.endswith(".full.json"):
            continue
        document = ranking.load(path)
        date = document["date"]
        full = picks_dir / f"{date}.full.json"
        by_date[date] = ranking.load(full) if full.exists() else document

    rounds = []
    for date in sorted(by_date):
        document = by_date[date]
        stats = summarise(document.get("rows", []))
        rounds.append(
            {
                "date": date,
                "label": document.get("label", date),
                "kind": document.get("kind", "round"),
                **stats,
            }
        )

    def total(key: str) -> int:
        return sum(int(row[key]) for row in rounds)

    cumulative = {
        "passing": total("passing"),
        "settled": total("settled"),
        "landed": total("landed"),
        "pending": total("pending"),
        "expected": round(sum(float(row["expected"]) for row in rounds), 4),
        "strong": {
            "settled": sum(int(row["strong"]["settled"]) for row in rounds),
            "landed": sum(int(row["strong"]["landed"]) for row in rounds),
        },
        "possible": {
            "settled": sum(int(row["possible"]["settled"]) for row in rounds),
            "landed": sum(int(row["possible"]["landed"]) for row in rounds),
        },
    }

    payload = {"min_fair": MIN_FAIR, "strong_probability": STRONG_PROBABILITY, "rounds": rounds, "cumulative": cumulative}
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "best-bets-record.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return payload
