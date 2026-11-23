"""Best bets record for /report: the unified 58%+ picker per settled round.

Rebuilt after every run_model pass so the report is automatic. The Any-bet
record uses the dashboard's default minimum fair odds (1.20). Aggregates only;
no Mozzart prices are involved.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import ranking

MIN_PC = 0.58
MIN_FAIR = 1.20
HIDDEN_PREFIX = "CORRECT_SCORE:"


def _probability(row: dict) -> float:
    return float(row.get("pc", row.get("p", 0.0)))


def passing_picks(rows: list[dict]) -> list[dict]:
    """Inclusive 58% calibrated probability, fair odds >= 1.20, one pick per match, highest pc."""
    best: dict[tuple, dict] = {}
    for row in rows:
        if str(row.get("m", "")).startswith(HIDDEN_PREFIX):
            continue
        probability = _probability(row)
        if probability < MIN_PC:
            continue
        if 1.0 / max(probability, 0.0001) < MIN_FAIR:
            continue
        key = (row.get("d"), row.get("h"), row.get("a"))
        current = best.get(key)
        if current is None or probability > _probability(current):
            best[key] = row
    return sorted(best.values(), key=_probability, reverse=True)


def summarise(rows: list[dict]) -> dict:
    picks = passing_picks(rows)
    landed = sum(1 for row in picks if row.get("st") == "landed")
    lost = sum(1 for row in picks if row.get("st") == "lost")
    void = sum(1 for row in picks if row.get("st") == "void")
    pending = len(picks) - landed - lost - void
    settled = landed + lost
    assert landed + lost + void + pending == len(picks)
    expected = round(sum(_probability(row) for row in picks if row.get("st") in ("landed", "lost")), 4)
    return {
        "passing": len(picks),
        "settled": settled,
        "landed": landed,
        "lost": lost,
        "void": void,
        "pending": pending,
        "expected": expected,
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
        "lost": total("lost"),
        "void": total("void"),
        "pending": total("pending"),
        "expected": round(sum(float(row["expected"]) for row in rounds), 4),
    }
    assert cumulative["landed"] + cumulative["lost"] + cumulative["void"] + cumulative["pending"] == cumulative["passing"]

    payload = {"min_pc": MIN_PC, "min_fair": MIN_FAIR, "rounds": rounds, "cumulative": cumulative}
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "best-bets-record.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return payload
