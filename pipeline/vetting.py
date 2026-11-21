"""Live vetting checks for the picker.

Each check is a pure function of a Candidate and returns (passed, value text).
C7 is a flag (Mozzart >= fair), never a filter. The live rule is the JSON saved
in pipeline/model/vetting.json; this module only evaluates it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candidate:
    probability: float
    model_probability: float
    league_rate: float
    league_n: int
    home_rate: float
    home_n: int
    away_rate: float
    away_n: int
    fair_odds: float
    counts_probability: float | None = None
    home_form: float | None = None
    away_form: float | None = None
    mozzart_odds: float | None = None
    bookmaker_disagreement: float | None = None
    bookmaker_p80: float | None = None
    xg_for: float | None = None
    xg_against: float | None = None
    league_xg: float | None = None
    bet_direction: str = "result"
    division_matches: int = 999
    days_since_home: int | None = None
    days_since_away: int | None = None
    division_gap: int | None = None


def c1(candidate: Candidate, threshold: float = 0.45) -> tuple[bool, str]:
    return candidate.probability >= threshold, f"{candidate.probability*100:.1f}% >= {threshold*100:.0f}%"


def c2(candidate: Candidate) -> tuple[bool, str]:
    target = candidate.league_rate + 0.05
    return candidate.probability >= target, f"{candidate.probability*100:.1f}% vs usual+5 {target*100:.1f}%"


def c3(candidate: Candidate) -> tuple[bool, str]:
    passed = (
        candidate.home_n >= 8 and candidate.away_n >= 8
        and candidate.home_rate >= candidate.league_rate and candidate.away_rate >= candidate.league_rate
    )
    return passed, (
        f"home {candidate.home_rate*100:.1f}%/{candidate.home_n}, "
        f"away {candidate.away_rate*100:.1f}%/{candidate.away_n}, usual {candidate.league_rate*100:.1f}%"
    )


def c4(candidate: Candidate) -> tuple[bool, str]:
    if candidate.counts_probability is None:
        return False, "no counts estimate"
    gap = abs(candidate.model_probability - candidate.counts_probability)
    return gap <= 0.10, f"gap {gap*100:.1f} points"


def c5(candidate: Candidate) -> tuple[bool, str]:
    if candidate.home_form is None or candidate.away_form is None:
        return False, "no recent form"
    passed = candidate.home_form >= candidate.league_rate and candidate.away_form >= candidate.league_rate
    return passed, f"form {candidate.home_form*100:.1f}%/{candidate.away_form*100:.1f}% vs usual {candidate.league_rate*100:.1f}%"


def c6(candidate: Candidate) -> tuple[bool, str]:
    return candidate.fair_odds >= 1.40, f"fair {candidate.fair_odds:.2f} >= 1.40"


def c7(candidate: Candidate) -> tuple[bool, str]:
    if candidate.mozzart_odds is None:
        return False, "no price"
    return candidate.mozzart_odds >= candidate.fair_odds, (
        f"Mozzart {candidate.mozzart_odds:.2f} vs fair {candidate.fair_odds:.2f}"
    )


def c8(candidate: Candidate) -> tuple[bool, str]:
    if candidate.bookmaker_disagreement is None or candidate.bookmaker_p80 is None:
        return False, "no bookmaker spread"
    return candidate.bookmaker_disagreement <= candidate.bookmaker_p80, (
        f"spread {candidate.bookmaker_disagreement*100:.1f}% (p80 {candidate.bookmaker_p80*100:.1f}%)"
    )


def c9(candidate: Candidate) -> tuple[bool, str]:
    if candidate.xg_for is None or candidate.xg_against is None or candidate.league_xg is None:
        return False, "no xG"
    level = candidate.xg_for + candidate.xg_against
    if candidate.bet_direction == "goals":
        return level >= candidate.league_xg * 2, f"xG {level:.2f} vs league {candidate.league_xg*2:.2f}"
    return True, f"xG {level:.2f}"


def c10(candidate: Candidate) -> tuple[bool, str]:
    return candidate.division_matches >= 8, f"{candidate.division_matches} matches in division"


def c11(candidate: Candidate) -> tuple[bool, str]:
    days = [day for day in (candidate.days_since_home, candidate.days_since_away) if day is not None]
    if not days:
        return False, "no rest data"
    return min(days) >= 3, f"rest {min(days)}d"


def c12(candidate: Candidate) -> tuple[bool, str]:
    if candidate.division_gap is None:
        return False, "no gap data"
    return candidate.division_gap < 10, f"gap {candidate.division_gap}d"


CHECKS = {
    "c1": c1, "c2": c2, "c3": c3, "c4": c4, "c5": c5, "c6": c6,
    "c8": c8, "c9": c9, "c10": c10, "c11": c11, "c12": c12,
}

DEFAULT_RULE: dict = {
    "c1": 0.45, "c2": True, "c3": True, "c4": True, "c5": False, "c6": True,
    "c7": True, "c8": False, "c9": False, "c10": False, "c11": False, "c12": False,
}

# Bet = "Any bet". Kept as a named alias so the two rules read as one definition.
ANY_RULE: dict = DEFAULT_RULE

# Bet = a group or a single market. No absolute probability floor and no minimum
# odds: the bet is judged relative to its own league usual. Fixed thresholds,
# never tuned on results.
TYPE_RULE: dict = {
    "min_lift_multiplier": 1.25,
    "min_lift_points": 0.03,
    "min_record_n": 8,
    "min_agreement": 0.05,
    "agreement_fraction": 0.25,
    "max_fair_odds": 15.0,
}


def lift_of(candidate: Candidate) -> float:
    """Shown probability divided by the league usual for that bet."""
    return candidate.probability / candidate.league_rate if candidate.league_rate > 0 else 0.0


def type_evaluate(candidate: Candidate, rule: dict | None = None) -> tuple[bool, list[dict]]:
    """TYPE_RULE: lift, team records, agreement and a long-shot cap. No C1/C6 floor."""
    rule = rule or TYPE_RULE
    checks: list[dict] = []
    usual = candidate.league_rate
    probability = candidate.probability

    lift = lift_of(candidate)
    lift_passed = (
        usual > 0
        and probability >= usual * float(rule["min_lift_multiplier"])
        and probability >= usual + float(rule["min_lift_points"])
    )
    checks.append({
        "id": "t1", "label": "Lift", "passed": bool(lift_passed),
        "value": f"{probability*100:.1f}% vs usual {usual*100:.1f}% ({lift:.2f}x)",
    })

    min_n = int(rule["min_record_n"])
    records_passed = (
        candidate.home_n >= min_n and candidate.away_n >= min_n
        and candidate.home_rate >= usual and candidate.away_rate >= usual
    )
    checks.append({
        "id": "t3", "label": "Team records", "passed": bool(records_passed),
        "value": f"home {candidate.home_rate*100:.1f}%/{candidate.home_n}, away {candidate.away_rate*100:.1f}%/{candidate.away_n}",
    })

    gap = abs(candidate.model_probability - usual)
    allowed = max(float(rule["min_agreement"]), float(rule["agreement_fraction"]) * probability)
    checks.append({
        "id": "t4", "label": "Agreement", "passed": bool(gap <= allowed),
        "value": f"gap {gap*100:.1f} pts <= {allowed*100:.1f} pts",
    })

    max_fair = float(rule["max_fair_odds"])
    checks.append({
        "id": "t6", "label": "Fair", "passed": bool(candidate.fair_odds <= max_fair),
        "value": f"fair {candidate.fair_odds:.2f} <= {max_fair:.2f}",
    })

    return all(check["passed"] for check in checks), checks


def evaluate(candidate: Candidate, rule: dict | None = None) -> tuple[bool, list[dict]]:
    """All active filters must pass. C7 is appended as a flag, never a filter."""
    rule = rule or DEFAULT_RULE
    checks: list[dict] = []
    for name, func in CHECKS.items():
        config = rule.get(name)
        if name == "c1":
            if config is False:
                continue
            passed, value = func(candidate, float(config if config is not None else 0.45))
        else:
            if not config:
                continue
            passed, value = func(candidate)
        checks.append({"id": name, "passed": bool(passed), "value": value})
    passed_all = all(check["passed"] for check in checks)
    if rule.get("c7"):
        flagged, value = c7(candidate)
        checks.append({"id": "c7", "passed": bool(flagged), "value": value, "flag": True})
    return passed_all, checks


def evaluate_rows(rows: list[dict], rule: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Evaluate candidate dicts; returns (passing, failing), each with check results."""
    passing: list[dict] = []
    failing: list[dict] = []
    for row in rows:
        candidate = row if isinstance(row, Candidate) else Candidate(**row)
        passed, checks = evaluate(candidate, rule)
        entry = {"candidate": candidate, "checks": checks}
        (passing if passed else failing).append(entry)
    return passing, failing
