"""Deterministic retrospective model-fair tickets for existing rounds.

These are permanently labelled retrospective simulations. Forward proposals and
their actual frozen prices are handled only by pipeline/proposed_tickets.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import ranking, settlement
from .proposed_tickets import FLAT_STAKES, TARGETS, choose_target

DATES = ("2026-11-14", "2026-11-21", "2026-11-22")
SCHEMA_VERSION = 1
DEFINITION_VERSION = "retrospective-model-fair-v1"
DISCLAIMER = "Retrospective simulation — generated after the round; not a frozen pre-match recommendation."
FAIR_NOTE = "Model-fair odds — not realised bookmaker returns."
MIN_PC = 0.58


def _pc(row: dict) -> float:
    return float(row.get("pc", row.get("p", 0.0)))


def _status_map(picks_dir: Path, date: str) -> dict[tuple, str]:
    full = picks_dir / f"{date}.full.json"
    path = full if full.exists() else picks_dir / f"{date}.json"
    if not path.exists():
        return {}
    document = ranking.load(path)
    return {
        (row["d"], row["h"], row["a"], row["m"]): row.get("st", "pending")
        for row in document.get("rows", [])
    }


def _leg_key(leg: dict) -> tuple:
    return settlement.leg_key(leg)


def eligible_pool(document: dict) -> list[dict]:
    best: dict[tuple, dict] = {}
    for row in document.get("rows", []):
        if str(row.get("m", "")).startswith("CORRECT_SCORE:"):
            continue
        probability = _pc(row)
        if probability < MIN_PC:
            continue
        key = (row["d"], row["h"], row["a"])
        current = best.get(key)
        if current is None or probability > current["pc"]:
            best[key] = {
                "d": row["d"], "h": row["h"], "a": row["a"], "k": row.get("k"),
                "m": row["m"], "pc": probability, "fair": 1.0 / probability,
            }
    return sorted(best.values(), key=lambda leg: (-leg["pc"], leg["d"], leg["h"], leg["a"]))


def _combined(legs: list[dict]) -> tuple[float | None, float | None]:
    if not legs:
        return None, None
    probability = 1.0
    fair = 1.0
    for leg in legs:
        probability *= leg["pc"]
        fair *= leg["fair"]
    return probability, fair


def _proposal(kind: str, pool: list[dict]) -> dict:
    spec = TARGETS[kind]
    if kind == "best2":
        legs = pool[:2] if len(pool) >= 2 else None
        reason = "" if legs else "fewer than 2 eligible legs"
    else:
        legs, reason = choose_target(
            pool, spec["target"], spec["low"], spec["high"], spec["min_legs"], spec["max_legs"],
            price_key="fair",
        )
    probability, fair = _combined(legs or [])
    return {
        "type": kind,
        "label": spec["label"],
        "status": "available" if legs else "unavailable",
        "reason": reason,
        "flat_stake": FLAT_STAKES[kind] if legs else 0.0,
        "legs": legs or [],
        "combined_probability": None if probability is None else round(probability, 8),
        "combined_fair_odds": None if fair is None else round(fair, 6),
        "settlement": {"status": "unavailable" if not legs else "pending", "return": None, "profit": None, "source_pending": bool(legs), "leg_statuses": []},
    }


def _settle(proposal: dict, statuses: dict[tuple, str]) -> None:
    if proposal["status"] != "available":
        proposal["settlement"] = {"status": "unavailable", "return": None, "profit": None, "source_pending": False, "leg_statuses": []}
        return
    outcome = settlement.ticket_outcome(
        proposal["legs"], statuses, float(proposal["flat_stake"]), price_key="fair",
    )
    proposal["settlement"] = {
        "status": outcome["status"],
        "return": None if outcome["return"] is None else round(float(outcome["return"]), 4),
        "profit": None if outcome["profit"] is None else round(float(outcome["profit"]), 4),
        "source_pending": outcome["source_pending"],
        "leg_statuses": outcome["leg_statuses"],
    }


def _cumulative(rounds: list[dict]) -> dict:
    """Counts only. Retrospective model-fair money never enters a profit headline."""
    counts = {"tickets": 0, "settled": 0, "landed": 0, "lost": 0, "void": 0, "pending": 0, "unavailable": 0, "source_pending": 0}
    for round_doc in rounds:
        for proposal in round_doc["proposals"]:
            counts["tickets"] += 1
            outcome = proposal["settlement"]
            status = outcome["status"]
            counts[status] = counts.get(status, 0) + 1
            if outcome["source_pending"]:
                counts["source_pending"] += 1
            if status in ("landed", "lost", "void"):
                counts["settled"] += 1
    return counts


def generate_payload(picks_dir: Path) -> dict:
    rounds = []
    for date in DATES:
        path = picks_dir / f"{date}.json"
        if not path.exists():
            continue
        document = ranking.load(path)
        pool = eligible_pool(document)
        proposals = [_proposal(kind, pool) for kind in ("best2", "around3", "around5")]
        statuses = _status_map(picks_dir, date)
        for proposal in proposals:
            _settle(proposal, statuses)
        rounds.append({
            "round_date": date,
            "disclaimer": DISCLAIMER,
            "fair_odds_note": FAIR_NOTE,
            "proposals": proposals,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "definition_version": DEFINITION_VERSION,
        "retrospective": True,
        "disclaimer": DISCLAIMER,
        "fair_odds_note": FAIR_NOTE,
        "rounds": rounds,
        "cumulative": _cumulative(rounds),
    }


def settle_payload(payload: dict, picks_dir: Path) -> dict:
    rounds = []
    for round_doc in payload.get("rounds", []):
        current = {**round_doc, "proposals": []}
        statuses = _status_map(picks_dir, round_doc["round_date"])
        for proposal in round_doc["proposals"]:
            item = {**proposal, "legs": [dict(leg) for leg in proposal.get("legs", [])]}
            _settle(item, statuses)
            current["proposals"].append(item)
        rounds.append(current)
    return {**payload, "rounds": rounds, "cumulative": _cumulative(rounds)}


def write_payload(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.retrospective_tickets")
    parser.add_argument("command", choices=["generate", "settle"])
    parser.add_argument("--picks-dir", type=Path, default=Path("picks"))
    parser.add_argument("--output", type=Path, default=Path("web/public/data/retrospective-tickets.json"))
    args = parser.parse_args(argv)
    if args.command == "generate":
        payload = generate_payload(args.picks_dir)
    else:
        payload = settle_payload(json.loads(args.output.read_text(encoding="utf-8")), args.picks_dir)
    write_payload(args.output, payload)
    print(f"retrospective tickets: {len(payload['rounds'])} rounds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
