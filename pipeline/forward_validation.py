"""Whole-round forward validation for the frozen paper proposals.

Actual pre-match prices only. Whole round dates are resampled with every ticket
and leg retained; bankroll, unresolved exposure and drawdown are replayed through
each sequence. Aggregate output only: no leg or ticket prices are written.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random
from pathlib import Path

from . import bankroll, preregistration, proposed_tickets, ranking, settlement

SCHEMA_VERSION = 1
MIN_BOOTSTRAP_ROUNDS = 2
PRIMARY = ("flat", "mel")
Z_ALPHA = 1.6448536269514722
Z_POWER = 0.8416212335729143


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _status_map(picks_dir: Path, date: str) -> dict[tuple, str]:
    for name in (f"{date}.full.json", f"{date}.json"):
        path = picks_dir / name
        if path.exists():
            return {settlement.leg_key(row): row.get("st", "pending") for row in ranking.load(path).get("rows", [])}
    return {}


def _stake_of(policy: str):
    if policy == "flat":
        return lambda proposal: float(proposal.get("flat_stake", 0.0))
    return lambda proposal: float(((proposal.get("policies") or {}).get(policy) or {}).get("stake", 0.0))


def _round_record(document: dict, picks_dir: Path) -> dict:
    date = document["round_date"]
    statuses = _status_map(picks_dir, date)
    proposals = document.get("proposals", [])
    available = [proposal for proposal in proposals if proposal.get("status") == "available"]
    accounts = {
        policy: settlement.round_accounting(proposals, statuses, _stake_of(policy))
        for policy in ("flat", *proposed_tickets.POLICY_KEYS)
    }
    counts = {"available": len(available), "void": 0, "pending": 0, "settled": 0}
    flat = accounts["flat"]
    for outcome in flat["outcomes"]:
        counts[outcome["status"]] = counts.get(outcome["status"], 0) + 1
    construction = [proposal.get("construction") or {} for proposal in available]
    leg_uses = {}
    for proposal in available:
        for leg in proposal.get("legs", []):
            leg_uses[settlement.leg_key(leg)] = leg_uses.get(settlement.leg_key(leg), 0) + 1
    shared_tickets = sum(1 for proposal in available if any(leg_uses[settlement.leg_key(leg)] > 1 for leg in proposal.get("legs", [])))
    exposure = {key: 0.0 for key in proposed_tickets.TARGETS}
    for proposal in available:
        exposure[proposal["type"]] += float(proposal.get("policies", {}).get("mel", {}).get("stake", 0.0))
    return {
        **{policy: accounts[policy] for policy in ("flat", *proposed_tickets.POLICY_KEYS)},
        "round_date": date,
        "available": len(available),
        "counts": counts,
        "flat": flat, "mel": accounts["mel"],
        "construction": construction,
        "fixtures": sorted({(leg["d"], leg["h"], leg["a"]) for proposal in available for leg in proposal.get("legs", [])}),
        "shared_leg_instances": sum(max(0, count - 1) for count in leg_uses.values()),
        "shared_leg_tickets": shared_tickets,
        "exposure_by_type": exposure,
    }


def _policy_series(rounds: list[dict], policy: str) -> dict:
    bank = float(bankroll.INITIAL_BANKROLL)
    peak = bank
    maximum_drawdown = 0.0
    staked = returned = 0.0
    unresolved_exposure = 0.0
    terminal = losing = 0
    log_growth = []
    for record in sorted(rounds, key=lambda row: row["round_date"]):
        accounting = record[policy]
        if not accounting["terminal"]:
            unresolved_exposure += float(accounting["staked"])
            continue
        terminal += 1
        net = float(accounting["net"] or 0.0)
        staked += float(accounting["staked"])
        returned += float(accounting["returned"] or 0.0)
        if accounting["staked"] and net < 0:
            losing += 1
        if bank > 0:
            growth = math.log((bank + net) / bank) if bank + net > 0 else float("-inf")
            log_growth.append(growth)
        bank += net
        peak = max(peak, bank)
        maximum_drawdown = max(maximum_drawdown, (peak - bank) / peak if peak > 0 else 0.0)
    return {
        "terminal_rounds": terminal,
        "staked": round(staked, 6), "returned": round(returned, 6),
        "net": round(returned - staked, 6),
        "roi": round((returned - staked) / staked, 6) if staked else None,
        "bankroll": round(bank, 6), "peak": round(peak, 6),
        "maximum_drawdown": round(maximum_drawdown, 6),
        "losing_round_frequency": round(losing / terminal, 6) if terminal else None,
        "unresolved_exposure": round(unresolved_exposure, 6),
        "round_log_growth": [round(value, 10) for value in log_growth],
    }


def _bootstrap(rounds: list[dict], policy: str, rng: random.Random) -> dict:
    ordered = sorted(rounds, key=lambda row: row["round_date"])
    terminal_count = sum(1 for record in ordered if record[policy]["terminal"])
    if terminal_count < MIN_BOOTSTRAP_ROUNDS:
        return {"rounds": terminal_count, "roi_ci": [None, None], "log_growth_ci": [None, None],
                "max_drawdown_ci": [None, None], "unresolved_exposure_ci": [None, None],
                "mean_log_growth": None}
    draws_roi, draws_growth, draws_dd, draws_unresolved = [], [], [], []
    for _ in range(preregistration.BOOTSTRAP_RESAMPLES):
        sample = [ordered[rng.randrange(len(ordered))] for _ in ordered]
        bank = bankroll.INITIAL_BANKROLL
        peak = bank
        maximum_drawdown = 0.0
        unresolved = 0.0
        staked = net = 0.0
        terminal = 0
        log_sum = 0.0
        for record in sample:
            accounting = record[policy]
            if not accounting["terminal"]:
                unresolved += float(accounting["staked"])
                continue
            terminal += 1
            staked += float(accounting["staked"])
            round_net = float(accounting["net"] or 0.0)
            net += round_net
            if bank > 0 and bank + round_net > 0:
                log_sum += math.log((bank + round_net) / bank)
            bank += round_net
            peak = max(peak, bank)
            maximum_drawdown = max(maximum_drawdown, (peak - bank) / peak if peak > 0 else 0.0)
        draws_roi.append(net / staked if staked else 0.0)
        draws_growth.append(log_sum / terminal if terminal else 0.0)
        draws_dd.append(maximum_drawdown)
        draws_unresolved.append(unresolved)
    draws_roi.sort(); draws_growth.sort(); draws_dd.sort(); draws_unresolved.sort()
    def bounds(values):
        return [round(values[int(0.025 * (len(values) - 1))], 6), round(values[int(0.975 * (len(values) - 1))], 6)]
    return {
        "rounds": terminal_count, "roi_ci": bounds(draws_roi), "log_growth_ci": bounds(draws_growth),
        "max_drawdown_ci": bounds(draws_dd), "unresolved_exposure_ci": bounds(draws_unresolved),
        "mean_log_growth": round(sum(draws_growth) / len(draws_growth), 6),
    }


def _power(primary_series: dict) -> dict:
    values = primary_series["round_log_growth"]
    if len(values) < 2:
        return {"n_star": None, "reason": "fewer than two settled playable rounds; N* is not estimated"}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    sd = math.sqrt(variance)
    if sd <= 0:
        return {"n_star": None, "reason": "zero observed log-growth dispersion; N* is not estimated"}
    delta = preregistration.MEANINGFUL_LOG_GROWTH
    n_star = math.ceil(((Z_ALPHA + Z_POWER) * sd / delta) ** 2)
    return {
        "n_star": n_star, "observed_rounds": len(values),
        "observed_sd": round(sd, 6), "meaningful_log_growth": round(delta, 8),
        "alpha_one_sided": preregistration.ALPHA_ONE_SIDED, "power": preregistration.POWER,
        "source": "simulated from observed round log-growth dispersion; not a guarantee",
    }


def _ruin(rounds: list[dict], policy: str, rng: random.Random) -> dict:
    values = [record[policy]["net"] for record in rounds if record[policy]["terminal"]]
    if len(values) < 2:
        return {"upper_95": None, "reason": "fewer than two settled playable rounds"}
    outcomes = []
    for _ in range(preregistration.BOOTSTRAP_RESAMPLES):
        bank = bankroll.INITIAL_BANKROLL
        hit = 0
        for _step in range(preregistration.RUIN_HORIZON):
            bank += values[rng.randrange(len(values))]
            if bank <= bankroll.INITIAL_BANKROLL * preregistration.RUIN_THRESHOLD:
                hit = 1
                break
        outcomes.append(hit)
    probabilities = []
    for _ in range(preregistration.BOOTSTRAP_RESAMPLES):
        sample = [outcomes[rng.randrange(len(outcomes))] for _ in outcomes]
        probabilities.append(sum(sample) / len(sample))
    probabilities.sort()
    upper = probabilities[int(0.975 * (len(probabilities) - 1))]
    return {"upper_95": round(upper, 6), "paths": preregistration.BOOTSTRAP_RESAMPLES,
            "horizon": preregistration.RUIN_HORIZON, "threshold": preregistration.RUIN_THRESHOLD}


def build(prices_dir: Path, picks_dir: Path) -> dict:
    documents = []
    for path in sorted((prices_dir / "proposals").glob("*.json")):
        payload = _load(path)
        if payload.get("proposals"):
            documents.append(payload)
    rounds = [_round_record(document, picks_dir) for document in documents]
    rng = random.Random(preregistration.BOOTSTRAP_SEED)
    primary = {}
    for policy in PRIMARY:
        series = _policy_series(rounds, policy)
        primary[policy] = {**series, "bootstrap": _bootstrap(rounds, policy, rng)}
    exploratory = {}
    for policy in proposed_tickets.POLICY_KEYS:
        if policy in PRIMARY:
            continue
        series = _policy_series(rounds, policy)
        exploratory[policy] = {key: series[key] for key in ("terminal_rounds", "roi", "maximum_drawdown")}

    total_tickets = sum(record["available"] for record in rounds)
    counts = {
        "rounds": len(rounds), "terminal_rounds": sum(1 for record in rounds if record["flat"]["terminal"]),
        "tickets": total_tickets,
        "void": sum(record["counts"].get("void", 0) for record in rounds),
        "pending": sum(record["counts"].get("pending", 0) for record in rounds),
    }
    counts["void_frequency"] = round(counts["void"] / total_tickets, 6) if total_tickets else None
    counts["pending_frequency"] = round(counts["pending"] / total_tickets, 6) if total_tickets else None

    identity_failure = False
    for record in rounds:
        for policy in ("flat", "mel"):
            accounting = record[policy]
            if abs(sum(float(item["stake"]) for item in accounting["outcomes"]) - float(accounting["staked"])) > 1e-9:
                identity_failure = True
            if accounting["terminal"] and abs(
                sum(float(item["return"] or 0.0) for item in accounting["outcomes"]) - float(accounting["returned"] or 0.0)
            ) > 1e-9:
                identity_failure = True
    construction = [item for record in rounds for item in record["construction"]]
    fallbacks = {
        "individual_floor_relaxed": sum(1 for item in construction if item.get("individual_floor_relaxed")),
        "overlap_relaxed": sum(1 for item in construction if item.get("overlap_relaxed")),
        "outside_preferred_band": sum(1 for item in construction if item.get("band") in ("outside", "below_floor")),
        "bounded_dp": sum(1 for item in construction if item.get("method") == "bounded_dp"),
        "negative_model_ev": sum(1 for item in construction if False),  # filled below
    }
    negative = 0
    for document in documents:
        for proposal in document.get("proposals", []):
            if proposal.get("status") == "available" and float(proposal.get("model_ev", 0.0)) <= 0:
                negative += 1
    fallbacks["negative_model_ev"] = negative
    fallbacks["negative_model_ev_share"] = round(negative / total_tickets, 6) if total_tickets else None
    fallback_tickets = sum(
        1 for item in construction
        if item.get("individual_floor_relaxed") or item.get("overlap_relaxed") or item.get("band") in ("outside", "below_floor")
    )
    fallbacks["any_fallback_tickets"] = fallback_tickets
    fallbacks["fallback_frequency"] = round(fallback_tickets / total_tickets, 6) if total_tickets else None

    exposure = {
        "by_type_mel_stake": {key: round(sum(record["exposure_by_type"].get(key, 0.0) for record in rounds), 6) for key in proposed_tickets.TARGETS},
        "fixtures": sum(len(record["fixtures"]) for record in rounds),
        "shared_leg_instances": sum(record["shared_leg_instances"] for record in rounds),
        "shared_leg_tickets": sum(record["shared_leg_tickets"] for record in rounds),
    }

    power = _power(primary["mel"])
    lower = primary["mel"]["bootstrap"]["log_growth_ci"][0]
    positive = bool(power.get("n_star") and counts["terminal_rounds"] >= power["n_star"] and lower is not None and lower > 0)
    inconclusive = bool(counts["terminal_rounds"] >= preregistration.INCONCLUSIVE_ROUNDS and not positive)
    ruin = _ruin(rounds, "mel", rng)
    safety = {
        "maximum_drawdown": primary["mel"]["maximum_drawdown"],
        "drawdown_review": primary["mel"]["maximum_drawdown"] >= preregistration.SAFETY_DRAWDOWN,
        "identity_failure": identity_failure,
        "ruin_upper_95": ruin.get("upper_95"),
        "stop_adaptive": bool(ruin.get("upper_95") is not None and ruin["upper_95"] > preregistration.RUIN_UPPER_LIMIT),
        "owner_loss_budget": None,
    }
    state = "no settled playable rounds" if not counts["terminal_rounds"] else (
        "inconclusive" if inconclusive else "positive evidence" if positive else "accumulating"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "counts": counts,
        "primary": primary,
        "exploratory": exploratory,
        "exposure": exposure,
        "fallbacks": fallbacks,
        "power": power,
        "evidence": {
            "n_star": power.get("n_star"), "settled_playable_rounds": counts["terminal_rounds"],
            "lower_95_log_growth": lower, "positive": positive, "inconclusive": inconclusive,
            "rule": "positive growth requires at least N* settled playable rounds and a whole-round-bootstrap lower 95% bound above zero",
            "no_early_efficacy_stopping": True,
        },
        "safety": safety,
        "protocol": preregistration.build()["protocol"],
        "notes": [
            "Actual pre-match prices only; no retrospective fair-odds substitution.",
            "Flat and MEL-v1 are the primary pre-registered comparison; other policies are exploratory diagnostics.",
            "Every policy consumes the same frozen proposals and round-atomic settlement.",
            "Do not select a policy because it has the best observed test return.",
            "Small samples and multiple comparisons: treat every exploratory return as descriptive.",
        ],
        "small_sample": counts["terminal_rounds"] < 30,
        "multiple_comparisons": "exploratory policies and splits are descriptive; do not select the best observed return",
        "bootstrap": {"unit": "whole round date", "resamples": preregistration.BOOTSTRAP_RESAMPLES, "seed": preregistration.BOOTSTRAP_SEED},
    }


def write(prices_dir: Path, picks_dir: Path, web_dir: Path) -> dict:
    payload = build(prices_dir, picks_dir)
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "forward-validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return payload


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="pipeline.forward_validation")
    parser.add_argument("--prices-dir", required=True, type=Path)
    parser.add_argument("--picks-dir", type=Path, default=Path("picks"))
    parser.add_argument("--web-dir", type=Path, default=Path("web/public/data"))
    args = parser.parse_args(argv)
    payload = write(args.prices_dir, args.picks_dir, args.web_dir)
    print(f"forward validation: {payload['counts']['rounds']} rounds, state {payload['state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
