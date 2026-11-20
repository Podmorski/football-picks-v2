"""Target-payout ticket optimiser.

Choose at most max_legs legs, one per match, with the highest combined
probability whose combined fair odds are at least target. Because log(p) =
-log(fair), this is the subset with the smallest sum of log(fair) that is at
least log(target).

Method: exact enumeration for pools up to 20 legs; above that an exact DP over
0.001-quantised log(fair), with the true fair odds checked before a candidate is
accepted. Ties by fair are broken by the first subset found.
"""
from __future__ import annotations

import itertools
import math

ENUMERATE_LIMIT = 20
STEP = 0.001


def _combined(legs: list[dict]) -> tuple[float, float]:
    probability = 1.0
    fair = 1.0
    for leg in legs:
        probability *= float(leg["pc"])
        fair *= float(leg["fair"])
    return probability, fair


def _dedupe(legs: list[dict], min_fair: float) -> list[dict]:
    by_match: dict[tuple, dict] = {}
    for leg in legs:
        if float(leg.get("fair", 0.0)) < min_fair:
            continue
        key = (leg.get("h"), leg.get("a"))
        current = by_match.get(key)
        if current is None or float(leg["pc"]) > float(current["pc"]):
            by_match[key] = leg
    return list(by_match.values())


def _enumerate(pool: list[dict], target: float, max_legs: int, alternatives: int) -> list[dict]:
    found: list[tuple[float, list[dict]]] = []
    for size in range(1, max_legs + 1):
        for combo in itertools.combinations(pool, size):
            _probability, fair = _combined(combo)
            if fair >= target:
                found.append((fair, list(combo)))
    found.sort(key=lambda item: item[0])
    out: list[dict] = []
    seen: set[tuple] = set()
    for fair, combo in found:
        key = tuple(sorted(id(leg) for leg in combo))
        if key in seen:
            continue
        seen.add(key)
        out.append({"legs": combo, "probability": 1.0 / fair, "fair": fair})
        if len(out) >= alternatives:
            break
    return out


def _reconstruct(reachable: list[dict], size: int, weight: int, pool: list[dict]) -> list[dict] | None:
    combo: list[dict] = []
    k = size
    w = weight
    while k > 0:
        previous = reachable[k].get(w)
        if previous is None:
            return None
        index, prev_weight = previous
        combo.append(pool[index])
        w = prev_weight
        k -= 1
    return combo


def _dp(pool: list[dict], target: float, max_legs: int, alternatives: int) -> list[dict]:
    weights = [max(1, math.ceil(math.log(max(float(leg["fair"]), 1.0)) / STEP)) for leg in pool]
    max_weight = max_legs * max(weights) if weights else 0
    reachable: list[dict] = [dict() for _ in range(max_legs + 1)]
    reachable[0][0] = None
    for index, weight in enumerate(weights):
        for size in range(max_legs, 0, -1):
            previous = reachable[size - 1]
            current = reachable[size]
            for prev_weight in list(previous.keys()):
                new_weight = prev_weight + weight
                if new_weight > max_weight:
                    continue
                if new_weight not in current:
                    current[new_weight] = (index, prev_weight)
    target_weight = math.ceil(math.log(target) / STEP)
    candidates: list[tuple[float, list[dict]]] = []
    for size in range(1, max_legs + 1):
        for weight in sorted(value for value in reachable[size] if value >= target_weight):
            combo = _reconstruct(reachable, size, weight, pool)
            if combo is None:
                continue
            _probability, fair = _combined(combo)
            if fair >= target:
                candidates.append((fair, combo))
    candidates.sort(key=lambda item: item[0])
    out: list[dict] = []
    seen: set[tuple] = set()
    for fair, combo in candidates:
        key = tuple(sorted(id(leg) for leg in combo))
        if key in seen:
            continue
        seen.add(key)
        out.append({"legs": combo, "probability": 1.0 / fair, "fair": fair})
        if len(out) >= alternatives:
            break
    return out


def optimise(legs: list[dict], target: float, max_legs: int, alternatives: int = 3, min_fair: float = 1.50) -> list[dict]:
    """Top tickets meeting the target, highest combined probability first."""
    pool = _dedupe(legs, min_fair)
    if len(pool) <= ENUMERATE_LIMIT:
        return _enumerate(pool, target, max_legs, alternatives)
    return _dp(pool, target, max_legs, alternatives)


def optimise_many(
    legs: list[dict], targets, max_legs_list, min_fair: float = 1.50, step: float = 0.02,
) -> dict:
    """Best ticket for every (target, max_legs) from one reachable DP.

    Used by the per-date backtest, where running the DP once per date is far
    cheaper than once per target. Small pools use exact enumeration.
    """
    pool = _dedupe(legs, min_fair)
    results: dict[tuple[float, int], dict | None] = {}
    if len(pool) <= ENUMERATE_LIMIT:
        for target in targets:
            for max_legs in max_legs_list:
                tickets = _enumerate(pool, target, max_legs, 1)
                results[(target, max_legs)] = tickets[0] if tickets else None
        return results

    weights = [max(1, math.ceil(math.log(max(float(leg["fair"]), 1.0)) / step)) for leg in pool]
    top = max(max_legs_list)
    max_weight = top * max(weights) if weights else 0
    reachable: list[dict] = [dict() for _ in range(top + 1)]
    reachable[0][0] = None
    for index, weight in enumerate(weights):
        for size in range(top, 0, -1):
            previous = reachable[size - 1]
            current = reachable[size]
            for prev_weight in list(previous.keys()):
                new_weight = prev_weight + weight
                if new_weight > max_weight:
                    continue
                if new_weight not in current:
                    current[new_weight] = (index, prev_weight)

    for target in targets:
        target_weight = math.ceil(math.log(target) / step)
        for max_legs in max_legs_list:
            best = None
            for size in range(1, max_legs + 1):
                for weight in sorted(value for value in reachable[size] if value >= target_weight):
                    combo = _reconstruct(reachable, size, weight, pool)
                    if combo is None:
                        continue
                    _probability, fair = _combined(combo)
                    if fair >= target:
                        if best is None or fair < best["fair"]:
                            best = {"legs": combo, "probability": 1.0 / fair, "fair": fair}
                        break
            results[(target, max_legs)] = best
    return results
