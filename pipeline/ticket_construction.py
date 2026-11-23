"""ticket-construction-v2: full-menu, banded, visible-fallback tickets.

Production markets only. Every candidate needs an exact actual pre-match price
from the frozen snapshot. The old 58% construction gate is gone. Search is exact
for small pools and a bounded DP for large rounds; the method and approximation
are recorded in the proposal metadata instead of claiming global optimality.
"""
from __future__ import annotations

import itertools
import math

CONSTRUCTION_VERSION = "ticket-construction-v2"
PREFERRED_MIN_INDIVIDUAL = 1.10
EXACT_COMBINATION_CAP = 250_000
DP_LOG_BUCKET = 0.02
DP_KEEP_PER_STATE = 3
MAX_BOUNDED_ODDS = 1000.0
HIDDEN_PREFIX = "CORRECT_SCORE:"

SPECS = {
    "best2": {
        "label": "2 best games", "target": 1.50, "low": 1.35, "high": 1.65,
        "floor": 1.20, "min_legs": 2, "max_legs": 2,
    },
    "around3": {
        "label": "Around 3.00", "target": 3.00, "low": 2.70, "high": 3.30,
        "floor": 2.00, "min_legs": 2, "max_legs": 5,
    },
    "around5": {
        "label": "Around 5.00", "target": 5.00, "low": 4.50, "high": 5.50,
        "floor": 3.00, "min_legs": 2, "max_legs": 5,
    },
}
ORDER = ("best2", "around3", "around5")


def fixture_key(leg: dict) -> tuple:
    return (leg["d"], leg["h"], leg["a"])


def leg_key(leg: dict) -> tuple:
    return (leg["d"], leg["h"], leg["a"], leg["m"])


def candidate_menu(document: dict, snapshot: dict) -> list[dict]:
    """Every priced, unstarted production market on every eligible fixture."""
    by_fixture: dict[tuple, list[dict]] = {}
    for row in document.get("rows", []):
        by_fixture.setdefault((row["d"], row["h"], row["a"]), []).append(row)
    started = {
        (row.get("div"), row.get("home"), row.get("away"))
        for row in snapshot.get("started_not_priced", [])
    }
    menu = []
    for fixture in snapshot.get("fixtures", []):
        key = (fixture.get("div"), fixture.get("home"), fixture.get("away"))
        if key in started or not fixture.get("prices"):
            continue
        for row in by_fixture.get(key, []):
            market = str(row.get("m", ""))
            if market.startswith(HIDDEN_PREFIX):
                continue
            probability = float(row.get("pc", row.get("p", 0.0)))
            if not 0.0 < probability < 1.0:
                continue
            odds = fixture["prices"].get(market)
            if not isinstance(odds, (int, float)) or float(odds) <= 1.0:
                continue
            menu.append({
                "d": row["d"], "h": row["h"], "a": row["a"], "k": row.get("k"),
                "m": market, "pc": probability, "fair": 1.0 / probability,
                "odds": float(odds),
            })
    return sorted(menu, key=lambda leg: (leg["d"], leg["h"], leg["a"], -leg["pc"], leg["odds"], leg["m"]))


def group_by_fixture(menu: list[dict]) -> list[list[dict]]:
    fixtures: dict[tuple, list[dict]] = {}
    for leg in menu:
        fixtures.setdefault(fixture_key(leg), []).append(leg)
    return [
        sorted(fixtures[key], key=lambda leg: (-leg["pc"], leg["odds"], leg["m"]))
        for key in sorted(fixtures)
    ]


def combined(legs: list[dict]) -> tuple[float, float]:
    probability = 1.0
    odds = 1.0
    for leg in legs:
        probability *= float(leg["pc"])
        odds *= float(leg["odds"])
    return probability, odds


def _rank_key(legs: list[dict], target: float) -> tuple:
    probability, odds = combined(legs)
    ev = probability * odds - 1.0
    distance = abs(math.log(odds) - math.log(target))
    identity = tuple(leg_key(leg) for leg in legs)
    return (-probability, -ev, len(legs), distance, identity)


