"""Frozen automatic round proposals and paper ledgers.

Actual leg/ticket prices live only in the private price store. Public aggregates
contain no individual prices. This module never fetches a price.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import random

from . import bankroll, ranking, settlement, ticket_construction
from .model.ranked_backtest import _clustered_mean_ci
from .model.ranking_backtest import RETURN_BOOTSTRAP_RESAMPLES, RETURN_BOOTSTRAP_SEED

MAX_LEGS = 5
# Rounds on/after this date require a frozen proposal file once a usable snapshot exists.
# Earlier snapshots are explicitly exempt because proposals were not generated then.
PROPOSAL_ACTIVATION_DATE = "2026-11-24"
PROPOSAL_ACTIVATION_MARKER = "proposal-readiness-v1"
SCHEMA_VERSION = 3
SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3)
POLICY_VERSION = bankroll.POLICY_VERSION
CONSTRUCTION_VERSION = ticket_construction.CONSTRUCTION_VERSION_V3
EVALUATION_ID = "ticket-construction-v3+mel-v1"
INITIAL_BANKROLL = 1000.0
PER_TICKET_CAP = 0.01
ROUND_CAP = 0.02
DRAWDOWN_HALF = 0.10
DRAWDOWN_STOP = 0.20
MIN_CI_ROUNDS = 30
FLAT_STAKES = {"best2": 50.0, "around3": 30.0, "around5": 20.0}
TARGETS = {
    "best2": {"label": "High-probability", "target": None, "low": None, "high": None, "min_legs": 2, "max_legs": 3},
    "around3": {"label": "Around 3.00", "target": 3.0, "low": 2.70, "high": 3.30, "min_legs": 1, "max_legs": 3},
    "around5": {"label": "5–10 combo", "target": 7.0, "low": 5.00, "high": 10.00, "min_legs": 3, "max_legs": 5},
}


def _pc(row: dict) -> float:
    return float(row.get("pc", row.get("p", 0.0)))


def _leg_key(leg: dict) -> tuple:
    return settlement.leg_key(leg)


def eligible_pool(document: dict, snapshot: dict) -> list[dict]:
    """Backward-compatible name for the full priced candidate menu."""
    return ticket_construction.candidate_menu(document, snapshot)


def _combined(legs: list[dict], price_key: str = "odds") -> tuple[float, float]:
    probability = 1.0
    odds = 1.0
    for leg in legs:
        probability *= leg["pc"]
        odds *= leg[price_key]
    return probability, odds


def _enumerated_best(pool: list[dict], low: float, high: float, target: float, min_legs: int, max_legs: int, price_key: str = "odds") -> tuple[list[dict] | None, str]:
    best_band = None
    best_closest = None
    for size in range(min_legs, min(max_legs, len(pool)) + 1):
        for combo in itertools.combinations(pool, size):
            probability, odds = _combined(list(combo), price_key)
            candidate = (probability, -abs(odds - target), list(combo), odds)
            if low <= odds <= high and (best_band is None or candidate[:2] > best_band[:2]):
                best_band = candidate
            if best_closest is None or (-abs(odds - target), probability) > (best_closest[1], best_closest[0]):
                best_closest = candidate
    chosen = best_band or best_closest
    if chosen is None:
        return None, "no eligible 2-5 leg combination"
    reason = "" if best_band else "no combination in the preferred odds band; closest actual odds used"
    return chosen[2], reason


def _dp_best(pool: list[dict], low: float, high: float, target: float, min_legs: int, max_legs: int, price_key: str = "odds") -> tuple[list[dict] | None, str]:
    """Bounded exact-state DP for larger priced pools; band membership is rechecked."""
    cap = max(high * 2.0, target * 2.0)
    step = 0.001
    states: dict[tuple[int, int], tuple[float, float, tuple[int, ...]]] = {(0, 0): (1.0, 1.0, ())}
    for index, leg in enumerate(pool):
        current = list(states.items())
        for (size, bucket), (probability, odds, combo) in current:
            if size >= max_legs:
                continue
            new_odds = odds * leg[price_key]
            if new_odds > cap:
                continue
            new_probability = probability * leg["pc"]
            key = (size + 1, round(math.log(new_odds) / step))
            existing = states.get(key)
            if existing is None or new_probability > existing[0]:
                states[key] = (new_probability, new_odds, combo + (index,))
    best_band = None
    best_closest = None
    for (size, _bucket), (probability, odds, combo) in states.items():
        if size < min_legs or size > max_legs:
            continue
        legs = [pool[index] for index in combo]
        if low <= odds <= high and (best_band is None or probability > best_band[0]):
            best_band = (probability, legs, odds)
        distance = abs(odds - target)
        if best_closest is None or distance < abs(best_closest[2] - target) or (
            distance == abs(best_closest[2] - target) and probability > best_closest[0]
        ):
            best_closest = (probability, legs, odds)
    chosen = best_band or best_closest
    if chosen is None:
        return None, "no eligible 2-5 leg combination"
    return chosen[1], "" if best_band else "no combination in the preferred odds band; closest actual odds used"


def choose_target(pool: list[dict], target: float, low: float, high: float, min_legs: int = 2, max_legs: int = 5, price_key: str = "odds") -> tuple[list[dict] | None, str]:
    if len(pool) < min_legs:
        return None, f"fewer than {min_legs} eligible legs"
    if len(pool) <= 18:
        return _enumerated_best(pool, low, high, target, min_legs, max_legs, price_key)
    return _dp_best(pool, low, high, target, min_legs, max_legs, price_key)


def _round_document(picks_dir: Path, date: str) -> dict | None:
    path = picks_dir / f"{date}.json"
    return ranking.load(path) if path.exists() else None


def _status_map(picks_dir: Path, date: str) -> dict[tuple, str]:
    full = picks_dir / f"{date}.full.json"
    path = full if full.exists() else picks_dir / f"{date}.json"
    if not path.exists():
        return {}
    document = ranking.load(path)
    return {_leg_key(row): row.get("st", "pending") for row in document.get("rows", [])}


def ticket_result(proposal: dict, statuses: dict[tuple, str]) -> dict:
    stake = float((proposal.get("adaptive") or {}).get("stake", 0.0))
    outcome = settlement.ticket_outcome(proposal.get("legs", []), statuses, stake)
    return {key: outcome[key] for key in ("status", "stake", "return", "profit")}


def _adaptive_stake(proposal: dict) -> float:
    return float((proposal.get("adaptive") or {}).get("stake", 0.0))


def replay_adaptive(prices_dir: Path, picks_dir: Path, before_date: str) -> dict:
    documents = []
    for path in sorted((prices_dir / "proposals").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != SCHEMA_VERSION:
            continue
        if document.get("round_date", "") >= before_date:
            continue
        documents.append(document)
    state = settlement.replay_bankroll(
        documents, lambda date: _status_map(picks_dir, date), _adaptive_stake, INITIAL_BANKROLL,
    )
    return {
        "bankroll": state["bankroll"], "peak": state["peak"], "drawdown": state["drawdown"],
        "unresolved_exposure": state["unresolved_exposure"], "available": state["available"],
    }


def _adaptive_allocations(proposals: list[dict], state: dict) -> None:
    available = float(state["available"])
    drawdown = float(state["drawdown"])
    multiplier = 0.0 if drawdown >= DRAWDOWN_STOP else 0.5 if drawdown >= DRAWDOWN_HALF else 1.0
    raw = []
    for proposal in proposals:
        base = {"stake": 0.0, "edge": None, "kelly_full": None, "kelly_quarter": None, "cap_applied": False, "reason": ""}
        if proposal["status"] != "available" or available <= 0 or multiplier == 0:
            base["reason"] = "no available bankroll" if available <= 0 or multiplier == 0 else "ticket unavailable"
            proposal["adaptive"] = base
            continue
        edge = proposal["combined_probability"] * proposal["combined_odds"] - 1.0
        base["edge"] = round(edge, 6)
        if edge <= 0 or proposal["combined_odds"] <= 1.0:
            base["reason"] = "edge <= 0"
            proposal["adaptive"] = base
            continue
        full = edge / (proposal["combined_odds"] - 1.0)
        raw_stake = min(PER_TICKET_CAP * available, 0.25 * full * available) * multiplier
        base.update({"kelly_full": round(full, 8), "kelly_quarter": round(full * 0.25, 8)})
        proposal["adaptive"] = base
        raw.append((proposal, raw_stake))
    cap = ROUND_CAP * available
    total = sum(value for _proposal, value in raw)
    scale = cap / total if total > cap and total > 0 else 1.0
    for proposal, value in raw:
        stake = max(0.0, value * scale)
        proposal["adaptive"]["stake"] = round(stake, 4)
        proposal["adaptive"]["cap_applied"] = scale < 1.0 or stake >= PER_TICKET_CAP * available - 1e-9


def _default_state() -> dict:
    return {
        "bankroll": INITIAL_BANKROLL, "peak": INITIAL_BANKROLL, "drawdown": 0.0,
        "unresolved_exposure": 0.0, "available": INITIAL_BANKROLL,
        "mel_total_stake": round(bankroll.mel_total_stake(INITIAL_BANKROLL, 0.0), 4),
        "martingale": {"rounds": 0, "multiplier": 1.0}, "initial_bankroll": INITIAL_BANKROLL,
    }


def build_proposals(
    document: dict, snapshot: dict, prior_state: dict | None = None,
    prices_dir: Path | None = None, picks_dir: Path | None = None,
) -> dict:
    date = document["date"]
    menu = eligible_pool(document, snapshot)
    proposals = []
    for item in ticket_construction.construct_v3(menu):
        key = item["type"]
        proposals.append({**item, "flat_stake": FLAT_STAKES[key] if item["status"] == "available" else 0.0})
    dependence = ticket_construction.unsupported_same_fixture_dependence(proposals)

    shifts: dict[tuple[str, str], float] = {}
    if picks_dir is not None:
        residuals = bankroll.residual_dates(picks_dir, date)
        rng = random.Random(bankroll.MEL_BOOTSTRAP_SEED)
        shifts = {cohort: bankroll.cohort_shift(dates, rng) for cohort, dates in residuals.items()}
    bankroll.annotate_q(proposals, shifts)
    state = prior_state or (
        bankroll.policy_state(prices_dir, picks_dir, date, schema_version=SCHEMA_VERSION)
        if prices_dir is not None and picks_dir is not None
        else _default_state()
    )

    outcomes, scenario_meta = bankroll.scenarios(proposals)
    scenario_meta["same_fixture_dependence"] = dependence
    if dependence:
        scenario_meta["assumption"] += "; unsupported same-fixture dependence detected; MEL exposure forced to zero"
        mel = {
            "available": float(state["available"]), "total_stake": 0.0,
            "tickets": sum(1 for proposal in proposals if proposal.get("status") == "available"),
            "mandatory_exposure": False,
            "negative_ev": all(float(proposal.get("model_ev", 0.0)) <= 0
                               for proposal in proposals if proposal.get("status") == "available"),
            "message": "unsupported same-fixture dependence",
            "stakes": [0.0] * sum(1 for proposal in proposals if proposal.get("status") == "available"),
            "solver": {"status": "blocked", "message": "unsupported same-fixture dependence"},
            "stress": {
                "shift": bankroll.MEL_STRESS_SHIFT,
                "stakes": [0.0] * sum(1 for proposal in proposals if proposal.get("status") == "available"),
                "status": "blocked",
                "note": "MEL exposure is zero because the joint scenario model does not represent same-fixture dependence.",
            },
        }
    else:
        mel = bankroll.allocate(proposals, state, outcomes)
    available = [proposal for proposal in proposals if proposal.get("status") == "available"]
    fixed_total, fixed_stakes = bankroll.fixed_fractional(state["available"], len(available))
    probability_stakes = bankroll.probability_weighted(proposals, state["mel_total_stake"])
    variance_stakes, _variance_meta = bankroll.minimum_variance(proposals, state, outcomes)
    kelly_total, kelly_stakes, _kelly_meta = bankroll.no_forced_kelly(proposals, state, outcomes)
    martingale_multiplier = float((state.get("martingale") or {}).get("multiplier", 1.0))
    shares = bankroll._shares(len(available))

    index = 0
    for proposal in proposals:
        if proposal.get("status") != "available":
            proposal["policies"] = {
                "flat": {"stake": 0.0}, "mel": {"stake": 0.0},
                "fixed_fractional": {"stake": 0.0}, "no_forced_kelly": {"stake": 0.0},
                "probability_weighted": {"stake": 0.0}, "minimum_variance": {"stake": 0.0},
                "martingale_capped": {"stake": 0.0}, "martingale_uncapped": {"stake": 0.0},
            }
            proposal["mel"] = {"stake": 0.0, "reason": "ticket unavailable"}
            proposal["adaptive"] = {"stake": 0.0, "edge": None, "kelly_full": None,
                                    "kelly_quarter": None, "cap_applied": False,
                                    "reason": "ticket unavailable", "policy": POLICY_VERSION}
            proposal["benchmarks"] = {}
            continue
        mel_stake = float(mel["stakes"][index])
        martingale_uncapped = bankroll.MARTINGALE_BASE * martingale_multiplier * shares[index]
        martingale_capped = min(martingale_uncapped, bankroll.MARTINGALE_CAP)
        proposal["policies"] = {
            "flat": {"stake": proposal["flat_stake"]},
            "mel": {"stake": round(mel_stake, 6)},
            "fixed_fractional": {"stake": round(fixed_stakes[index], 6)},
            "no_forced_kelly": {"stake": round(kelly_stakes[index], 6)},
            "probability_weighted": {"stake": round(probability_stakes[index], 6)},
            "minimum_variance": {"stake": round(variance_stakes[index], 6)},
            "martingale_capped": {"stake": round(martingale_capped, 6)},
            "martingale_uncapped": {"stake": round(martingale_uncapped, 6)},
        }
        proposal["mel"] = {
            "stake": round(mel_stake, 6), "total_stake": mel["total_stake"],
            "mandatory_exposure": mel["mandatory_exposure"], "negative_ev": mel["negative_ev"],
            "message": mel["message"], "solver": mel["solver"], "stress": mel["stress"],
        }
        proposal["adaptive"] = {
            "stake": round(mel_stake, 6), "edge": proposal.get("model_ev"),
            "kelly_full": None, "kelly_quarter": None, "cap_applied": False,
            "reason": mel["message"], "policy": POLICY_VERSION,
        }
        proposal["benchmarks"] = {
            name: {"stake": proposal["policies"][name]["stake"]}
            for name in ("fixed_fractional", "no_forced_kelly", "probability_weighted",
                         "minimum_variance", "martingale_capped", "martingale_uncapped")
        }
        index += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "construction_version": CONSTRUCTION_VERSION,
        "evaluation_id": EVALUATION_ID,
        "round_date": date,
        "snapshot_identity": {"round_date": snapshot.get("round_date"), "fetched_at": snapshot.get("fetched_at")},
        "policy": {
            "version": POLICY_VERSION, "construction_version": CONSTRUCTION_VERSION,
            "initial_bankroll": INITIAL_BANKROLL,
            "mel": {
                "supported": not dependence,
                "reason": "unsupported same-fixture dependence" if dependence else "",
                "drawdown_scale": bankroll.MEL_DRAWDOWN_SCALE,
                "base_fraction": bankroll.MEL_BASE_FRACTION, "slope": bankroll.MEL_SLOPE,
                "residual_quantile": bankroll.MEL_SHIFT_QUANTILE,
                "residual_fallback": bankroll.MEL_FALLBACK_SHIFT,
                "minimum_residual_dates": bankroll.MEL_MIN_RESIDUAL_DATES,
                "stress_shift": bankroll.MEL_STRESS_SHIFT,
            },
            "comparators": {
                "fixed_fractional": bankroll.FIXED_FRACTIONAL_FRACTION,
                "no_forced_total_cap": bankroll.NO_FORCED_TOTAL_CAP,
                "no_forced_ticket_cap": bankroll.NO_FORCED_TICKET_CAP,
                "no_forced_kelly_fraction": bankroll.NO_FORCED_KELLY_FRACTION,
                "martingale_base": bankroll.MARTINGALE_BASE,
                "martingale_cap": bankroll.MARTINGALE_CAP,
                "flat_shares": list(bankroll.FLAT_SHARES),
            },
            "flat_stakes": FLAT_STAKES,
            "scenarios": scenario_meta,
        },
        "state_before": state,
        "proposals": proposals,
    }


class ProposalReadinessError(RuntimeError):
    pass


def _proposal_is_valid(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    proposals = payload.get("proposals")
    return (
        payload.get("schema_version") in SUPPORTED_SCHEMA_VERSIONS
        and isinstance(proposals, list)
        and len(proposals) == 3
        and {item.get("type") for item in proposals} == set(TARGETS)
    )


def missing_required_proposals(prices_dir: Path) -> list[str]:
    """Snapshot-backed rounds after activation that lack a valid frozen proposal."""
    missing = []
    for path in sorted((prices_dir / "rounds").glob("*.json")):
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        round_date = str(snapshot.get("round_date", ""))
        if round_date < PROPOSAL_ACTIVATION_DATE or not snapshot.get("fixtures"):
            continue
        if not _proposal_is_valid(prices_dir / "proposals" / f"{round_date}.json"):
            missing.append(round_date)
    return missing


def validate_required_proposals(prices_dir: Path) -> None:
    missing = missing_required_proposals(prices_dir)
    if missing:
        raise ProposalReadinessError(
            f"missing required frozen proposal file for snapshot round(s): {', '.join(missing)} "
            f"(activation {PROPOSAL_ACTIVATION_DATE}, marker {PROPOSAL_ACTIVATION_MARKER})"
        )


def ensure_proposals(round_date: str, document: dict, snapshot: dict, prices_dir: Path, picks_dir: Path) -> dict:
    path = prices_dir / "proposals" / f"{round_date}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    state = bankroll.policy_state(prices_dir, picks_dir, round_date, schema_version=SCHEMA_VERSION)
    payload = build_proposals(document, snapshot, state, prices_dir, picks_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return payload


POLICY_KEYS = ("mel", "fixed_fractional", "no_forced_kelly", "probability_weighted", "minimum_variance", "martingale_capped", "martingale_uncapped")


def _policy_stake(policy: str):
    def getter(proposal: dict) -> float:
        return float(((proposal.get("policies") or {}).get(policy) or {}).get("stake", 0.0))
    return getter


def _empty_account(initial: float) -> dict:
    return {
        "staked": 0.0, "returned": 0.0, "bankroll": initial, "peak": initial,
        "unresolved": 0.0, "max_drawdown": 0.0, "series": [], "date_rows": [],
    }


def _ledger(account: dict) -> dict:
    net = account["returned"] - account["staked"]
    return {
        "staked": round(account["staked"], 4), "returned": round(account["returned"], 4),
        "net": round(net, 4), "roi": round(net / account["staked"], 6) if account["staked"] else None,
    }


def _bankroll_block(account: dict) -> dict:
    drawdown = (account["peak"] - account["bankroll"]) / account["peak"] if account["peak"] > 0 else 0.0
    return {
        **_ledger(account), "initial_bankroll": INITIAL_BANKROLL,
        "bankroll": round(account["bankroll"], 4), "peak": round(account["peak"], 4),
        "current_drawdown": round(drawdown, 6),
        "maximum_drawdown": round(account["max_drawdown"], 6),
        "unresolved_exposure": round(account["unresolved"], 4),
        "series": account["series"],
    }


def _advance(account: dict, accounting: dict, date: str) -> None:
    if accounting["terminal"]:
        account["staked"] += accounting["staked"]
        account["returned"] += float(accounting["returned"] or 0.0)
        if accounting["staked"] > 0:
            account["date_rows"].append([accounting["staked"], float(accounting["net"] or 0.0)])
        account["bankroll"] += float(accounting["net"] or 0.0)
        account["peak"] = max(account["peak"], account["bankroll"])
        account["max_drawdown"] = max(
            account["max_drawdown"],
            (account["peak"] - account["bankroll"]) / account["peak"] if account["peak"] > 0 else 0.0,
        )
        unresolved = account["unresolved"]
    else:
        account["unresolved"] += accounting["exposure"]
        unresolved = account["unresolved"]
    account["series"].append({
        "round_date": date, "bankroll": round(account["bankroll"], 4),
        "terminal": accounting["terminal"], "unresolved_exposure": round(unresolved, 4),
    })


def aggregate_records(prices_dir: Path, picks_dir: Path) -> dict:
    rounds = []
    type_stats = {
        key: {
            "tickets": 0, "settled": 0, "landed": 0, "lost": 0, "void": 0, "pending": 0,
            "flat_staked": 0.0, "flat_returned": 0.0, "mel_staked": 0.0, "mel_returned": 0.0,
        }
        for key in TARGETS
    }
    flat_account = _empty_account(INITIAL_BANKROLL)
    accounts = {key: _empty_account(INITIAL_BANKROLL) for key in POLICY_KEYS}
    counts = Counter()
    legacy_rounds = 0
    for path in sorted((prices_dir / "proposals").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != SCHEMA_VERSION:
            legacy_rounds += 1
            continue
        date = document["round_date"]
        statuses = _status_map(picks_dir, date)
        proposals = document.get("proposals", [])
        flat = settlement.round_accounting(
            proposals, statuses, lambda proposal: float(proposal.get("flat_stake", 0.0)),
        )
        policy_accounting = {
            key: settlement.round_accounting(proposals, statuses, _policy_stake(key))
            for key in POLICY_KEYS
        }
        round_row = {
            "round_date": date, "terminal": flat["terminal"],
            "available": len(flat["outcomes"]), "unavailable": 0, "pending": 0,
            "void": 0, "settled": 0, "flat_staked": 0.0, "flat_returned": 0.0,
            "mel_staked": 0.0, "mel_returned": 0.0,
        }
        for proposal in proposals:
            stats = type_stats[proposal["type"]]
            stats["tickets"] += 1
            counts["tickets"] += 1
            if proposal.get("status") != "available":
                round_row["unavailable"] += 1
                stats["unavailable"] = stats.get("unavailable", 0) + 1
                counts["unavailable"] += 1
        for outcome in flat["outcomes"]:
            proposal = outcome["proposal"]
            stats = type_stats[proposal["type"]]
            status = outcome["status"]
            if status == "pending":
                round_row["pending"] += 1
                stats["pending"] += 1
                counts["pending"] += 1
                continue
            round_row["settled"] += 1
            stats["settled"] += 1
            stats[status] += 1
            counts[status] += 1
            if status == "void":
                round_row["void"] += 1
            if not flat["terminal"]:
                # Atomic rounds: a terminal ticket in a still-pending round does
                # not move ledger money until every ticket in the round is terminal.
                continue
            gross = float(outcome["gross_multiplier"])
            flat_return = outcome["stake"] * gross
            mel_stake = _policy_stake("mel")(proposal)
            mel_return = mel_stake * gross
            round_row["flat_staked"] += outcome["stake"]
            round_row["flat_returned"] += flat_return
            round_row["mel_staked"] += mel_stake
            round_row["mel_returned"] += mel_return
            stats["flat_staked"] += outcome["stake"]
            stats["flat_returned"] += flat_return
            stats["mel_staked"] += mel_stake
            stats["mel_returned"] += mel_return

        _advance(flat_account, {**flat, "unresolved": 0.0}, date)
        for key in POLICY_KEYS:
            _advance(accounts[key], policy_accounting[key], date)
        round_row["flat_net"] = round(round_row["flat_returned"] - round_row["flat_staked"], 4)
        round_row["mel_net"] = round(round_row["mel_returned"] - round_row["mel_staked"], 4)
        rounds.append(round_row)

    def ci(account: dict) -> list:
        if len(account["date_rows"]) < MIN_CI_ROUNDS:
            return [None, None]
        _mean, bounds = _clustered_mean_ci(
            account["date_rows"], 0, 1, resamples=RETURN_BOOTSTRAP_RESAMPLES, seed=RETURN_BOOTSTRAP_SEED,
        )
        return [None if value is None else round(value, 6) for value in bounds]

    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "construction_version": CONSTRUCTION_VERSION,
        "evaluation_id": EVALUATION_ID,
        "rounds": rounds,
        "counts": {
            "rounds": len(rounds), "tickets": counts["tickets"],
            "settled": counts["landed"] + counts["lost"] + counts["void"],
            "pending": counts["pending"], "void": counts["void"],
            "unavailable": counts["unavailable"], "unpriced": 0,
            "legacy_rounds": legacy_rounds,
        },
        "flat": {
            **_ledger(flat_account), "return_ci": ci(flat_account),
            "ci_rounds": len(flat_account["date_rows"]),
        },
        "mel": {
            **_bankroll_block(accounts["mel"]), "return_ci": ci(accounts["mel"]),
            "ci_rounds": len(accounts["mel"]["date_rows"]),
        },
        "benchmarks": {
            key: {
                **_bankroll_block(accounts[key]), "return_ci": ci(accounts[key]),
                "ci_rounds": len(accounts[key]["date_rows"]),
            }
            for key in POLICY_KEYS if key != "mel"
        },
        "types": type_stats,
        "note": "Paper ledger for ticket-construction-v3 only. Flat is 50/30/20; MEL-v1 is mandatory-exposure expected-log allocation; other policies are diagnostics. Bankroll advances once per fully terminal round. v2/v3 records are never pooled. Not a profit guarantee.",
    }


def write_aggregate(prices_dir: Path, picks_dir: Path, web_dir: Path) -> dict:
    payload = aggregate_records(prices_dir, picks_dir)
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "proposed-tickets-record.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.proposed_tickets")
    parser.add_argument("command", choices=["aggregate"])
    parser.add_argument("--prices-dir", required=True)
    parser.add_argument("--picks-dir", type=Path, default=Path("picks"))
    parser.add_argument("--web-dir", type=Path, default=Path("web/public/data"))
    args = parser.parse_args(argv)
    try:
        validate_required_proposals(Path(args.prices_dir))
    except ProposalReadinessError as exc:
        print(f"ERROR: {exc}")
        return 2
    payload = write_aggregate(Path(args.prices_dir), args.picks_dir, args.web_dir)
    print(f"proposal ledger: {payload['counts']['rounds']} rounds, {payload['counts']['tickets']} tickets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
