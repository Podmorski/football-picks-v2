"""Forward proposal readiness and aggregate paper results.

Counts only. Actual prices stay in the private store; this public file carries
activation/version, eligible round, construction fallbacks, overlap, negative
model-EV and price-coverage counts, plus the frozen-price paper ledger.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import bankroll, proposed_tickets

SCHEMA_VERSION = 1


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _snapshots(prices_dir: Path | None) -> list[dict]:
    if prices_dir is None:
        return []
    out = []
    for path in sorted((prices_dir / "rounds").glob("*.json")):
        payload = _load(path)
        if payload.get("round_date"):
            out.append(payload)
    return out


def build(prices_dir: Path | None, picks_dir: Path, web_dir: Path) -> dict:
    snapshots = _snapshots(prices_dir)
    eligible = sorted(
        row["round_date"] for row in snapshots
        if row["round_date"] >= proposed_tickets.PROPOSAL_ACTIVATION_DATE and row.get("fixtures")
    )
    eligible_round = eligible[0] if eligible else None
    missing = proposed_tickets.missing_required_proposals(prices_dir) if prices_dir is not None else []

    documents = []
    legacy_rounds = 0
    if prices_dir is not None:
        for path in sorted((prices_dir / "proposals").glob("*.json")):
            payload = _load(path)
            if not payload.get("proposals"):
                continue
            if payload.get("schema_version") != proposed_tickets.SCHEMA_VERSION:
                legacy_rounds += 1
                continue
            documents.append(payload)
    evaluation_start_round = min(
        (row["round_date"] for row in documents if row.get("round_date")), default=None,
    )

    bands = Counter()
    tickets = available = unavailable = 0
    floor_relaxed = overlap_relaxed = negative_ev = 0
    methods = Counter()
    for document in documents:
        for proposal in document.get("proposals", []):
            tickets += 1
            if proposal.get("status") != "available":
                unavailable += 1
                bands["unavailable"] += 1
                continue
            available += 1
            construction = proposal.get("construction") or {}
            bands[construction.get("band", "unknown")] += 1
            floor_relaxed += int(bool(construction.get("individual_floor_relaxed")))
            overlap_relaxed += int(bool(construction.get("overlap_relaxed")))
            methods[construction.get("method", "unknown")] += 1
            negative_ev += int(float(proposal.get("model_ev", 0.0)) <= 0)

    coverage = {
        "snapshot_rounds": len(snapshots),
        "fixtures": sum(len(row.get("fixtures", [])) for row in snapshots),
        "priced_fixtures": sum(1 for row in snapshots for fixture in row.get("fixtures", []) if fixture.get("prices")),
        "priced_markets": sum(len(fixture.get("prices", {})) for row in snapshots for fixture in row.get("fixtures", [])),
        "started_not_priced": sum(len(row.get("started_not_priced", [])) for row in snapshots),
        "unmatched_fixtures": sum(len(row.get("unmatched_fixtures", [])) for row in snapshots),
    }

    record = _load(web_dir / "proposed-tickets-record.json")
    if missing:
        state = "required frozen proposal data missing"
    elif eligible_round is None:
        state = "awaiting first eligible published round with fixtures and a usable snapshot"
    elif documents:
        state = "frozen proposals available"
    elif legacy_rounds:
        state = "frozen legacy proposals only; ticket-construction-v3 awaits an eligible round"
    else:
        state = "eligible round exists; proposal file not yet frozen"

    errors = []
    if prices_dir is None or not (prices_dir / "rounds").exists():
        errors.append("private proposal store not available in this build; counters are zero and no actual prices are shown")
    if missing:
        errors.append(
            f"missing required frozen proposal file for snapshot round(s): {', '.join(missing)} "
            f"(activation {proposed_tickets.PROPOSAL_ACTIVATION_DATE})"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "activation_date": proposed_tickets.PROPOSAL_ACTIVATION_DATE,
        "policy_version": bankroll.POLICY_VERSION,
        "construction_version": proposed_tickets.CONSTRUCTION_VERSION,
        "evaluation_id": proposed_tickets.EVALUATION_ID,
        "eligible_round": eligible_round,
        "evaluation_start_round": evaluation_start_round,
        "state": state,
        "errors": errors,
        "rounds_with_proposals": len(documents),
        "legacy_rounds": legacy_rounds,
        "counts": {
            "tickets": tickets, "available": available, "unavailable": unavailable,
            "bands": dict(bands), "individual_floor_relaxed": floor_relaxed,
            "overlap_relaxed": overlap_relaxed, "negative_model_ev": negative_ev,
            "negative_model_ev_share": round(negative_ev / available, 6) if available else None,
            "search_methods": dict(methods),
        },
        "price_coverage": coverage,
        "evaluation": {
            "id": proposed_tickets.EVALUATION_ID,
            "construction_version": proposed_tickets.CONSTRUCTION_VERSION,
            "policy_version": bankroll.POLICY_VERSION,
            "start_round": evaluation_start_round,
            "pooling_rule": "v2 and v3 records are separate forward evaluations and are never pooled",
            "unsupported_same_fixture_rule": "flat proposals are retained; new MEL exposure is zero with reason unsupported same-fixture dependence",
        },
        "results": {
            "source": "proposed-tickets-record.json",
            "counts": record.get("counts", {}),
            "flat": record.get("flat", {}), "mel": record.get("mel", {}),
            "types": record.get("types", {}),
            "note": "Forward frozen-price paper results. Not an executable-return or profit claim.",
            "has_settled_data": bool((record.get("counts") or {}).get("settled", 0)),
        },
    }


def write(prices_dir: Path | None, picks_dir: Path, web_dir: Path) -> dict:
    payload = build(prices_dir, picks_dir, web_dir)
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "forward-proposals.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return payload


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="pipeline.forward_proposals")
    parser.add_argument("--prices-dir", type=Path)
    parser.add_argument("--picks-dir", type=Path, default=Path("picks"))
    parser.add_argument("--web-dir", type=Path, default=Path("web/public/data"))
    args = parser.parse_args(argv)
    payload = write(args.prices_dir, args.picks_dir, args.web_dir)
    print(f"forward proposals: state {payload['state']}, eligible round {payload['eligible_round']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