def _estimate(fixtures: list[list[dict]], spec: dict) -> float:
    total = 0.0
    count = len(fixtures)
    for size in range(spec["min_legs"], min(spec["max_legs"], count) + 1):
        average = sum(len(items) for items in fixtures) / max(count, 1)
        total += math.comb(count, size) * (max(average, 1.0) ** size)
    return total


def _enumerate(fixtures: list[list[dict]], spec: dict) -> list[list[dict]]:
    out = []
    for size in range(spec["min_legs"], min(spec["max_legs"], len(fixtures)) + 1):
        for chosen in itertools.combinations(fixtures, size):
            for product in itertools.product(*chosen):
                out.append(list(product))
    return out


def _bounded(fixtures: list[list[dict]], spec: dict) -> list[list[dict]]:
    """Deterministic bounded DP; states are collapsed by 2% log-odds buckets."""
    states: dict[tuple[int, int], list[tuple[tuple, list[dict]]]] = {(0, 0): [((1.0, 1.0), [])]}
    for items in fixtures:
        updates: dict[tuple[int, int], list[tuple[tuple, list[dict]]]] = {}
        for (size, bucket), entries in states.items():
            if size >= spec["max_legs"]:
                continue
            for _summary, legs in entries:
                for leg in items:
                    probability, odds = combined(legs + [leg])
                    if odds > MAX_BOUNDED_ODDS:
                        continue
                    new_bucket = round(math.log(odds) / DP_LOG_BUCKET)
                    updates.setdefault((size + 1, new_bucket), []).append(((probability, odds), legs + [leg]))
        for key, entries in updates.items():
            merged = states.get(key, []) + entries
            merged.sort(key=lambda item: _rank_key(item[1], spec["target"]))
            states[key] = merged[:DP_KEEP_PER_STATE]
    out = []
    for (size, _bucket), entries in states.items():
        if spec["min_legs"] <= size <= spec["max_legs"]:
            out.extend(legs for _summary, legs in entries)
    return out


def search(fixtures: list[list[dict]], spec: dict) -> tuple[list[list[dict]], dict]:
    exact = _estimate(fixtures, spec) <= EXACT_COMBINATION_CAP
    if exact:
        combos = _enumerate(fixtures, spec)
        method = {"method": "exact", "exact": True, "combinations": len(combos)}
    else:
        combos = _bounded(fixtures, spec)
        method = {
            "method": "bounded_dp", "exact": False,
            "log_odds_bucket": DP_LOG_BUCKET, "keep_per_state": DP_KEEP_PER_STATE,
            "note": "Bounded DP collapses states by 2% log-odds buckets; no global maximum-pc optimality claim.",
        }
    return combos, method


def _select_level(combos: list[list[dict]], spec: dict) -> tuple[str, list[list[dict]]]:
    band = [legs for legs in combos if spec["low"] <= combined(legs)[1] <= spec["high"]]
    if band:
        band.sort(key=lambda legs: _rank_key(legs, spec["target"]))
        return "preferred", band
    above = [legs for legs in combos if combined(legs)[1] >= spec["floor"]]
    if above:
        above.sort(key=lambda legs: (
            abs(math.log(combined(legs)[1]) - math.log(spec["target"])),
            *_rank_key(legs, spec["target"]),
        ))
        return "outside", above
    highest = sorted(combos, key=lambda legs: (-combined(legs)[1], *_rank_key(legs, spec["target"])))
    return "below_floor", highest


