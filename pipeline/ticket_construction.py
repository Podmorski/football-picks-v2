"""ticket-construction-v3: full-menu, visible-fallback automatic tickets.

Production markets only. Every candidate needs an exact actual pre-match price
from the frozen snapshot. The 58% construction gate is gone. Search is exact
for small pools and a bounded DP for large rounds; the method and approximation
are recorded in the proposal metadata instead of claiming global optimality.

v3 specs: High-probability (2-3 legs, no odds target), Around 3.00 (1-3 legs,
2.70-3.30), and 5-10 combo (3-5 legs, 5.00-10.00). Individual prices relax in
three visible tiers: >=1.20, >=1.10, then any price above 1.00.
"""
from __future__ import annotations

import itertools
import math

CONSTRUCTION_VERSION = "ticket-construction-v2"
CONSTRUCTION_VERSION_V3 = "ticket-construction-v3"
PREFERRED_MIN_INDIVIDUAL = 1.20
MID_MIN_INDIVIDUAL = 1.10
EXACT_COMBINATION_CAP = 250_000
DP_LOG_BUCKET = 0.02
DP_KEEP_PER_STATE = 3
MAX_BOUNDED_ODDS = 1000.0
HIDDEN_PREFIX = "CORRECT_SCORE:"

PRICE_TIERS = (
    ("preferred", PREFERRED_MIN_INDIVIDUAL,
     "preferred individual odds (every leg at least 1.20)"),
    ("relaxed_1_10", MID_MIN_INDIVIDUAL,
     "preferred individual-odds floor relaxed to 1.10"),
    ("relaxed_below_1_10", 1.0,
     "individual-odds preference relaxed below 1.10; lowest available prices used"),
)
PRICE_TIER_MESSAGE = {name: message for name, _minimum, message in PRICE_TIERS}

