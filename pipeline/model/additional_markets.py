"""Research-only candidate combinations, not registered in production.

Definitions reuse the production Market/settlement rule type and the same
half-score grid ordering. Importing this module never mutates MARKETS.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from ..markets import MARKET_BY_ID, Market, result, settle
from .grid import N_CELLS, N_HALF

EVIDENCE_FILE = "soccer_events__20260924T213344Z.json"
EVIDENCE_DATE = "2026-09-24T21:33:44Z"
EVIDENCE_LOCATION = "/home/nikola/code/Work/Betting/data/mozzart/raw"
CONFIRMED = "confirmed_in_existing_snapshot"
UNCONFIRMED = "insufficient_catalogue_evidence"


def _btts(fthg: int, ftag: int) -> bool:
    return fthg > 0 and ftag > 0


def _result_code(fthg: int, ftag: int, codes: str) -> bool:
    return result(fthg, ftag) in set(codes)


def _goal_band(total: int, code: str) -> bool:
    if code == "0-2":
        return total <= 2
    if code == "2+":
        return total >= 2
    return total >= 3


def _evidence(section: str, market_id: str, selection: str) -> dict:
    return {
        "source": "read-only v1 Mozzart raw snapshot",
        "date": EVIDENCE_DATE,
        "file": EVIDENCE_FILE,
        "location": EVIDENCE_LOCATION,
        "section": section,
        "provider_market_id": market_id,
        "selection": selection,
    }


@dataclass(frozen=True, slots=True)
class CandidateSpec:
    market: Market
    catalogue_status: str
    evidence: dict | None = None
    equivalent_existing_id: str | None = None

    @property
    def id(self) -> str:
        return self.market.id

    @property
    def group(self) -> str:
        return self.market.group

    @property
    def activation_blocker(self) -> str | None:
        if self.equivalent_existing_id:
            return f"logically equivalent to {self.equivalent_existing_id}"
        if self.catalogue_status != CONFIRMED:
            return "catalogue availability not confirmed"
        return None


def _market(family: str, code: str, plain: str, group: str, predicate: Callable, needs_ht: bool) -> Market:
    return Market(f"{family}:{code}", family, code, code, plain, group, predicate, needs_ht)


def _htft_combo(ht: str, ft: str) -> CandidateSpec:
    code = f"{ht}-{ft}&gg"
    market = _market(
        "HTFT_COMBO", code,
        f"{ht} at half-time, {ft} at full-time and both teams score",
        "HT/FT",
        lambda f, a, h1, a1, x=ht, y=ft: (
            result(h1, a1) == x and result(f, a) == y and _btts(f, a)
        ),
        True,
    )
    equivalent = {
        "1-X": "HTFT:1-X", "1-2": "HTFT:1-2",
        "2-1": "HTFT:2-1", "2-X": "HTFT:2-X",
    }.get(f"{ht}-{ft}")
    return CandidateSpec(market, UNCONFIRMED, None, equivalent)


def _result_btts(code: str, suffix: str) -> CandidateSpec:
    goals = suffix == "gg"
    plain = {
        "1": "Home win", "X": "Draw", "2": "Away win",
        "1X": "Home win or draw", "12": "Home or away win", "X2": "Draw or away win",
    }[code]
    market = _market(
        "RESULT_AND_BTTS", f"{code}&{suffix}",
        f"{plain} and {'both teams score' if goals else 'at least one team fails to score'}",
        "Combos",
        lambda f, a, h1, a1, x=code, g=goals: _result_code(f, a, x) and _btts(f, a) == g,
        False,
    )
    confirmed = {
        ("1", "gg"): ("Konačan ishod kombinazzije", "92:FULL_TIME", "1 & gg"),
        ("2", "gg"): ("Konačan ishod kombinazzije", "92:FULL_TIME", "2 & gg"),
    } if code in ("1", "2") else {}
    evidence = _evidence(*confirmed[(code, suffix)]) if (code, suffix) in confirmed else None
    return CandidateSpec(market, CONFIRMED if evidence else UNCONFIRMED, evidence)


def _dc_btts(code: str, suffix: str) -> CandidateSpec:
    goals = suffix == "gg"
    plain = {"1X": "Home win or draw", "12": "Home or away win", "X2": "Draw or away win"}[code]
    market = _market(
        "DC_AND_BTTS", f"{code}&{suffix}",
        f"{plain} and {'both teams score' if goals else 'at least one team fails to score'}",
        "Combos",
        lambda f, a, h1, a1, x=code, g=goals: _result_code(f, a, x) and _btts(f, a) == g,
        False,
    )
    confirmed = {
        ("1X", "gg"): ("Dupla šansa kombinazzije", "94:FULL_TIME", "1X & gg"),
        ("X2", "gg"): ("Dupla šansa kombinazzije", "94:FULL_TIME", "X2 & gg"),
    }
    evidence = _evidence(*confirmed[(code, suffix)]) if (code, suffix) in confirmed else None
    return CandidateSpec(market, CONFIRMED if evidence else UNCONFIRMED, evidence)


def _btts_goals(btts_code: str, band: str) -> CandidateSpec:
    goals = btts_code == "GG"
    market = _market(
        "BTTS_AND_GOALS", f"{btts_code}&{band}",
        f"{'Both teams score' if goals else 'At least one team fails to score'} and "
        f"{'0-2' if band == '0-2' else '3+'} total goals",
        "Combos",
        lambda f, a, h1, a1, g=goals, b=band: _btts(f, a) == g and _goal_band(f + a, b),
        False,
    )
    evidence = _evidence("Oba tima daju gol", "67:FULL_TIME", "GG3+") if (btts_code, band) == ("GG", "3+") else None
    return CandidateSpec(market, CONFIRMED if evidence else UNCONFIRMED, evidence)


def _htft_goals(band: str) -> CandidateSpec:
    market = _market(
        "HTFT_AND_GOALS", f"X-X&{band}",
        f"Level at half-time, draw at full-time and {band} total goals",
        "HT/FT",
        lambda f, a, h1, a1, b=band: (
            result(h1, a1) == "X" and result(f, a) == "X" and _goal_band(f + a, b)
        ),
        True,
    )
    evidence = _evidence("Poluvreme - Kraj + Golovi", "96:FULL_TIME", "X-X&3+") if band == "3+" else None
    return CandidateSpec(market, CONFIRMED if evidence else UNCONFIRMED, evidence)


HTFT_CANDIDATES = tuple(_htft_combo(*code.split("-")) for code in ("1-X", "1-2", "2-1", "2-X")) + (
    CandidateSpec(
        _market(
            "HTFT_COMBO", "X-X&ng", "Level at half-time, draw at full-time and at least one team fails to score",
            "HT/FT",
            lambda f, a, h1, a1: result(h1, a1) == "X" and result(f, a) == "X" and not _btts(f, a),
            True,
        ),
        UNCONFIRMED,
    ),
)
RESULT_BTTS_CANDIDATES = (
    tuple(_result_btts(code, suffix) for code in ("1", "X", "2") for suffix in ("gg", "ng"))
    + tuple(_dc_btts(code, suffix) for code in ("1X", "12", "X2") for suffix in ("gg", "ng"))
)
BTTS_GOALS_CANDIDATES = tuple(
    _btts_goals(code, band)
    for code in ("GG", "NG")
    for band in ("0-2", "3+")
)
HTFT_GOALS_CANDIDATES = (_htft_goals("2+"), _htft_goals("3+"))

CANDIDATES: tuple[CandidateSpec, ...] = (
    HTFT_CANDIDATES + RESULT_BTTS_CANDIDATES + BTTS_GOALS_CANDIDATES + HTFT_GOALS_CANDIDATES
)
CANDIDATE_BY_ID = {spec.id: spec for spec in CANDIDATES}
REQUESTED_IDS = tuple(spec.id for spec in CANDIDATES)
AUGMENTED_CANDIDATES = tuple(spec for spec in CANDIDATES if spec.equivalent_existing_id is None)
AUGMENTED_IDS = frozenset(spec.id for spec in AUGMENTED_CANDIDATES)
CONFIRMED_IDS = frozenset(spec.id for spec in CANDIDATES if spec.catalogue_status == CONFIRMED)
EQUIVALENT_IDS = frozenset(spec.id for spec in CANDIDATES if spec.equivalent_existing_id)
IMPOSSIBLE_IDS = (
    "HTFT_COMBO:1-X&ng", "HTFT_COMBO:1-2&ng",
    "HTFT_COMBO:2-1&ng", "HTFT_COMBO:2-X&ng",
)


@lru_cache(maxsize=1)
def candidate_mask() -> np.ndarray:
    """(N_CELLS, candidates) mask in the existing half-score grid ordering."""
    mask = np.zeros((N_CELLS, len(CANDIDATES)), dtype=np.float32)
    for h1 in range(N_HALF):
        for a1 in range(N_HALF):
            for h2 in range(N_HALF):
                for a2 in range(N_HALF):
                    index = (((h1 * N_HALF) + a1) * N_HALF + h2) * N_HALF + a2
                    fthg, ftag = h1 + h2, a1 + a2
                    for position, spec in enumerate(CANDIDATES):
                        mask[index, position] = 1.0 if spec.market.settle(fthg, ftag, h1, a1) else 0.0
    return mask


def candidate_probabilities(joint: np.ndarray) -> np.ndarray:
    return joint @ candidate_mask()


def settle_candidate(spec_or_id: CandidateSpec | str, fthg: int, ftag: int, hthg: int | None, htag: int | None) -> bool | None:
    spec = CANDIDATE_BY_ID[spec_or_id] if isinstance(spec_or_id, str) else spec_or_id
    return settle(spec.market, fthg, ftag, hthg, htag)


def catalogue_summary() -> dict:
    return {
        "current_private_snapshot_checked": False,
        "current_private_snapshot_note": (
            "No private price-store checkout was available locally; no Mozzart request or budget was used."
        ),
        "existing_evidence": {
            "source": EVIDENCE_FILE,
            "date": EVIDENCE_DATE,
            "location": EVIDENCE_LOCATION,
            "scope": "historical read-only snapshot; confirms observation, not current availability",
        },
        "candidates": [
            {
                "id": spec.id,
                "group": spec.group,
                "catalogue_status": spec.catalogue_status,
                "evidence": spec.evidence,
                "equivalent_existing_id": spec.equivalent_existing_id,
                "activation_blocker": spec.activation_blocker,
                "exists_in_production": spec.id in MARKET_BY_ID,
            }
            for spec in CANDIDATES
        ],
    }
