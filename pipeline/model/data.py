"""Vectorised training arrays so the engines can fit with numpy rather than
python loops over ~20k matches.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

from ..outcomes import OUTCOMES, evaluate
from ..parse import Match

EPOCH = dt.date(2000, 1, 1)


def day_number(value: dt.date) -> float:
    return float((value - EPOCH).days)


@dataclass(slots=True)
class MatchArrays:
    teams: list[str]
    team_index: dict[str, int]
    dates: np.ndarray
    home: np.ndarray
    away: np.ndarray
    hits: np.ndarray          # (n, 62) uint8 — outcome true/false when applicable
    applicable: np.ndarray    # (n, 62) uint8 — 0 when the row lacks half-time data
    fthg: np.ndarray
    ftag: np.ndarray
    hthg: np.ndarray          # NaN when missing
    htag: np.ndarray
    odds: list[dict]

    def __len__(self) -> int:
        return int(self.dates.shape[0])


def build_arrays(matches: list[Match]) -> MatchArrays:
    teams = sorted({m.home for m in matches} | {m.away for m in matches})
    team_index = {team: position for position, team in enumerate(teams)}

    count = len(matches)
    hits = np.zeros((count, len(OUTCOMES)), dtype=np.uint8)
    applicable = np.zeros((count, len(OUTCOMES)), dtype=np.uint8)
    dates = np.zeros(count, dtype=np.float64)
    home = np.zeros(count, dtype=np.int32)
    away = np.zeros(count, dtype=np.int32)
    fthg = np.zeros(count, dtype=np.float64)
    ftag = np.zeros(count, dtype=np.float64)
    hthg = np.full(count, np.nan)
    htag = np.full(count, np.nan)

    for row, match in enumerate(matches):
        dates[row] = day_number(match.date)
        home[row] = team_index[match.home]
        away[row] = team_index[match.away]
        fthg[row] = match.fthg
        ftag[row] = match.ftag
        if match.hthg is not None and match.htag is not None:
            hthg[row] = match.hthg
            htag[row] = match.htag
        for column, outcome in enumerate(OUTCOMES):
            if outcome.needs_ht and not match.has_ht:
                continue
            applicable[row, column] = 1
            hits[row, column] = 1 if outcome.fn(match.fthg, match.ftag, match.hthg, match.htag) else 0

    return MatchArrays(
        teams=teams,
        team_index=team_index,
        dates=dates,
        home=home,
        away=away,
        hits=hits,
        applicable=applicable,
        fthg=fthg,
        ftag=ftag,
        hthg=hthg,
        htag=htag,
        odds=[dict(match.odds) for match in matches],
    )


def subset(arrays: MatchArrays, indices: np.ndarray) -> MatchArrays:
    """Slice a training set without re-evaluating the outcome matrix."""
    return MatchArrays(
        teams=arrays.teams,
        team_index=arrays.team_index,
        dates=arrays.dates[indices],
        home=arrays.home[indices],
        away=arrays.away[indices],
        hits=arrays.hits[indices],
        applicable=arrays.applicable[indices],
        fthg=arrays.fthg[indices],
        ftag=arrays.ftag[indices],
        hthg=arrays.hthg[indices],
        htag=arrays.htag[indices],
        odds=[arrays.odds[int(i)] for i in indices],
    )


def recency_weights(dates: np.ndarray, reference_day: float, half_life_days: float) -> np.ndarray:
    age = np.maximum(reference_day - dates, 0.0)
    return np.power(0.5, age / float(half_life_days))


def team_sums(indices: np.ndarray, weighted: np.ndarray, n_teams: int) -> np.ndarray:
    """Column-wise weighted sums grouped by team index."""
    return np.stack(
        [np.bincount(indices, weights=weighted[:, column], minlength=n_teams) for column in range(weighted.shape[1])],
        axis=1,
    )
