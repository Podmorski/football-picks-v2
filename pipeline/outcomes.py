"""Single source of truth for every counted outcome.

An outcome is a predicate over a match's goals:
``fn(fthg, ftag, hthg, htag) -> bool``. Outcomes flagged ``needs_ht`` are only
meaningful when both half-time goal counts are present; rows without them are
excluded from the sample for those outcomes only, never for FT-based ones.

Second-half goals are derived: ``FT - HT``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

Predicate = Callable[[int, int, int | None, int | None], bool]


@dataclass(frozen=True, slots=True)
class Outcome:
    id: str
    label: str
    group: str
    needs_ht: bool
    fn: Predicate


def result(goals_for: int, goals_against: int) -> str:
    if goals_for > goals_against:
        return "1"
    if goals_for < goals_against:
        return "2"
    return "X"


def first_half_goals(hthg: int | None, htag: int | None) -> int | None:
    if hthg is None or htag is None:
        return None
    return hthg + htag


def second_half_goals(fthg: int, ftag: int, hthg: int | None, htag: int | None) -> int | None:
    if hthg is None or htag is None:
        return None
    return (fthg - hthg) + (ftag - htag)


# --- predicate factories ---------------------------------------------------

def _ft(code: str) -> Predicate:
    return lambda fthg, ftag, hthg, htag: result(fthg, ftag) == code


def _ht(code: str) -> Predicate:
    return lambda fthg, ftag, hthg, htag: result(hthg, htag) == code


def _htft(ht_code: str, ft_code: str) -> Predicate:
    return lambda fthg, ftag, hthg, htag: (
        result(hthg, htag) == ht_code and result(fthg, ftag) == ft_code
    )


def _result_in(codes: set[str]) -> Predicate:
    return lambda fthg, ftag, hthg, htag: result(fthg, ftag) in codes


def _in_range(low: int, high: int) -> Predicate:
    return lambda fthg, ftag, hthg, htag: low <= fthg + ftag <= high


def _at_least(minimum: int) -> Predicate:
    return lambda fthg, ftag, hthg, htag: fthg + ftag >= minimum


def _over(line: float) -> Predicate:
    return lambda fthg, ftag, hthg, htag: fthg + ftag > line


def _under(line: float) -> Predicate:
    return lambda fthg, ftag, hthg, htag: fthg + ftag < line


def _btts(fthg, ftag, hthg, htag) -> bool:
    return fthg >= 1 and ftag >= 1


def _btts_first_half(fthg, ftag, hthg, htag) -> bool:
    return hthg >= 1 and htag >= 1


def _home_at_least(minimum: int) -> Predicate:
    return lambda fthg, ftag, hthg, htag: fthg >= minimum


def _away_at_least(minimum: int) -> Predicate:
    return lambda fthg, ftag, hthg, htag: ftag >= minimum


def _home_first_half_at_least(minimum: int) -> Predicate:
    return lambda fthg, ftag, hthg, htag: hthg >= minimum


def _away_first_half_at_least(minimum: int) -> Predicate:
    return lambda fthg, ftag, hthg, htag: htag >= minimum


def _home_scores_both_halves(fthg, ftag, hthg, htag) -> bool:
    return hthg >= 1 and fthg - hthg >= 1


def _away_scores_both_halves(fthg, ftag, hthg, htag) -> bool:
    return htag >= 1 and ftag - htag >= 1


def _first_half_at_least(minimum: int) -> Predicate:
    return lambda fthg, ftag, hthg, htag: hthg + htag >= minimum


def _second_half_at_least(minimum: int) -> Predicate:
    return lambda fthg, ftag, hthg, htag: (fthg - hthg) + (ftag - htag) >= minimum


def _more_goals_first_half(fthg, ftag, hthg, htag) -> bool:
    return hthg + htag > (fthg - hthg) + (ftag - htag)


def _more_goals_equal(fthg, ftag, hthg, htag) -> bool:
    return hthg + htag == (fthg - hthg) + (ftag - htag)


def _more_goals_second_half(fthg, ftag, hthg, htag) -> bool:
    return hthg + htag < (fthg - hthg) + (ftag - htag)


def _odd(fthg, ftag, hthg, htag) -> bool:
    return (fthg + ftag) % 2 == 1


def _even(fthg, ftag, hthg, htag) -> bool:
    return (fthg + ftag) % 2 == 0


def _c1(fthg, ftag, hthg, htag) -> bool:
    return result(fthg, ftag) in {"1", "X"} and fthg + ftag >= 3


def _c2(fthg, ftag, hthg, htag) -> bool:
    return (hthg + htag) >= 1 and ((fthg - hthg) + (ftag - htag)) >= 2


def _c3(fthg, ftag, hthg, htag) -> bool:
    return fthg >= 2 and fthg >= 1 and ftag >= 1


def _c4(fthg, ftag, hthg, htag) -> bool:
    return fthg >= 1 and ftag >= 1 and fthg + ftag >= 3


def _c5(fthg, ftag, hthg, htag) -> bool:
    return result(fthg, ftag) in {"1", "X"} and fthg >= 1 and ftag >= 1


def _c6(fthg, ftag, hthg, htag) -> bool:
    return result(fthg, ftag) in {"X", "2"} and fthg + ftag >= 3


def _c7(fthg, ftag, hthg, htag) -> bool:
    return (hthg + htag) >= 1 and ((fthg - hthg) + (ftag - htag)) >= 1


def _c8(fthg, ftag, hthg, htag) -> bool:
    return ftag >= 2 and fthg >= 1 and ftag >= 1


def _c9(fthg, ftag, hthg, htag) -> bool:
    return result(hthg, htag) == "X" and fthg + ftag >= 2


def _c10(fthg, ftag, hthg, htag) -> bool:
    return hthg >= 1 and fthg + ftag >= 3


def _o(id: str, label: str, group: str, fn: Predicate, needs_ht: bool = False) -> Outcome:
    return Outcome(id=id, label=label, group=group, needs_ht=needs_ht, fn=fn)


OUTCOMES: list[Outcome] = [
    # FT result
    _o("ft_1", "1", "FT result", _ft("1")),
    _o("ft_x", "X", "FT result", _ft("X")),
    _o("ft_2", "2", "FT result", _ft("2")),
    # HT result
    _o("ht_1", "1", "HT result", _ht("1"), needs_ht=True),
    _o("ht_x", "X", "HT result", _ht("X"), needs_ht=True),
    _o("ht_2", "2", "HT result", _ht("2"), needs_ht=True),
    # HT/FT (all nine)
    _o("htft_11", "1/1", "HT/FT", _htft("1", "1"), needs_ht=True),
    _o("htft_1x", "1/X", "HT/FT", _htft("1", "X"), needs_ht=True),
    _o("htft_12", "1/2", "HT/FT", _htft("1", "2"), needs_ht=True),
    _o("htft_x1", "X/1", "HT/FT", _htft("X", "1"), needs_ht=True),
    _o("htft_xx", "X/X", "HT/FT", _htft("X", "X"), needs_ht=True),
    _o("htft_x2", "X/2", "HT/FT", _htft("X", "2"), needs_ht=True),
    _o("htft_21", "2/1", "HT/FT", _htft("2", "1"), needs_ht=True),
    _o("htft_2x", "2/X", "HT/FT", _htft("2", "X"), needs_ht=True),
    _o("htft_22", "2/2", "HT/FT", _htft("2", "2"), needs_ht=True),
    # Double chance
    _o("dc_1x", "1X", "Double chance", _result_in({"1", "X"})),
    _o("dc_x2", "X2", "Double chance", _result_in({"X", "2"})),
    _o("dc_12", "12", "Double chance", _result_in({"1", "2"})),
    # Total goals
    _o("tg_0_1", "0-1", "Total goals", _in_range(0, 1)),
    _o("tg_2_3", "2-3", "Total goals", _in_range(2, 3)),
    _o("tg_4_6", "4-6", "Total goals", _in_range(4, 6)),
    _o("tg_1plus", "1+", "Total goals", _at_least(1)),
    _o("tg_2plus", "2+", "Total goals", _at_least(2)),
    _o("tg_3plus", "3+", "Total goals", _at_least(3)),
    _o("tg_4plus", "4+", "Total goals", _at_least(4)),
    _o("tg_5plus", "5+", "Total goals", _at_least(5)),
    # Over/under
    _o("ou_o15", "Over 1.5", "Over/Under", _over(1.5)),
    _o("ou_u15", "Under 1.5", "Over/Under", _under(1.5)),
    _o("ou_o25", "Over 2.5", "Over/Under", _over(2.5)),
    _o("ou_u25", "Under 2.5", "Over/Under", _under(2.5)),
    _o("ou_o35", "Over 3.5", "Over/Under", _over(3.5)),
    _o("ou_u35", "Under 3.5", "Over/Under", _under(3.5)),
    # BTTS
    _o("btts_yes", "Yes", "BTTS", _btts),
    _o("btts_no", "No", "BTTS", lambda f, a, h1, a1: not (f >= 1 and a >= 1)),
    _o("btts_1h", "1H BTTS", "BTTS", _btts_first_half, needs_ht=True),
    # Parity
    _o("odd", "Odd", "Odd/Even", _odd),
    _o("even", "Even", "Odd/Even", _even),
    # More goals by half
    _o("mg_1h", "1H more", "More goals", _more_goals_first_half, needs_ht=True),
    _o("mg_eq", "Equal", "More goals", _more_goals_equal, needs_ht=True),
    _o("mg_2h", "2H more", "More goals", _more_goals_second_half, needs_ht=True),
    # Half goals
    _o("h1_1plus", "1H 1+", "Half goals", _first_half_at_least(1), needs_ht=True),
    _o("h1_2plus", "1H 2+", "Half goals", _first_half_at_least(2), needs_ht=True),
    _o("h2_1plus", "2H 1+", "Half goals", _second_half_at_least(1), needs_ht=True),
    _o("h2_2plus", "2H 2+", "Half goals", _second_half_at_least(2), needs_ht=True),
    # Team goals
    _o("home_1plus", "Home 1+", "Team goals", _home_at_least(1)),
    _o("home_2plus", "Home 2+", "Team goals", _home_at_least(2)),
    _o("away_1plus", "Away 1+", "Team goals", _away_at_least(1)),
    _o("away_2plus", "Away 2+", "Team goals", _away_at_least(2)),
    _o("home_1h_1plus", "Home 1+ in 1H", "Team goals", _home_first_half_at_least(1), needs_ht=True),
    _o("away_1h_1plus", "Away 1+ in 1H", "Team goals", _away_first_half_at_least(1), needs_ht=True),
    _o("home_both_halves", "Home scores both halves", "Team goals", _home_scores_both_halves, needs_ht=True),
    _o("away_both_halves", "Away scores both halves", "Team goals", _away_scores_both_halves, needs_ht=True),
    # Combos
    _o("c1", "C1: 1X & 3+", "Combos", _c1),
    _o("c2", "C2: 1H 1+ & 2H 2+", "Combos", _c2, needs_ht=True),
    _o("c3", "C3: Home 2+ & BTTS", "Combos", _c3),
    _o("c4", "C4: BTTS & 3+", "Combos", _c4),
    _o("c5", "C5: 1X & BTTS", "Combos", _c5),
    _o("c6", "C6: X2 & 3+", "Combos", _c6),
    _o("c7", "C7: 1H 1+ & 2H 1+", "Combos", _c7, needs_ht=True),
    _o("c8", "C8: Away 2+ & BTTS", "Combos", _c8),
    _o("c9", "C9: HT X & FT 2+", "Combos", _c9, needs_ht=True),
    _o("c10", "C10: Home 1+ in 1H & 3+", "Combos", _c10, needs_ht=True),
]

OUTCOMES_BY_ID: dict[str, Outcome] = {outcome.id: outcome for outcome in OUTCOMES}
OUTCOME_IDS: tuple[str, ...] = tuple(outcome.id for outcome in OUTCOMES)
OUTCOME_GROUPS: tuple[str, ...] = tuple(dict.fromkeys(outcome.group for outcome in OUTCOMES))


def evaluate(outcome: Outcome, match) -> bool | None:
    """Return the hit, or None when the row cannot answer this outcome."""
    if outcome.needs_ht and not match.has_ht:
        return None
    return bool(outcome.fn(match.fthg, match.ftag, match.hthg, match.htag))


def _validate() -> None:
    if len(OUTCOMES_BY_ID) != len(OUTCOMES):
        raise AssertionError("duplicate outcome ids")
    for outcome in OUTCOMES:
        if not outcome.id or not outcome.label or not outcome.group:
            raise AssertionError(f"incomplete outcome {outcome!r}")


_validate()
