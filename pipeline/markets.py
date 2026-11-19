"""Mozzart market catalogue that can be settled from half-time and full-time scores.

Every market is a predicate over ``(fthg, ftag, hthg, htag)``, so the same rule
settles a real result and prices one cell of the model's half-score grid. Families
and codes follow Mozzart's own sections (see pipeline/mozzart_markets.yaml, which is
generated from this module) and the Soccer Bet catalogue it shares codes with.

Markets that need events we do not have (first goal, cards, corners, shots, player
goals, 15/30-minute windows, qualification) are listed in NOT_SETTLABLE with the
reason; they are never invented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

Predicate = Callable[[int, int, int, int], bool]


def result(goals_for: int, goals_against: int) -> str:
    if goals_for > goals_against:
        return "1"
    if goals_for < goals_against:
        return "2"
    return "X"


def _range(code: str) -> Callable[[int], bool]:
    """'2+' -> >= 2, '0-2' -> 0..2, '3' -> == 3, '1-2' -> 1..2."""
    if code.endswith("+"):
        threshold = int(code[:-1])
        return lambda value: value >= threshold
    if "-" in code:
        low, high = code.split("-", 1)
        return lambda value: int(low) <= value <= int(high)
    target = int(code)
    return lambda value: value == target


@dataclass(frozen=True, slots=True)
class Market:
    id: str
    family: str
    code: str
    mozzart_label: str
    plain: str
    group: str
    settle: Predicate
    needs_ht: bool = True


GROUPS = (
    "Result & double chance",
    "HT/FT",
    "Goals",
    "BTTS",
    "Half-time",
    "Team goals",
    "Correct score",
    "Combos",
)

# Families Mozzart publishes that cannot be settled from (HT, FT) scores.
NOT_SETTLABLE = (
    ("Daje prvi gol", "needs the identity of the first scorer — not derivable from goals per half"),
    ("Daje prvi gol - Kraj", "first goal combined with the result; the first-goal half is not the same as the score at half-time"),
    ("Prvi gol na meču - *", "how the first goal was scored (header, penalty, free kick, own goal)"),
    ("Prvi događaj na meču - *", "first event (corner, foul, offside, throw-in) needs event data"),
    ("Mozzart šansa", "proprietary combined offer with an unpublished formula"),
    ("Broj golova <player>", "player-level goals"),
    ("<player> daje gol i <team> pobeđuje", "player-level goals"),
    ("Broj žutih kartona / kornera / šuteva", "cards, corners and shots per team or match"),
    ("Oba tima po N+ kartona/kornera/šuteva", "cards, corners and shots"),
    ("UG 1-15 MIN / UG 1-30 MIN / KI 1-15 MIN / KI 1-30 MIN", "goal and card windows inside the half"),
    ("Penal na meču / Penal u prvom poluvremenu / Promašen penal", "penalty events"),
    ("Crveni karton / Oba tima dobijaju crveni karton / Autogol", "card and own-goal events"),
    ("Gol glavom / Gol direktno iz slobodnog udarca / Het-trik", "how goals were scored"),
    ("PD 1 / PD 2 (to qualify)", "aggregate qualification, not a single match score"),
)


def _goal_words(code: str) -> str:
    """'1' -> '1 goal', '2' -> '2 goals', '2+' -> '2+ goals', '0-2' -> '0-2 goals'."""
    unit = code in ("1",)
    return f"{code} goal" if unit else f"{code} goals"


HT_WORDS = {
    "1": "Home team ahead",
    "X": "Level",
    "2": "Away team ahead",
}
FT_WORDS = {
    "1": "home win",
    "X": "draw",
    "2": "away win",
}


def _build() -> list[Market]:
    markets: list[Market] = []

    def add(family, code, label, plain, group, fn, needs_ht=True):
        markets.append(Market(f"{family}:{code}", family, code, label, plain, group, fn, needs_ht))

    # --- result and double chance -------------------------------------------
    for code, plain in (("1", "Home win"), ("X", "Draw"), ("2", "Away win")):
        add("RESULT", code, code, plain, "Result & double chance",
            lambda f, a, h1, a1, c=code: result(f, a) == c, needs_ht=False)
    for code, plain in (("1X", "Home win or draw"), ("12", "Home or away win"), ("X2", "Draw or away win")):
        add("DOUBLE_CHANCE", code, code, plain, "Result & double chance",
            lambda f, a, h1, a1, c=code: result(f, a) in set(c), needs_ht=False)

    # --- half-time ----------------------------------------------------------
    for code, label, plain in (("I1", "1", "Home leads at half-time"), ("IX", "X", "Level at half-time"),
                               ("I2", "2", "Away leads at half-time")):
        add("HALF_RESULT", code, label, plain, "Half-time",
            lambda f, a, h1, a1, c=code[1]: result(h1, a1) == c)
    for code, label, plain in (("II1", "1", "Home leads the second half"), ("IIX", "X", "Second half level"),
                               ("II2", "2", "Away leads the second half")):
        add("SECOND_HALF_RESULT", code, label, plain, "Half-time",
            lambda f, a, h1, a1, c=code[2]: result(f - h1, a - a1) == c)
    for code, plain in (("I1X", "Home or level at half-time"), ("I12", "No draw at half-time"),
                        ("IX2", "Level or away ahead at half-time")):
        add("HALF_DC", code, code.replace("I", ""), plain, "Half-time",
            lambda f, a, h1, a1, c=code[1:]: result(h1, a1) in set(c))
    for code, plain in (("II1X", "Home or level in the second half"), ("II12", "No draw in the second half"),
                        ("IIX2", "Level or away ahead in the second half")):
        add("SECOND_HALF_DC", code, code.replace("II", ""), plain, "Half-time",
            lambda f, a, h1, a1, c=code[2:]: result(f - h1, a - a1) in set(c))

    # --- BTTS and parity -----------------------------------------------------
    btts = lambda f, a, h1, a1: f >= 1 and a >= 1
    for family, label, plain, fn, ht in (
        ("BTTS", "GG", "Both teams score", btts, False),
        ("BTTS", "NG", "At least one team fails to score", lambda f, a, h1, a1: not btts(f, a, h1, a1), False),
        ("BTTS_1H", "IGG", "Both teams score in the first half", lambda f, a, h1, a1: h1 >= 1 and a1 >= 1, True),
        ("BTTS_1H", "ING", "At least one team fails to score in the first half", lambda f, a, h1, a1: not (h1 >= 1 and a1 >= 1), True),
        ("BTTS_2H", "IIGG", "Both teams score in the second half", lambda f, a, h1, a1: f - h1 >= 1 and a - a1 >= 1, True),
        ("BTTS_2H", "IING", "At least one team fails to score in the second half", lambda f, a, h1, a1: not (f - h1 >= 1 and a - a1 >= 1), True),
    ):
        add(family, label, label, plain, "BTTS", fn, needs_ht=ht)
    add("PARITY", "PAR", "PAR", "Even number of goals", "Goals", lambda f, a, h1, a1: (f + a) % 2 == 0, needs_ht=False)
    add("PARITY", "NEPAR", "NEPAR", "Odd number of goals", "Goals", lambda f, a, h1, a1: (f + a) % 2 == 1, needs_ht=False)

    # --- goal ranges ---------------------------------------------------------
    ft_codes = ("0-1", "0-2", "0-3", "0-4", "1", "1+", "1-2", "1-3", "1-4", "1-5", "1-6",
                "2", "2+", "2-3", "2-4", "2-5", "2-6", "3", "3+", "3-4", "3-5", "4", "4+", "5", "5+")
    for code in ft_codes:
        add("GOAL_RANGE_FT", code, code, f"{_goal_words(code)} in the match", "Goals",
            lambda f, a, h1, a1, r=_range(code): r(f + a), needs_ht=False)
    for code in ("I0", "I1", "I2", "I3", "I1+", "I2+", "I3+", "I0-1", "I0-2", "I1-2", "I2-3"):
        bare = code[1:]
        add("GOAL_RANGE_1H", code, bare, f"{_goal_words(bare)} in the first half", "Half-time",
            lambda f, a, h1, a1, r=_range(bare): r(h1 + a1))
    for code in ("II0", "II1", "II2", "II3", "II1+", "II2+", "II3+", "II0-1", "II0-2", "II1-2", "II2-3"):
        bare = code[2:]
        add("GOAL_RANGE_2H", code, bare, f"{_goal_words(bare)} in the second half", "Half-time",
            lambda f, a, h1, a1, r=_range(bare): r((f - h1) + (a - a1)))

    # --- team goals ----------------------------------------------------------
    for side, prefix in (("home", "I1"), ("away", "I2")):
        for code, plain in (("0", f"{side.title()} team does not score"), ("1+", f"{side.title()} team scores 1+"),
                            ("2+", f"{side.title()} team scores 2+"), ("3+", f"{side.title()} team scores 3+")):
            check = _range(code)
            pick = (lambda f, a: f) if side == "home" else (lambda f, a: a)
            add("TEAM_GOALS", f"{prefix} {code}", code, plain, "Team goals",
                lambda f, a, h1, a1, ch=check, p=pick: (ch(p(f, a)) if code != "0" else p(f, a) == 0),
                needs_ht=False)
    for half, offset, group in (("1H", 1, "Team goals"), ("2H", 2, "Team goals")):
        for side, prefix in (("home", "I1" if half == "1H" else "II1"), ("away", "I2" if half == "1H" else "II2")):
            for code, plain in (("0", f"{side.title()} team does not score in the {half.replace('H', 'st' if half == '1H' else 'nd')} half"),
                                ("1+", f"{side.title()} team scores in the {half.replace('H', 'st' if half == '1H' else 'nd')} half"),
                                ("2+", f"{side.title()} team scores 2+ in the {half.replace('H', 'st' if half == '1H' else 'nd')} half")):
                def goals(f, a, h1, a1, s=side, h=half):
                    if h == "1H":
                        return h1 if s == "home" else a1
                    return (f - h1) if s == "home" else (a - a1)
                add("TEAM_GOALS_HALF", f"{prefix} {code}", code, plain, group,
                    lambda f, a, h1, a1, ch=_range(code), g=goals: (g(f, a, h1, a1) == 0 if code == "0" else ch(g(f, a, h1, a1))))

    # --- half goal combos ----------------------------------------------------
    for first, second in (("I1+", "II1+"), ("I1+", "II2+"), ("I1+", "II3+"), ("I2+", "II1+"),
                          ("I2+", "II2+"), ("I2+", "II3+"), ("I1-2", "II1-2"), ("I1-3", "II1-3")):
        f_range = _range(first[1:])
        s_range = _range(second[2:])
        add("HALF_GOAL_COMBOS", f"{first}&{second}", f"{first}&{second}",
            f"{first[1:]} goals in the first half and {second[2:]} in the second", "Combos",
            lambda f, a, h1, a1, fr=f_range, sr=s_range: fr(h1 + a1) and sr((f - h1) + (a - a1)))

    # --- more goals in a half -----------------------------------------------
    for code, plain, test in (
        ("I>II", "More goals in the first half", lambda h1, a1, h2, a2: h1 + a1 > h2 + a2),
        ("I=II", "Same number of goals in each half", lambda h1, a1, h2, a2: h1 + a1 == h2 + a2),
        ("I<II", "More goals in the second half", lambda h1, a1, h2, a2: h1 + a1 < h2 + a2),
    ):
        add("MORE_GOALS_HALF", code, code, plain, "Goals",
            lambda f, a, h1, a1, t=test: t(h1, a1, f - h1, a - a1))

    # --- HT/FT ---------------------------------------------------------------
    for ht in "1X2":
        for ft in "1X2":
            add("HTFT", f"{ht}-{ft}", f"{ht}-{ft}",
                f"{HT_WORDS[ht]} at half-time, {FT_WORDS[ft]} at full-time", "HT/FT",
                lambda f, a, h1, a1, x=ht, y=ft: result(h1, a1) == x and result(f, a) == y)
    for ht, ft, plain in (("1-1", "2+", "Home ahead at HT and FT with 2+ goals"), ("1-1", "3+", "Home ahead at HT and FT with 3+ goals"),
                          ("2-2", "2+", "Away ahead at HT and FT with 2+ goals"), ("2-2", "3+", "Away ahead at HT and FT with 3+ goals")):
        add("HTFT_AND_GOALS", f"{ht}&{ft}", f"{ht}&{ft}", plain, "HT/FT",
            lambda f, a, h1, a1, x=ht, r=_range(ft): result(h1, a1) == x[0] and result(f, a) == x[2] and r(f + a))
    for ht, ft in (("1-1", "gg"), ("1-1", "ng"), ("X-1", "gg"), ("X-1", "ng"), ("X-X", "gg"),
                   ("X-2", "gg"), ("X-2", "ng"), ("2-2", "gg"), ("2-2", "ng")):
        is_gg = ft == "gg"
        add("HTFT_COMBO", f"{ht}&{ft}", f"{ht}&{ft}",
            f"{HT_WORDS[ht[0]]} at half-time, {FT_WORDS[ht[2]]} at full-time and "
            + ("both teams score" if is_gg else "not both teams score"),
            "HT/FT",
            lambda f, a, h1, a1, x=ht, gg=is_gg: (
                result(h1, a1) == x[0] and result(f, a) == x[2]
                and ((f >= 1 and a >= 1) if gg else not (f >= 1 and a >= 1))
            ))
    for first in ("1X", "12", "X2"):
        for second in ("1X", "12", "X2"):
            add("HTFT_DC", f"{first}-{second}", f"{first}-{second}",
                f"{first} at half-time, {second} at full-time", "HT/FT",
                lambda f, a, h1, a1, x=first, y=second: result(h1, a1) in set(x) and result(f, a) in set(y))

    # --- specials ------------------------------------------------------------
    add("WIN_BOTH_HALVES", "DP 1", "DP1", "Home team wins both halves", "Result & double chance",
        lambda f, a, h1, a1: h1 > a1 and f - h1 > a - a1)
    add("WIN_BOTH_HALVES", "DP 2", "DP2", "Away team wins both halves", "Result & double chance",
        lambda f, a, h1, a1: a1 > h1 and a - a1 > f - h1)
    for code, plain, fn in (
        ("SP 1", "Home wins to nil", lambda f, a, h1, a1: f > a and a == 0),
        ("SP 2", "Away wins to nil", lambda f, a, h1, a1: a > f and f == 0),
        ("HP 1", "Home wins by 2+", lambda f, a, h1, a1: f - a >= 2),
        ("HP 2", "Away wins by 2+", lambda f, a, h1, a1: a - f >= 2),
        ("HH 1 3+", "Home wins by 3+", lambda f, a, h1, a1: f - a >= 3),
        ("HH 2 3+", "Away wins by 3+", lambda f, a, h1, a1: a - f >= 3),
    ):
        family = "WIN_TO_NIL" if code.startswith("SP") else "MARGIN"
        add(family, code, code, plain, "Result & double chance", fn, needs_ht=False)

    # --- correct score -------------------------------------------------------
    for home in range(0, 5):
        for away in range(0, 5):
            if home in (0, 1) and away in (0, 1) and (home, away) not in ((0, 0), (1, 1)):
                continue
            add("CORRECT_SCORE", f"{home}:{away}", f"{home}:{away}", f"Correct score {home}-{away}", "Correct score",
                lambda f, a, h1, a1, x=home, y=away: f == x and a == y, needs_ht=False)

    # --- result and double chance with goals --------------------------------
    for code, plain in (("1&2+", "Home win and 2+ goals"), ("1&3+", "Home win and 3+ goals"),
                        ("X&2+", "Draw and 2+ goals"), ("2&2+", "Away win and 2+ goals"),
                        ("2&3+", "Away win and 3+ goals"), ("1&0-2", "Home win and 0-2 goals")):
        add("RESULT_AND_GOALS", code, code, plain, "Combos",
            lambda f, a, h1, a1, c=code: result(f, a) == c[0] and _range(c.split("&")[1])(f + a), needs_ht=False)
    for code, plain in (("1X&0-2", "Home or draw with 0-2 goals"), ("1X&2+", "Home or draw with 2+ goals"),
                        ("1X&3+", "Home or draw with 3+ goals"), ("X2&0-2", "Draw or away win with 0-2 goals"),
                        ("X2&2+", "Draw or away win with 2+ goals"), ("12&2+", "No draw with 2+ goals")):
        add("DC_AND_GOALS", code, code, plain, "Combos",
            lambda f, a, h1, a1, c=code: result(f, a) in set(c.split("&")[0]) and _range(c.split("&")[1])(f + a),
            needs_ht=False)

    return markets


MARKETS: list[Market] = _build()
MARKET_BY_ID: dict[str, Market] = {market.id: market for market in MARKETS}
MARKET_GROUPS = tuple(dict.fromkeys(market.group for market in MARKETS))


def family_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for market in MARKETS:
        counts[market.family] = counts.get(market.family, 0) + 1
    return dict(sorted(counts.items()))


def settle(market: Market, fthg: int, ftag: int, hthg: int | None, htag: int | None) -> bool | None:
    """Settle one market; None when the row has no half-time score it needs."""
    if market.needs_ht and (hthg is None or htag is None):
        return None
    return bool(market.settle(fthg, ftag, int(hthg or 0), int(htag or 0)))


_MASK = None


def market_mask():
    """(N_CELLS, len(MARKETS)) float32 mask over the half-score grid."""
    global _MASK
    if _MASK is not None:
        return _MASK

    import numpy as np

    from .model.grid import N_CELLS, N_HALF

    mask = np.zeros((N_CELLS, len(MARKETS)), dtype=np.float32)
    for h1 in range(N_HALF):
        for a1 in range(N_HALF):
            for h2 in range(N_HALF):
                for a2 in range(N_HALF):
                    index = (((h1 * N_HALF) + a1) * N_HALF + h2) * N_HALF + a2
                    fthg, ftag = h1 + h2, a1 + a2
                    for position, market in enumerate(MARKETS):
                        mask[index, position] = 1.0 if market.settle(fthg, ftag, h1, a1) else 0.0
    _MASK = mask
    return mask


def probabilities(joint) -> "object":
    """Market probabilities from a joint half-score vector (grid ordering)."""
    return joint @ market_mask()


def catalogue_yaml() -> str:
    """Render pipeline/mozzart_markets.yaml from this registry (single source of truth)."""
    lines = [
        "# Mozzart market catalogue for football-picks-v2.",
        "# Generated from pipeline/markets.py — edit the module, not this file.",
        "# Every entry is settled from (HT, FT) goals only; `settle` is the rule in words.",
        "#",
        f"# families: {len(family_counts())}   markets: {len(MARKETS)}",
        "markets:",
    ]
    for market in MARKETS:
        lines.extend(
            [
                f"  - id: {market.id}",
                f"    family: {market.family}",
                f"    code: \"{market.code}\"",
                f"    mozzart_label: \"{market.mozzart_label}\"",
                f"    plain: \"{market.plain}\"",
                f"    group: \"{market.group}\"",
                f"    needs_ht: {str(market.needs_ht).lower()}",
                f"    settle: \"{_rule_text(market)}\"",
            ]
        )
    lines.append("")
    lines.append("not_settleable:")
    for family, reason in NOT_SETTLABLE:
        lines.append(f"  - family: \"{family}\"")
        lines.append(f"    reason: \"{reason}\"")
    return "\n".join(lines) + "\n"


def _rule_text(market: Market) -> str:
    """Human-readable settlement rule, derived from the market's family and code."""
    code = market.code
    family = market.family
    rules = {
        "RESULT": "full-time result is {code}",
        "DOUBLE_CHANCE": "full-time result is one of {code}",
        "HALF_RESULT": "half-time result is {last}",
        "SECOND_HALF_RESULT": "second-half result is {last}",
        "HALF_DC": "half-time result is one of {tail}",
        "SECOND_HALF_DC": "second-half result is one of {tail2}",
        "BTTS": "both teams score",
        "BTTS_1H": "both teams score before half-time",
        "BTTS_2H": "both teams score after half-time",
        "PARITY": "total goals are {parity}",
        "GOAL_RANGE_FT": "total goals {bare}",
        "GOAL_RANGE_1H": "first-half goals {bare1}",
        "GOAL_RANGE_2H": "second-half goals {bare2}",
        "TEAM_GOALS": "{side} goals {bare}",
        "TEAM_GOALS_HALF": "{side} goals in that half {bare}",
        "HALF_GOAL_COMBOS": "first-half goals and second-half goals both match the code",
        "MORE_GOALS_HALF": "goals compare between halves as the code says",
        "HTFT": "half-time result is {first}, full-time result is {last}",
        "HTFT_AND_GOALS": "HT/FT result is {first} and total goals {tail}",
        "HTFT_COMBO": "HT/FT result is {first} and both teams {gg}",
        "HTFT_DC": "half-time result in the first double chance and full-time in the second",
        "WIN_BOTH_HALVES": "the named team wins both halves",
        "WIN_TO_NIL": "the named team wins and the other does not score",
        "MARGIN": "the named team wins by the stated margin or more",
        "CORRECT_SCORE": "full-time score is exactly {code}",
        "RESULT_AND_GOALS": "full-time result is {first} and total goals {tail}",
        "DC_AND_GOALS": "full-time double chance is {first} and total goals {tail}",
    }
    template = rules.get(family, "see family {family}")
    return template.format(
        code=code,
        last=code[-1],
        tail=code[1:],
        tail2=code[2:],
        bare=code[1:] if family == "GOAL_RANGE_1H" else (code[2:] if family == "GOAL_RANGE_2H" else code),
        bare1=code[1:],
        bare2=code[2:],
        side="home" if code.startswith("I1") else "away",
        first=code.split("&")[0],
        gg="score" if code.endswith("gg") else "do not both score",
        parity="even" if code == "PAR" else "odd",
        family=family,
    )
