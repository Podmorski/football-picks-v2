"""Map a Mozzart (section, period, code) onto one v2 catalogue market id.

The rules are a direct port of the v1 (football-edge-finder) resolver, rewritten
to emit v2 ids instead of v1 family/code pairs. The section decides what a code
means, so the rules key on (rawName, period). Anything not matched is
UNMAPPED and simply absent -- never guessed.

Only the markets that can be settled from (HT, FT) scores are mapped, which is
exactly the v2 catalogue. Prefix families in v1 (HT, AT, CS, R, DCG, HFG, C) are
expanded here into the equivalent v2 family + code.
"""
from __future__ import annotations

from ..markets import MARKETS

FULL_TIME = "FULL_TIME"
FIRST_HALF = "FIRST_HALF"
SECOND_HALF = "SECOND_HALF"


def _norm(code: str) -> str:
    """Codes are compared ignoring spacing and case: 'I1 0' == 'i10'."""
    return str(code).replace(" ", "").upper()


_INDEX: dict[tuple[str, str], str] = {(market.family, _norm(market.code)): market.id for market in MARKETS}
VALID_IDS = frozenset(market.id for market in MARKETS)


def _identity(code: str) -> str:
    return code


def _mapping(table: dict[str, str]):
    return lambda code: table.get(code, code)


def _prefix(prefix: str):
    return lambda code: f"{prefix} {code}"


def _half_range(prefix: str):
    table = {
        "0": f"{prefix}0", "1": f"{prefix}1", "2": f"{prefix}2", "3": f"{prefix}3",
        "1+": f"{prefix}1+", "2+": f"{prefix}2+", "3+": f"{prefix}3+",
        "0-1": f"{prefix}0-1", "0-2": f"{prefix}0-2", "1-2": f"{prefix}1-2", "2-3": f"{prefix}2-3",
    }
    return _mapping(table)


# key = (rawName, period) -> (v2 family, code transform)
RULES: dict[tuple[str, str], tuple[str, object]] = {
    # --- full-time result / goals -----------------------------------------
    ("Konačan ishod", FULL_TIME): ("RESULT", _identity),
    ("Dupla šansa", FULL_TIME): ("DOUBLE_CHANCE", _identity),
    ("Ukupno golova na meču", FULL_TIME): ("GOAL_RANGE_FT", _identity),
    ("Tačan broj golova na meču", FULL_TIME): ("GOAL_RANGE_FT", _identity),
    ("Poluvreme - Kraj", FULL_TIME): ("HTFT", _identity),
    ("Poluvreme- Kraj / Dupla šansa", FULL_TIME): ("HTFT_DC", _identity),
    ("Poluvreme - Kraj kombinazzije", FULL_TIME): ("HTFT_COMBO", _identity),
    ("Poluvreme sa više golova", FULL_TIME): ("MORE_GOALS_HALF", _mapping(
        {"prvo": "I>II", "jednako": "I=II", "drugo": "I<II"})),

    # --- halves ------------------------------------------------------------
    ("Prvo poluvreme", FIRST_HALF): ("HALF_RESULT", _mapping({"1": "I1", "X": "IX", "2": "I2"})),
    ("Drugo poluvreme", SECOND_HALF): ("SECOND_HALF_RESULT", _mapping({"1": "II1", "X": "IIX", "2": "II2"})),
    ("Dupla šansa prvo poluvreme", FIRST_HALF): ("HALF_DC", _mapping({"1X": "I1X", "12": "I12", "X2": "IX2"})),
    ("Ukupno golova prvo poluvreme", FIRST_HALF): ("GOAL_RANGE_1H", _half_range("I")),
    ("Ukupno golova drugo poluvreme", SECOND_HALF): ("GOAL_RANGE_2H", _half_range("II")),

    # --- both teams to score ----------------------------------------------
    ("Oba tima daju gol", FULL_TIME): ("BTTS", _identity),
    ("Oba tima daju gol", FIRST_HALF): ("BTTS_1H", _mapping({"GG": "IGG", "NG": "ING"})),
    ("Oba tima daju gol", SECOND_HALF): ("BTTS_2H", _mapping({"GG": "IIGG", "NG": "IING"})),

    # --- parity / specials -------------------------------------------------
    ("Ukupno golova - Par/Nepar", FULL_TIME): ("PARITY", _mapping({"PAR": "PAR", "NEPAR": "NEPAR"})),
    ("Dupla pobeda", FULL_TIME): ("WIN_BOTH_HALVES", _mapping({"DP1": "DP 1", "DP2": "DP 2"})),
    ("Sigurna pobeda", FULL_TIME): ("WIN_TO_NIL", _mapping({"SP1": "SP 1", "SP2": "SP 2"})),
    ("Hendikep pobeda", FULL_TIME): ("MARGIN", _mapping({"1": "HP 1", "2": "HP 2"})),

    # --- team goals --------------------------------------------------------
    ("Tim 1 daje gol", FULL_TIME): ("TEAM_GOALS", _prefix("I1")),
    ("Tim 2 daje gol", FULL_TIME): ("TEAM_GOALS", _prefix("I2")),
    ("Tim 1 golovi prvo poluvreme", FIRST_HALF): ("TEAM_GOALS_HALF", _prefix("I1")),
    ("Tim 2 golovi prvo poluvreme", FIRST_HALF): ("TEAM_GOALS_HALF", _prefix("I2")),
    ("Tim 1 golovi drugo poluvreme", SECOND_HALF): ("TEAM_GOALS_HALF", _prefix("II1")),
    ("Tim 2 golovi drugo poluvreme", SECOND_HALF): ("TEAM_GOALS_HALF", _prefix("II2")),

    # --- combined markets --------------------------------------------------
    ("Tačan rezultat", FULL_TIME): ("CORRECT_SCORE", _identity),
    ("Konačan ishod + Golovi", FULL_TIME): ("RESULT_AND_GOALS", _identity),
    ("Dupla šansa + Golovi", FULL_TIME): ("DC_AND_GOALS", _identity),
    ("Poluvreme - Kraj + Golovi", FULL_TIME): ("HTFT_AND_GOALS", _identity),
    ("Broj golova u prvom i drugom poluvremenu", SECOND_HALF): ("HALF_GOAL_COMBOS", _identity),
}


def resolve(section: str, period: str, code: str) -> str | None:
    """The v2 market id for this Mozzart selection, or None when UNMAPPED."""
    rule = RULES.get((section, period))
    if rule is None:
        return None
    family, transform = rule
    target = transform(code)  # type: ignore[operator]
    return _INDEX.get((family, _norm(target)))


def coverage(rows: list[dict]) -> dict[str, int]:
    """How many v2 markets per family at least one selection maps to.

    rows are dicts with section/period/code. Used by tests and the
    match-rate report; it is a union over all rows.
    """
    from collections import Counter

    total = Counter(market.family for market in MARKETS)
    hit: Counter[str] = Counter()
    seen: set[str] = set()
    for row in rows:
        market_id = resolve(row["section"], row["period"], row["code"])
        if market_id and market_id not in seen:
            seen.add(market_id)
            hit[market_id.split(":", 1)[0]] += 1
    return {family: hit.get(family, 0) for family in sorted(total)}