SPECS = {
    "best2": {
        "label": "High-probability", "target": None, "low": None, "high": None,
        "floor": None, "min_legs": 2, "max_legs": 3, "rank_distance": False,
        "required_fixtures": 2,
        "unavailable": "unavailable — fewer than two distinct eligible priced fixtures",
    },
    "around3": {
        "label": "Around 3.00", "target": 3.00, "low": 2.70, "high": 3.30,
        "floor": 2.00, "min_legs": 1, "max_legs": 3, "rank_distance": True,
        "required_fixtures": 1,
        "unavailable": "unavailable — no eligible priced fixture",
    },
    "around5": {
        "label": "5–10 combo", "target": 7.00, "low": 5.00, "high": 10.00,
        "floor": 3.00, "min_legs": 3, "max_legs": 5, "rank_distance": False,
        "required_fixtures": 3,
        "unavailable": "unavailable — fewer than three distinct eligible priced fixtures",
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


def _identity(legs: list[dict]) -> tuple:
    return tuple(leg_key(leg) for leg in legs)


def _rank_key(legs: list[dict], spec: dict) -> tuple:
    probability, odds = combined(legs)
    ev = probability * odds - 1.0
    keys = [-probability, -ev, len(legs)]
    if spec.get("rank_distance"):
        keys.append(abs(math.log(odds) - math.log(spec["target"])))
    keys.append(_identity(legs))
    return tuple(keys)


def _band_distance(odds: float, spec: dict) -> float:
    if spec.get("low") is None:
        return 0.0
    if odds < spec["low"]:
        return abs(math.log(odds) - math.log(spec["low"]))
    if spec.get("high") is not None and odds > spec["high"]:
        return abs(math.log(odds) - math.log(spec["high"]))
    return 0.0


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
            merged.sort(key=lambda item: _rank_key(item[1], spec))
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
    if spec.get("low") is None:
        ranked = sorted(combos, key=lambda legs: _rank_key(legs, spec))
        return "no_band", ranked
    band = [legs for legs in combos if spec["low"] <= combined(legs)[1] <= spec["high"]]
    if band:
        band.sort(key=lambda legs: _rank_key(legs, spec))
        return "preferred", band
    above = [legs for legs in combos if combined(legs)[1] >= spec["floor"]]
    if above:
        above.sort(key=lambda legs: (
            _band_distance(combined(legs)[1], spec),
            -combined(legs)[0],
            -(combined(legs)[0] * combined(legs)[1] - 1.0),
            len(legs),
            _identity(legs),
        ))
        return "outside", above
    highest = sorted(
        combos,
        key=lambda legs: (-combined(legs)[1], -combined(legs)[0], _identity(legs)),
    )
    return "below_floor", highest


def _choose_tier(menu: list[dict], min_legs: int) -> tuple[str, int, list[list[dict]]]:
    """Relax individual prices only as far as needed to reach min_legs fixtures."""
    for name, minimum, _message in PRICE_TIERS:
        filtered = [leg for leg in menu if leg["odds"] >= minimum] if minimum > 1.0 else list(menu)
        fixtures = group_by_fixture(filtered)
        if len(fixtures) >= min_legs:
            return name, minimum, fixtures
    return "relaxed_below_1_10", 1.0, group_by_fixture(menu)


def _build_one(menu: list[dict], key: str) -> dict:
    spec = SPECS[key]
    tier, individual_min, fixtures = _choose_tier(menu, spec["min_legs"])
    if len(fixtures) < spec["required_fixtures"]:
        return {
            "type": key, "label": spec["label"], "status": "unavailable",
            "reason": spec["unavailable"],
            "legs": [], "combined_probability": None, "combined_odds": None,
            "construction": {
                "policy": CONSTRUCTION_VERSION_V3, "band": "unavailable",
                "band_message": "unavailable",
                "band_low": spec["low"], "band_high": spec["high"], "floor": spec["floor"],
                "individual_price_tier": tier,
                "individual_price_min": individual_min,
                "individual_floor_relaxed": tier != "preferred",
                "individual_floor_message": "" if tier == "preferred" else PRICE_TIER_MESSAGE[tier],
                "overlap_relaxed": False, "overlap_message": "", "overlap_level": "none",
            },
        }
    combos, method = search(fixtures, spec)
    level, ranked = _select_level(combos, spec)
    messages = {
        "preferred": "in preferred band",
        "outside": "outside preferred band",
        "below_floor": "below meaningful payout floor; highest available payout",
        "no_band": "no combined-odds target",
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
            "policy": CONSTRUCTION_VERSION_V3, "band": level, "band_message": messages[level],
            "band_low": spec["low"], "band_high": spec["high"], "floor": spec["floor"],
            "achieved_odds": round(odds, 6),
            "individual_price_tier": tier,
            "individual_price_min": individual_min,
            "individual_floor_relaxed": tier != "preferred",
            "individual_floor_message": "" if tier == "preferred" else PRICE_TIER_MESSAGE[tier],
            "overlap_relaxed": False, "overlap_message": "", "overlap_level": "none", **method,
        },
        "_ranked": ranked,
    }


def _fixture_markets(ticket: list[dict]) -> dict[tuple, tuple]:
    return {fixture_key(leg): leg_key(leg) for leg in ticket}


def _overlap_level(candidate: list[dict], chosen: list[list[dict]]) -> int | None:
    """0 = no fixture reused; 1 = only exact shared legs; 2 = other overlap; None = exact duplicate."""
    candidate_legs = {leg_key(leg) for leg in candidate}
    candidate_fixtures = {fixture_key(leg) for leg in candidate}
    used_fixtures = {fixture_key(leg) for ticket in chosen for leg in ticket}
    if candidate_fixtures.isdisjoint(used_fixtures):
        return 0
    if any(candidate_legs == {leg_key(leg) for leg in ticket} for ticket in chosen):
        return None
    level_one_ok = True
    for ticket in chosen:
        ticket_legs = {leg_key(leg) for leg in ticket}
        if len(candidate_legs & ticket_legs) > 1:
            level_one_ok = False
        for fixture, market in _fixture_markets(candidate).items():
            other = _fixture_markets(ticket).get(fixture)
            if other is not None and other != market:
                level_one_ok = False
    if len(chosen) == 2:
        common = (
            candidate_fixtures
            & {fixture_key(leg) for leg in chosen[0]}
            & {fixture_key(leg) for leg in chosen[1]}
        )
        if common:
            level_one_ok = False
    return 1 if level_one_ok else 2


def _pick_with_overlap(ranked: list[list[dict]], chosen: list[list[dict]]) -> tuple[list[dict], int]:
    for max_level in (0, 1, 2):
        for legs in ranked:
            level = _overlap_level(legs, chosen)
            if level is not None and level <= max_level:
                return legs, level
    return ranked[0], 2


def construct_v3(menu: list[dict]) -> list[dict]:
    """Build the three v3 proposals in order with explicit overlap relaxation."""
    built = [_build_one(menu, key) for key in ORDER]
    chosen: list[list[dict]] = []
    selected = []
    for proposal in built:
        ranked = proposal.pop("_ranked", [])
        if proposal["status"] != "available":
            selected.append(proposal)
            continue
        picked, level = _pick_with_overlap(ranked, chosen)
        chosen.append(picked)
        probability, odds = combined(picked)
        proposal["legs"] = picked
        proposal["combined_probability"] = round(probability, 8)
        proposal["combined_odds"] = round(odds, 6)
        proposal["model_ev"] = round(probability * odds - 1.0, 6)
        proposal["construction"]["achieved_odds"] = round(odds, 6)
        proposal["construction"]["overlap_relaxed"] = level > 0
        proposal["construction"]["overlap_message"] = "cross-ticket overlap relaxation" if level > 0 else ""
        proposal["construction"]["overlap_level"] = "none" if level == 0 else "shared_leg" if level == 1 else "relaxed"
        selected.append(proposal)
    return selected


# ---------------------------------------------------------------------------
# Frozen ticket-construction-v2 (legacy). Published-pick reconstructions call
# `construct` and must keep producing byte-identical v2 metadata. New automatic
# proposals use `construct_v3` above.
# ---------------------------------------------------------------------------

V2_PREFERRED_MIN_INDIVIDUAL = 1.10
V2_SPECS = {
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
V2_ORDER = ("best2", "around3", "around5")


def _v2_rank_key(legs: list[dict], target: float) -> tuple:
    probability, odds = combined(legs)
    ev = probability * odds - 1.0
    distance = abs(math.log(odds) - math.log(target))
    return (-probability, -ev, len(legs), distance, _identity(legs))


def _v2_estimate(fixtures: list[list[dict]], spec: dict) -> float:
    total = 0.0
    count = len(fixtures)
    for size in range(spec["min_legs"], min(spec["max_legs"], count) + 1):
        average = sum(len(items) for items in fixtures) / max(count, 1)
        total += math.comb(count, size) * (max(average, 1.0) ** size)
    return total


def _v2_enumerate(fixtures: list[list[dict]], spec: dict) -> list[list[dict]]:
    out = []
    for size in range(spec["min_legs"], min(spec["max_legs"], len(fixtures)) + 1):
        for chosen in itertools.combinations(fixtures, size):
            for product in itertools.product(*chosen):
                out.append(list(product))
    return out


def _v2_bounded(fixtures: list[list[dict]], spec: dict) -> list[list[dict]]:
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
            merged.sort(key=lambda item: _v2_rank_key(item[1], spec["target"]))
            states[key] = merged[:DP_KEEP_PER_STATE]
    out = []
    for (size, _bucket), entries in states.items():
        if spec["min_legs"] <= size <= spec["max_legs"]:
            out.extend(legs for _summary, legs in entries)
    return out


def _v2_search(fixtures: list[list[dict]], spec: dict) -> tuple[list[list[dict]], dict]:
    exact = _v2_estimate(fixtures, spec) <= EXACT_COMBINATION_CAP
    if exact:
        combos = _v2_enumerate(fixtures, spec)
        method = {"method": "exact", "exact": True, "combinations": len(combos)}
    else:
        combos = _v2_bounded(fixtures, spec)
        method = {
            "method": "bounded_dp", "exact": False,
            "log_odds_bucket": DP_LOG_BUCKET, "keep_per_state": DP_KEEP_PER_STATE,
            "note": "Bounded DP collapses states by 2% log-odds buckets; no global maximum-pc optimality claim.",
        }
    return combos, method


def _v2_select_level(combos: list[list[dict]], spec: dict) -> tuple[str, list[list[dict]]]:
    band = [legs for legs in combos if spec["low"] <= combined(legs)[1] <= spec["high"]]
    if band:
        band.sort(key=lambda legs: _v2_rank_key(legs, spec["target"]))
        return "preferred", band
    above = [legs for legs in combos if combined(legs)[1] >= spec["floor"]]
    if above:
        above.sort(key=lambda legs: (
            abs(math.log(combined(legs)[1]) - math.log(spec["target"])),
            *_v2_rank_key(legs, spec["target"]),
        ))
        return "outside", above
    highest = sorted(combos, key=lambda legs: (-combined(legs)[1], *_v2_rank_key(legs, spec["target"])))
    return "below_floor", highest


def _v2_build_one(menu: list[dict], key: str) -> dict:
    spec = V2_SPECS[key]
    all_fixtures = group_by_fixture(menu)
    preferred_menu = [leg for leg in menu if leg["odds"] >= V2_PREFERRED_MIN_INDIVIDUAL]
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
    combos, method = _v2_search(fixtures, spec)
    level, ranked = _v2_select_level(combos, spec)
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


def _v2_overlap_ok(candidate: list[dict], chosen: list[list[dict]], strict: bool) -> bool:
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
    seen = [set(leg_key(leg) for leg in ticket) for ticket in chosen]
    if any(candidate_legs == ticket for ticket in seen):
        return False
    if len(candidate) > 0 and any(len(candidate_legs & ticket) > 1 for ticket in seen):
        return False
    return True


def construct(menu: list[dict]) -> list[dict]:
    """Frozen ticket-construction-v2 used by published-pick reconstructions."""
    built = [_v2_build_one(menu, key) for key in V2_ORDER]
    chosen: list[list[dict]] = []
    selected = []
    for proposal in built:
        ranked = proposal.pop("_ranked", [])
        if proposal["status"] != "available":
            selected.append(proposal)
            continue
        picked = next((legs for legs in ranked if _v2_overlap_ok(legs, chosen, True)), None)
        relaxed = False
        if picked is None:
            picked = next((legs for legs in ranked if _v2_overlap_ok(legs, chosen, False)), None)
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


def unsupported_same_fixture_dependence(proposals: list[dict]) -> bool:
    """True when two proposals use different markets from the same fixture."""
    available = [proposal for proposal in proposals if proposal.get("status") == "available"]
    markets = [_fixture_markets(proposal.get("legs", [])) for proposal in available]
    for left in range(len(markets)):
        for right in range(left + 1, len(markets)):
            for fixture, market in markets[left].items():
                other = markets[right].get(fixture)
                if other is not None and other != market:
                    return True
    return False
