"""Versioned published-pick reconstructions for the three visible rounds.

The pick pool is the exact pool displayed at the round's first publication
commit. Tickets are constructed later with ticket-construction-v2 using
model-fair odds only. Settlement status is applied after construction and is
never read by pool selection or construction. This is not a forward proposal
and its model-fair accounting is not realised profit.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from . import ranking, settlement, ticket_construction

SCHEMA_VERSION = 2
DEFINITION_VERSION = "published-pick-reconstruction-v1"
DATES = ("2026-11-14", "2026-11-21", "2026-11-22")
PROVENANCE_DIR = Path(__file__).resolve().parent / "provenance"
SAMPLE = "Tickets constructed later from that pool; these were not frozen automatic proposals before kickoff."
EXAMPLE = "Retrospective example round; no pre-match publication."
FAIR_NOTE = (
    "Model-fair pricing - 1/pc. No verified usable pre-match actual price was available for every "
    "selected leg; not realised bookmaker returns."
)


def load_provenance(date: str, directory: Path = PROVENANCE_DIR) -> dict:
    return json.loads((directory / f"{date}.json").read_text(encoding="utf-8"))


def _disclaimer(provenance: dict) -> str:
    return (
        f"Published pick pool reproduced from commit {provenance['publication_commit']} "
        f"({provenance['rule_version']}). {SAMPLE}"
    )


def pool_menu(provenance: dict) -> list[dict]:
    """Pure transformation: no result or status fields are read."""
    menu = []
    for leg in provenance.get("pool", []):
        market = str(leg.get("m", ""))
        if market.startswith(ticket_construction.HIDDEN_PREFIX) or leg.get("group") == "Correct score":
            continue
        probability = float(leg["pc"])
        fair = float(leg["fair"])
        menu.append({
            "d": leg["d"], "h": leg["h"], "a": leg["a"], "k": leg.get("k"),
            "m": market, "label": leg.get("label", market), "group": leg.get("group", ""),
            "pc": probability, "fair": fair, "odds": fair,
        })
    return menu


def construct(provenance: dict) -> list[dict]:
    """Apply ticket-construction-v2 to the fixed published pool."""
    proposals = ticket_construction.construct(pool_menu(provenance))
    out = []
    for proposal in proposals:
        construction = dict(proposal.get("construction") or {})
        construction["algorithm"] = ticket_construction.CONSTRUCTION_VERSION
        construction["applied_later"] = True
        if "achieved_odds" in construction:
            construction["achieved_fair_odds"] = construction.pop("achieved_odds")
        legs = [
            {
                "d": leg["d"], "k": leg.get("k"), "h": leg["h"], "a": leg["a"],
                "m": leg["m"], "label": leg.get("label", leg["m"]), "group": leg.get("group", ""),
                "pc": leg["pc"], "fair": leg["fair"],
            }
            for leg in proposal.get("legs", [])
        ]
        out.append({
            "type": proposal["type"], "label": proposal["label"], "status": proposal["status"],
            "reason": proposal.get("reason", ""), "legs": legs,
            "combined_probability": proposal.get("combined_probability"),
            "combined_fair_odds": proposal.get("combined_odds"),
            "construction": construction,
        })
    return out


def _status_map(picks_dir: Path, date: str) -> dict[tuple, str]:
    for name in (f"{date}.full.json", f"{date}.json"):
        path = picks_dir / name
        if path.exists():
            document = ranking.load(path)
            return {
                (row["d"], row["h"], row["a"], row["m"]): row.get("st", "pending")
                for row in document.get("rows", [])
            }
    return {}


def _settlement(proposal: dict, statuses: dict[tuple, str], date: str) -> dict:
    if date == "2026-11-14":
        return {"status": "not_reconstructed", "source_pending": False, "leg_statuses": []}
    if proposal["status"] != "available" or not proposal.get("legs"):
        return {"status": "unavailable", "source_pending": False, "leg_statuses": []}
    outcome = settlement.ticket_outcome(proposal["legs"], statuses, 1.0, price_key="fair")
    return {
        "status": outcome["status"],
        "source_pending": outcome["source_pending"],
        "leg_statuses": outcome["leg_statuses"],
    }


def build_round(provenance: dict, statuses: dict[tuple, str]) -> dict:
    proposals = construct(provenance)
    for proposal in proposals:
        proposal["settlement"] = _settlement(proposal, statuses, provenance["date"])
    return {
        "round_date": provenance["date"],
        "kind": provenance["kind"],
        "pre_match_publication": bool(provenance["pre_match_publication"]),
        "disclaimer": _disclaimer(provenance),
        "example_disclaimer": EXAMPLE if provenance["kind"] == "example" else "",
        "pricing_note": FAIR_NOTE,
        "pick_pool_count": len(provenance.get("pool", [])),
        "provenance": {
            "source_publication_commit": provenance["publication_commit"],
            "publication_time": provenance["publication_time"],
            "rule_version": provenance["rule_version"],
            "rule_source": provenance["rule_source"],
            "prediction_input_hash": provenance["prediction_input_hash"],
            "pool_hash": provenance["pool_hash"],
            "pricing_mode": provenance.get("pricing_mode", "model-fair"),
            "pre_match_publication": bool(provenance["pre_match_publication"]),
            "current_fields_match": bool((provenance.get("current_comparison") or {}).get("match")),
            "construction_version": ticket_construction.CONSTRUCTION_VERSION,
        },
        "proposals": proposals,
    }


def _cumulative(rounds: list[dict]) -> dict:
    counts = {"tickets": 0, "settled": 0, "landed": 0, "lost": 0, "void": 0,
              "pending": 0, "unavailable": 0, "not_reconstructed": 0, "source_pending": 0}
    for round_doc in rounds:
        for proposal in round_doc["proposals"]:
            counts["tickets"] += 1
            outcome = proposal["settlement"]
            status = outcome["status"]
            counts[status] = counts.get(status, 0) + 1
            if status in ("landed", "lost", "void"):
                counts["settled"] += 1
            if outcome["source_pending"]:
                counts["source_pending"] += 1
    return counts


def generate_payload(directory: Path = PROVENANCE_DIR, picks_dir: Path = Path("picks")) -> dict:
    rounds = []
    for date in DATES:
        provenance = load_provenance(date, directory)
        rounds.append(build_round(provenance, _status_map(picks_dir, date)))
    return {
        "schema_version": SCHEMA_VERSION,
        "definition_version": DEFINITION_VERSION,
        "pricing_mode": "model-fair",
        "rounds": rounds,
        "cumulative": _cumulative(rounds),
    }


def settle_payload(payload: dict, picks_dir: Path) -> dict:
    rounds = []
    for round_doc in payload.get("rounds", []):
        current = copy.deepcopy(round_doc)
        statuses = _status_map(picks_dir, round_doc["round_date"])
        for proposal in current.get("proposals", []):
            proposal["settlement"] = _settlement(proposal, statuses, round_doc["round_date"])
        rounds.append(current)
    return {**payload, "rounds": rounds, "cumulative": _cumulative(rounds)}


def write_payload(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.published_reconstructions")
    parser.add_argument("command", choices=["generate", "settle"])
    parser.add_argument("--provenance-dir", type=Path, default=PROVENANCE_DIR)
    parser.add_argument("--picks-dir", type=Path, default=Path("picks"))
    parser.add_argument("--output", type=Path, default=Path("web/public/data/published-reconstructions.json"))
    args = parser.parse_args(argv)
    if args.command == "generate":
        payload = generate_payload(args.provenance_dir, args.picks_dir)
    else:
        payload = settle_payload(json.loads(args.output.read_text(encoding="utf-8")), args.picks_dir)
    write_payload(args.output, payload)
    print(f"published reconstructions: {len(payload['rounds'])} rounds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
