"""Shared ticket settlement and round-atomic paper accounting.

Every ledger (forward flat, forward adaptive, retrospective model-fair) uses the
same gross-return rules. Bankroll, peak and drawdown advance once per round,
after every ticket in that round is terminal, so ticket order cannot change the
result.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable

TERMINAL_STATUSES = frozenset({"landed", "lost", "void"})


def leg_key(leg: dict) -> tuple:
    return (leg["d"], leg["h"], leg["a"], leg["m"])


def leg_statuses(legs: Iterable[dict], statuses: dict[tuple, str]) -> list[str]:
    return [statuses.get(leg_key(leg), "pending") for leg in legs]


def ticket_outcome(legs: list[dict], statuses: dict[tuple, str], stake: float, price_key: str = "odds") -> dict:
    """Settle one paper ticket with the shared gross-multiplier rules.

    * Any lost leg: multiplier 0.
    * All legs void: multiplier 1 (stake returned).
    * Mixed landed/void: product of actual prices for landed legs only.
    * Any pending leg: no bankroll movement.
    """
    states = leg_statuses(legs, statuses)
    stake = float(stake)
    if any(state == "lost" for state in states):
        return {
            "status": "lost", "stake": stake, "return": 0.0, "profit": -stake,
            "gross_multiplier": 0.0, "leg_statuses": states, "source_pending": False,
        }
    if not states or any(state not in TERMINAL_STATUSES for state in states):
        return {
            "status": "pending", "stake": stake, "return": None, "profit": None,
            "gross_multiplier": None, "leg_statuses": states,
            "source_pending": all(state == "pending" for state in states),
        }
    if all(state == "void" for state in states):
        return {
            "status": "void", "stake": stake, "return": stake, "profit": 0.0,
            "gross_multiplier": 1.0, "leg_statuses": states, "source_pending": False,
        }
    multiplier = 1.0
    for leg, state in zip(legs, states):
        if state == "landed":
            multiplier *= float(leg[price_key])
    returned = stake * multiplier
    return {
        "status": "landed", "stake": stake, "return": returned, "profit": returned - stake,
        "gross_multiplier": multiplier, "leg_statuses": states, "source_pending": False,
    }


def round_accounting(
    proposals: list[dict], statuses: dict[tuple, str], stake_of: Callable[[dict], float],
    price_key: str = "odds",
) -> dict:
    """One round's tickets and its single aggregate result.

    A round is terminal only when every available ticket is terminal. Until then
    its whole stake is reserved as unresolved exposure and no bankroll change is
    applied. This is what makes accounting independent of ticket order.
    """
    outcomes = []
    for proposal in proposals:
        if proposal.get("status") != "available":
            continue
        stake = float(stake_of(proposal))
        outcome = ticket_outcome(proposal.get("legs", []), statuses, stake, price_key)
        outcomes.append({"proposal": proposal, **outcome})

    terminal = all(item["status"] in TERMINAL_STATUSES for item in outcomes)
    staked = sum(item["stake"] for item in outcomes)
    if not terminal:
        return {
            "terminal": False, "outcomes": outcomes, "staked": staked,
            "returned": None, "net": None, "exposure": staked,
        }
    returned = sum(float(item["return"] or 0.0) for item in outcomes)
    return {
        "terminal": True, "outcomes": outcomes, "staked": staked,
        "returned": returned, "net": returned - staked, "exposure": 0.0,
    }


def replay_bankroll(
    rounds: Iterable[dict], statuses_for_date: Callable[[str], dict[tuple, str]],
    stake_of: Callable[[dict], float], initial_bankroll: float, price_key: str = "odds",
) -> dict:
    """Replay rounds in date order; advance bankroll once per terminal round."""
    bankroll = float(initial_bankroll)
    peak = float(initial_bankroll)
    unresolved = 0.0
    maximum_drawdown = 0.0
    series = []
    for document in rounds:
        date = document["round_date"]
        accounting = round_accounting(
            document.get("proposals", []), statuses_for_date(date), stake_of, price_key,
        )
        if accounting["terminal"]:
            bankroll += float(accounting["net"] or 0.0)
            peak = max(peak, bankroll)
            maximum_drawdown = max(maximum_drawdown, (peak - bankroll) / peak if peak > 0 else 0.0)
        else:
            unresolved += float(accounting["exposure"])
        drawdown = (peak - bankroll) / peak if peak > 0 else 0.0
        series.append({
            "round_date": date, "bankroll": round(bankroll, 4),
            "terminal": accounting["terminal"],
            "unresolved_exposure": round(unresolved, 4),
            "drawdown": round(drawdown, 6),
        })
    drawdown = (peak - bankroll) / peak if peak > 0 else 0.0
    return {
        "bankroll": round(bankroll, 4), "peak": round(peak, 4),
        "drawdown": round(drawdown, 6), "maximum_drawdown": round(maximum_drawdown, 6),
        "unresolved_exposure": round(unresolved, 4),
        "available": round(max(0.0, bankroll - unresolved), 4), "series": series,
    }