def _build_one(menu: list[dict], key: str) -> dict:
    spec = SPECS[key]
    all_fixtures = group_by_fixture(menu)
    preferred_menu = [leg for leg in menu if leg["odds"] >= PREFERRED_MIN_INDIVIDUAL]
    preferred_fixtures = group_by_fixture(preferred_menu)
    relaxed = len(preferred_fixtures) < spec["min_legs"]
    fixtures = preferred_fixtures if not relaxed else all_fixtures
    if len(fixtures) < spec["min_legs"]:
        return {
            "type": key, "label": spec["label"], "status": "unavailable",
            "reason": "unavailable — fewer than two distinct priced fixtures",
            "legs": [], "combined_probability": None, "combined_odds": None,
            "construction": {
                "policy": CONSTRUCTION_VERSION, "band": "unavailable",
                "individual_floor_relaxed": False, "overlap_relaxed": False,
            },
        }
    combos, method = search(fixtures, spec)
    level, ranked = _select_level(combos, spec)
    messages = {
        "preferred": "in preferred band",
        "outside": "outside preferred band",
        "below_floor": "below meaningful payout floor; highest available payout",
    }
    best = ranked[0]
    probability, odds = combined(best)
    return {
        "type": key, "label": spec["label"], "status": "available", "reason": "",
        "legs": best,
        "combined_probability": round(probability, 8),
        "combined_odds": round(odds, 6),
        "model_ev": round(probability * odds - 1.0, 6),
        "construction": {
            "policy": CONSTRUCTION_VERSION, "band": level, "band_message": messages[level],
            "achieved_odds": round(odds, 6),
            "individual_floor_relaxed": relaxed,
            "individual_floor_message": "preferred individual-odds floor relaxed" if relaxed else "",
            "overlap_relaxed": False, "overlap_message": "", **method,
        },
        "_ranked": ranked,
    }


def _overlap_ok(candidate: list[dict], chosen: list[list[dict]], strict: bool) -> bool:
    candidate_legs = {leg_key(leg) for leg in candidate}
    candidate_fixtures = {fixture_key(leg) for leg in candidate}
    if strict:
        if any(candidate_legs == {leg_key(leg) for leg in ticket} for ticket in chosen):
            return False
        used_fixtures = [fixture_key(leg) for ticket in chosen for leg in ticket]
        if any(key in used_fixtures for key in candidate_fixtures):
            return False
        all_three = chosen + [candidate]
        if len(all_three) == 3:
            common = set.intersection(*[{fixture_key(leg) for leg in ticket} for ticket in all_three])
            if common:
                return False
        return True
    # Relaxed: allow fixtures to repeat, but still avoid an exact duplicate and
    # keep any pair to at most one shared leg when possible.
    seen = [set(leg_key(leg) for leg in ticket) for ticket in chosen]
    if any(candidate_legs == ticket for ticket in seen):
        return False
    if len(candidate) > 0 and any(len(candidate_legs & ticket) > 1 for ticket in seen):
        return False
    return True


def construct(menu: list[dict]) -> list[dict]:
    """Build the three proposals in order with explicit overlap relaxation."""
    built = [_build_one(menu, key) for key in ORDER]
    chosen: list[list[dict]] = []
    selected = []
    for proposal in built:
        ranked = proposal.pop("_ranked", [])
        if proposal["status"] != "available":
            selected.append(proposal)
            continue
        picked = next((legs for legs in ranked if _overlap_ok(legs, chosen, True)), None)
        relaxed = False
        if picked is None:
            picked = next((legs for legs in ranked if _overlap_ok(legs, chosen, False)), None)
            relaxed = True
        if picked is None:
            picked = ranked[0]
            relaxed = True
        chosen.append(picked)
        probability, odds = combined(picked)
        proposal["legs"] = picked
        proposal["combined_probability"] = round(probability, 8)
        proposal["combined_odds"] = round(odds, 6)
        proposal["model_ev"] = round(probability * odds - 1.0, 6)
        proposal["construction"]["achieved_odds"] = round(odds, 6)
        proposal["construction"]["overlap_relaxed"] = relaxed
        proposal["construction"]["overlap_message"] = "cross-ticket overlap relaxation" if relaxed else ""
        selected.append(proposal)
    return selected
