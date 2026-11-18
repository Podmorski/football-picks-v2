"""Goals engine: a Poisson / Dixon-Coles half-score grid from time-decayed team
strengths, optionally anchored on de-margined PRE-MATCH odds.

Only pre-match columns are ever read (PS*/Avg*/BbAv*/B365*). Closing columns
(PSC*, AvgC*, B365C*, BbAvC*) are deliberately absent from the key lists; the
leakage test asserts that changing them changes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .data import MatchArrays, recency_weights
from .grid import outcome_probabilities, solve_split, solve_total

from ..outcomes import OUTCOMES

PREMATCH_1X2 = (
    ("PSH", "PSD", "PSA"),
    ("AvgH", "AvgD", "AvgA"),
    ("BbAvH", "BbAvD", "BbAvA"),
    ("B365H", "B365D", "B365A"),
)
PREMATCH_OU = (
    ("P>2.5", "P<2.5"),
    ("Avg>2.5", "Avg<2.5"),
    ("BbAv>2.5", "BbAv<2.5"),
    ("B365>2.5", "B365<2.5"),
)

MIN_LAMBDA = 0.05
MAX_LAMBDA = 6.0


def power_demargin(implied: np.ndarray) -> np.ndarray:
    """Remove the bookmaker margin with the power method: find k with sum(p^k) = 1."""
    p = np.clip(np.asarray(implied, dtype=np.float64), 1e-6, 1.0)
    low, high = 0.2, 6.0
    for _ in range(60):
        mid = (low + high) / 2.0
        if float(np.power(p, mid).sum()) > 1.0:
            low = mid
        else:
            high = mid
    powered = np.power(p, (low + high) / 2.0)
    total = powered.sum()
    return powered / total if total > 0 else np.full_like(p, 1.0 / p.size)


def extract_targets(odds: dict) -> tuple[float, float, float, float | None] | None:
    """De-margined (home, draw, away, over 2.5) or None when odds are absent."""
    home = draw = away = None
    for keys in PREMATCH_1X2:
        if all(odds.get(key) for key in keys):
            probabilities = power_demargin([1.0 / odds[key] for key in keys])
            home, draw, away = (float(value) for value in probabilities)
            break
    if home is None or draw is None or away is None:
        return None

    over: float | None = None
    for keys in PREMATCH_OU:
        if all(odds.get(key) for key in keys):
            probabilities = power_demargin([1.0 / odds[key] for key in keys])
            over = float(probabilities[0])
            break
    return home, draw, away, over


@dataclass(slots=True)
class GoalsModel:
    att: np.ndarray
    dfn: np.ndarray
    played: np.ndarray
    league_home: float
    league_away: float
    share_home: float
    share_away: float
    rho: float = -0.05

    def lambdas(self, home_index: np.ndarray, away_index: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        home = self.league_home * self.att[home_index] * self.dfn[away_index]
        away = self.league_away * self.att[away_index] * self.dfn[home_index]
        return np.clip(home, MIN_LAMBDA, MAX_LAMBDA), np.clip(away, MIN_LAMBDA, MAX_LAMBDA)

    def probabilities(
        self,
        home_index: np.ndarray,
        away_index: np.ndarray,
        odds: list[dict],
        use_odds: bool = True,
    ) -> np.ndarray:
        home_lambda, away_lambda = self.lambdas(home_index, away_index)
        out = np.zeros((len(home_lambda), len(OUTCOMES)))
        for row in range(len(home_lambda)):
            lh = float(home_lambda[row])
            la = float(away_lambda[row])
            targets = extract_targets(odds[row]) if use_odds else None
            if targets is not None:
                p_home, _p_draw, _p_away, p_over = targets
                total = solve_total(p_over) if p_over is not None else lh + la
                share = solve_split(total, p_home, self.rho)
                lh, la = total * share, total * (1.0 - share)
            out[row] = outcome_probabilities(
                lh * self.share_home,
                la * self.share_away,
                lh * (1.0 - self.share_home),
                la * (1.0 - self.share_away),
                self.rho,
            )
        return out


def fit(
    arrays: MatchArrays,
    reference_day: float,
    half_life_days: float,
    k: float = 5.0,
    rho: float = -0.05,
) -> GoalsModel:
    n_teams = len(arrays.teams)
    weights = recency_weights(arrays.dates, reference_day, half_life_days)

    scored = np.bincount(arrays.home, weights=weights * arrays.fthg, minlength=n_teams) + np.bincount(
        arrays.away, weights=weights * arrays.ftag, minlength=n_teams
    )
    conceded = np.bincount(arrays.home, weights=weights * arrays.ftag, minlength=n_teams) + np.bincount(
        arrays.away, weights=weights * arrays.fthg, minlength=n_teams
    )
    played = np.bincount(arrays.home, weights=weights, minlength=n_teams) + np.bincount(
        arrays.away, weights=weights, minlength=n_teams
    )

    league_avg = float((weights * (arrays.fthg + arrays.ftag)).sum() / max(2.0 * weights.sum(), 1e-9))
    league_home = float((weights * arrays.fthg).sum() / max(weights.sum(), 1e-9))
    league_away = float((weights * arrays.ftag).sum() / max(weights.sum(), 1e-9))

    safe_played = np.maximum(played, 1e-9)
    attack_raw = np.where(played > 0, (scored / safe_played) / league_avg, 1.0)
    defence_raw = np.where(played > 0, (conceded / safe_played) / league_avg, 1.0)
    shrink = played / (played + k)
    att = np.exp(shrink * np.log(np.maximum(attack_raw, 1e-6)))
    dfn = np.exp(shrink * np.log(np.maximum(defence_raw, 1e-6)))

    has_ht = ~np.isnan(arrays.hthg)
    ht_home = float((weights[has_ht] * arrays.hthg[has_ht]).sum())
    ht_away = float((weights[has_ht] * arrays.htag[has_ht]).sum())
    ft_home = float((weights * arrays.fthg).sum())
    ft_away = float((weights * arrays.ftag).sum())
    share_home = float(np.clip(ht_home / max(ft_home, 1e-9), 0.25, 0.65)) if ft_home > 0 else 0.45
    share_away = float(np.clip(ht_away / max(ft_away, 1e-9), 0.25, 0.65)) if ft_away > 0 else 0.45

    return GoalsModel(
        att=att,
        dfn=dfn,
        played=played,
        league_home=league_home,
        league_away=league_away,
        share_home=share_home,
        share_away=share_away,
        rho=rho,
    )
