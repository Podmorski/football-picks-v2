"""MEL-v1 mandatory-exposure paper allocation and diagnostic comparators.

MEL-v1 is a paper bankroll simulation, not a proven optimum. Displayed pc is
never changed; MEL uses conservative q values with frozen provenance. Scenarios
are binary pre-match win/loss states over the unique legs of the three tickets.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from . import ranking, settlement
from .markets import MARKET_BY_ID

INITIAL_BANKROLL = 1000.0
MEL_DRAWDOWN_SCALE = 0.20
MEL_BASE_FRACTION = 0.0025
MEL_SLOPE = 0.0175
MEL_MIN_RESIDUAL_DATES = 30
MEL_FALLBACK_SHIFT = -0.05
MEL_SHIFT_QUANTILE = 0.10
MEL_BOOTSTRAP_RESAMPLES = 2000
MEL_BOOTSTRAP_SEED = 20261123
MEL_STRESS_SHIFT = -0.05
NO_FORCED_TOTAL_CAP = 0.02
NO_FORCED_TICKET_CAP = 0.01
NO_FORCED_KELLY_FRACTION = 0.25
FIXED_FRACTIONAL_FRACTION = 0.10
MARTINGALE_BASE = 1.0
MARTINGALE_CAP = 32.0
FLAT_SHARES = (0.5, 0.3, 0.2)
POLICY_VERSION = "mel-v1"


def band_of(probability: float) -> str:
    percent = probability * 100.0
    if percent < 20:
        return "lt20"
    for low in (20, 30, 40, 50, 60, 70):
        if low <= percent < low + 10:
            return f"{low}-{low + 10}"
    return "80plus"


def drawdown(bankroll: float, peak: float) -> float:
    return (peak - bankroll) / peak if peak > 0 else 0.0


def mel_total_stake(available: float, current_drawdown: float) -> float:
    if available <= 0:
        return 0.0
    multiplier = max(0.0, 1.0 - current_drawdown / MEL_DRAWDOWN_SCALE)
    return available * (MEL_BASE_FRACTION + MEL_SLOPE * multiplier)


def _market_group(market: str) -> str | None:
    item = MARKET_BY_ID.get(market)
    return item.group if item is not None else None


def _prior_documents(prices_dir: Path, before_date: str, schema_version: int | None = None) -> list[dict]:
    documents = []
    for path in sorted((prices_dir / "proposals").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if schema_version is not None and document.get("schema_version") != schema_version:
            continue
        if document.get("round_date", "") < before_date:
            documents.append(document)
    return documents


def _round_rows(picks_dir: Path, date: str) -> list[dict]:
    for name in (f"{date}.full.json", f"{date}.json"):
        path = picks_dir / name
        if path.exists():
            return ranking.load(path).get("rows", [])
    return []


def residual_dates(picks_dir: Path, before_date: str) -> dict[tuple[str, str], list[float]]:
    """Per-round-date mean residual y - pc for every group x pc-band cohort."""
    by_cohort: dict[tuple[str, str], dict[str, list[float]]] = {}
    for path in sorted(picks_dir.glob("*.json")):
        if path.name.endswith(".full.json"):
            continue
        date = path.name[:-5]
        if not date < before_date:
            continue
        for row in _round_rows(picks_dir, date):
            if row.get("st") not in ("landed", "lost"):
                continue
            market = str(row.get("m", ""))
            if market.startswith("CORRECT_SCORE:"):
                continue
            group = _market_group(market)
            if group is None:
                continue
            probability = float(row.get("pc", row.get("p", 0.0)))
            if not 0.0 < probability < 1.0:
                continue
            outcome = 1.0 if row["st"] == "landed" else 0.0
            cohort = (group, band_of(probability))
            by_cohort.setdefault(cohort, {}).setdefault(date, []).append(outcome - probability)
    out = {}
    for cohort, dates in by_cohort.items():
        out[cohort] = [sum(values) / len(values) for _date, values in sorted(dates.items())]
    return out


def cohort_shift(dates: list[float], rng: random.Random) -> float:
    if len(dates) < MEL_MIN_RESIDUAL_DATES:
        return MEL_FALLBACK_SHIFT
    draws = []
    for _ in range(MEL_BOOTSTRAP_RESAMPLES):
        sample = [dates[rng.randrange(len(dates))] for _ in dates]
        draws.append(sum(sample) / len(sample))
    draws.sort()
    index = int(MEL_SHIFT_QUANTILE * (len(draws) - 1))
    return min(0.0, draws[index])


def conservative_q(probability: float, cohort: tuple[str, str], shifts: dict[tuple[str, str], float]) -> float:
    shift = shifts.get(cohort, MEL_FALLBACK_SHIFT)
    return min(0.999, max(0.001, probability + shift))


def annotate_q(proposals: list[dict], shifts: dict[tuple[str, str], float]) -> None:
    for proposal in proposals:
        for leg in proposal.get("legs", []):
            group = _market_group(leg["m"])
            cohort = (group or "Unknown", band_of(float(leg["pc"])))
            leg["cohort"] = f"{cohort[0]}|{cohort[1]}"
            leg["q"] = round(conservative_q(float(leg["pc"]), cohort, shifts), 6)


def scenarios(proposals: list[dict], shift: float = 0.0) -> tuple[list[dict], dict]:
    """Binary pre-match scenarios over unique legs; shared legs share one state."""
    available = [proposal for proposal in proposals if proposal.get("status") == "available"]
    unique: dict[tuple, float] = {}
    for proposal in available:
        for leg in proposal["legs"]:
            q = float(leg["q"]) + shift
            unique[settlement.leg_key(leg)] = min(0.999, max(0.001, q))
    keys = sorted(unique)
    outcomes = []
    for mask in range(1 << len(keys)):
        won = {key: bool(mask >> index & 1) for index, key in enumerate(keys)}
        probability = 1.0
        for key in keys:
            q = unique[key]
            probability *= q if won[key] else (1.0 - q)
        gross = []
        for proposal in available:
            if all(won[settlement.leg_key(leg)] for leg in proposal["legs"]):
                gross.append(float(proposal["combined_odds"]) - 1.0)
            else:
                gross.append(-1.0)
        outcomes.append({"probability": probability, "net": gross})
    total = sum(item["probability"] for item in outcomes)
    if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise AssertionError(f"scenario probabilities sum to {total}")
    return outcomes, {"unique_legs": len(keys), "scenarios": len(outcomes), "assumption": "cross-fixture conditional independence; exact shared legs reused"}


def _log_allocation(A: float, total: float, outcomes: list[dict], cap: float) -> tuple[list[float], dict]:
    count = len(outcomes[0]["net"]) if outcomes else 0
    if count == 0 or total <= 0:
        return [0.0] * count, {"status": "zero", "message": "no available exposure"}
    weights = np.array([item["probability"] for item in outcomes])
    returns = np.array([item["net"] for item in outcomes])

    def objective(stakes):
        wealth = A + returns @ stakes
        if np.any(wealth[weights > 0] <= 0):
            return 1e12
        return -float(np.sum(weights * np.log(wealth)))

    bounds = [(0.0, cap)] * count
    constraint = {"type": "eq", "fun": lambda stakes: float(np.sum(stakes) - total)}
    start = np.full(count, min(total / count, cap))
    if np.sum(start) < total - 1e-12:
        start = np.full(count, cap)
    result = minimize(objective, start, method="SLSQP", bounds=bounds, constraints=[constraint],
                      options={"maxiter": 1000, "ftol": 1e-12})
    stakes = [float(value) for value in result.x]
    feasible = result.success and abs(sum(stakes) - total) <= 1e-6 and all(-1e-12 <= value <= cap + 1e-9 for value in stakes)
    if not feasible:
        raise RuntimeError(f"MEL allocation failed: {result.message}")
    return stakes, {"status": "ok", "method": "SLSQP", "iterations": int(result.nit), "objective": round(float(result.fun), 8)}


def _shares(count: int) -> list[float]:
    weights = list(FLAT_SHARES[:count]) if count <= 3 else [1 / count] * count
    total = sum(weights)
    return [weight / total for weight in weights]


def allocate(proposals: list[dict], state: dict, outcomes: list[dict]) -> dict:
    available = [proposal for proposal in proposals if proposal.get("status") == "available"]
    count = len(available)
    A = float(state["available"])
    S = float(state["mel_total_stake"])
    result = {
        "available": A, "total_stake": S, "tickets": count,
        "mandatory_exposure": bool(S > 0), "negative_ev": all(float(p.get("model_ev", 0)) <= 0 for p in available),
        "message": "mandatory exposure; no positive-edge claim" if available and all(float(p.get("model_ev", 0)) <= 0 for p in available) else "",
    }
    if count == 0:
        return {**result, "stakes": [], "solver": {"status": "zero", "message": "no available tickets"}}
    cap = S / 2.0 if count >= 2 else S
    if S <= 0:
        stakes = [0.0] * count
        solver = {"status": "zero", "message": "A = 0 solvency exception" if A <= 0 else "zero total exposure"}
    else:
        stakes, solver = _log_allocation(A, S, outcomes, cap)
    result["stakes"] = stakes
    result["solver"] = solver
    # Simultaneous one-notch q shock: re-solve, do not present as a confidence bound.
    shocked, _meta = scenarios(proposals, shift=MEL_STRESS_SHIFT)
    stress_stakes, stress_solver = _log_allocation(A, S, shocked, cap) if S > 0 else ([0.0] * count, {"status": "zero"})
    result["stress"] = {
        "shift": MEL_STRESS_SHIFT, "stakes": [round(value, 6) for value in stress_stakes],
        "status": stress_solver["status"], "note": "Stress analysis, not a confidence interval or guaranteed bound.",
    }
    return result


def fixed_fractional(available: float, count: int) -> tuple[float, list[float]]:
    total = max(0.0, FIXED_FRACTIONAL_FRACTION * available)
    return total, [total * share for share in _shares(count)]


def probability_weighted(proposals: list[dict], total: float) -> list[float]:
    available = [proposal for proposal in proposals if proposal.get("status") == "available"]
    probabilities = [float(proposal["combined_probability"]) for proposal in available]
    denominator = sum(probabilities)
    if denominator <= 0:
        return [total / len(available)] * len(available) if available else []
    return [total * probability / denominator for probability in probabilities]


def minimum_variance(proposals: list[dict], state: dict, outcomes: list[dict]) -> tuple[list[float], dict]:
    available = [proposal for proposal in proposals if proposal.get("status") == "available"]
    count = len(available)
    S = float(state["mel_total_stake"])
    if count == 0 or S <= 0:
        return [0.0] * count, {"status": "zero"}
    returns = np.array([item["net"] for item in outcomes])
    weights = np.array([item["probability"] for item in outcomes])
    mean = np.average(returns, axis=0, weights=weights)
    centred = returns - mean
    covariance = (centred * weights[:, None]).T @ centred
    covariance = (covariance + covariance.T) / 2.0
    cap = S / 2.0 if count >= 2 else S

    def objective(stakes):
        return float(stakes @ covariance @ stakes)

    result = minimize(objective, np.full(count, min(S / count, cap)), method="SLSQP",
                      bounds=[(0.0, cap)] * count,
                      constraints=[{"type": "eq", "fun": lambda stakes: float(np.sum(stakes) - S)}],
                      options={"maxiter": 1000, "ftol": 1e-14})
    stakes = [float(value) for value in result.x]
    if not result.success or abs(sum(stakes) - S) > 1e-6:
        raise RuntimeError(f"minimum-variance allocation failed: {result.message}")
    return stakes, {"status": "ok", "method": "SLSQP", "iterations": int(result.nit)}


def no_forced_kelly(proposals: list[dict], state: dict, outcomes: list[dict]) -> tuple[float, list[float], dict]:
    available = [proposal for proposal in proposals if proposal.get("status") == "available"]
    count = len(available)
    A = float(state["available"])
    if count == 0 or A <= 0:
        return 0.0, [0.0] * count, {"status": "zero", "message": "no available bankroll"}
    robust_ev = [
        sum(item["probability"] * item["net"][index] for item in outcomes)
        for index in range(count)
    ]
    if all(value <= 1e-12 for value in robust_ev):
        return 0.0, [0.0] * count, {"status": "zero", "message": "no positive robust edge"}
    multiplier = max(0.0, 1.0 - float(state["drawdown"]) / MEL_DRAWDOWN_SCALE)
    total_cap = NO_FORCED_TOTAL_CAP * A * multiplier
    # A single available ticket cannot carry the whole 2% total cap: the 1%
    # per-ticket cap is binding. This preserves both caps without changing MEL.
    total_cap = min(total_cap, NO_FORCED_TICKET_CAP * A)
    stakes, solver = _log_allocation(A, total_cap, outcomes, NO_FORCED_TICKET_CAP * A)
    stakes = [NO_FORCED_KELLY_FRACTION * value for value in stakes]
    total = sum(stakes)
    return total, stakes, {"status": "ok" if total > 0 else "zero", "method": "SLSQP", "iterations": solver.get("iterations")}


def martingale_multiplier(
    prices_dir: Path, picks_dir: Path, before_date: str, schema_version: int | None = None,
) -> tuple[float, dict]:
    multiplier = 1.0
    rounds = 0
    for document in _prior_documents(prices_dir, before_date, schema_version):
        accounting = settlement.round_accounting(
            document.get("proposals", []), _status_map(picks_dir, document["round_date"]),
            lambda proposal: float(proposal.get("flat_stake", 0.0)),
        )
        if not accounting["terminal"]:
            continue
        rounds += 1
        if float(accounting["net"] or 0.0) < 0:
            multiplier *= 2.0
        else:
            multiplier = 1.0
    return multiplier, {"rounds": rounds, "multiplier": multiplier}


def _status_map(picks_dir: Path, date: str) -> dict[tuple, str]:
    return {
        settlement.leg_key(row): row.get("st", "pending")
        for row in _round_rows(picks_dir, date)
    }


def policy_state(
    prices_dir: Path, picks_dir: Path, before_date: str, schema_version: int | None = None,
) -> dict:
    documents = _prior_documents(prices_dir, before_date, schema_version)
    mel_stake = lambda proposal: float(((proposal.get("policies") or {}).get("mel") or {}).get("stake", 0.0))
    replay = settlement.replay_bankroll(
        documents, lambda date: _status_map(picks_dir, date), mel_stake, INITIAL_BANKROLL,
    )
    bankroll = replay["bankroll"]
    peak = replay["peak"]
    current = drawdown(bankroll, peak)
    available = replay["available"]
    total = mel_total_stake(available, current)
    multiplier, martingale = martingale_multiplier(prices_dir, picks_dir, before_date, schema_version)
    return {
        "bankroll": bankroll, "peak": peak, "drawdown": current,
        "unresolved_exposure": replay["unresolved_exposure"], "available": available,
        "mel_total_stake": round(total, 4), "martingale": martingale,
        "initial_bankroll": INITIAL_BANKROLL,
    }
