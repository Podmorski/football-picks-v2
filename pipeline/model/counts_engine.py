"""Counts engine: recency-weighted league rate plus shrunk home/away team deviations,
combined in log-odds space.

Only matches before the reference date are ever passed in; the engine has no notion
of the future.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .data import MatchArrays, recency_weights, team_sums

EPS = 1e-6


def logit(probability: np.ndarray | float) -> np.ndarray:
    p = np.clip(probability, EPS, 1.0 - EPS)
    return np.log(p / (1.0 - p))


def sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-value))


@dataclass(slots=True)
class CountsModel:
    half_life_days: float
    k: float
    league_logit: np.ndarray      # (62,)
    home_dev: np.ndarray          # (n_teams, 62) shrunk log-odds deviation at home
    away_dev: np.ndarray          # (n_teams, 62) shrunk log-odds deviation away
    n_home: np.ndarray            # (n_teams,) effective weighted home sample
    n_away: np.ndarray            # (n_teams,) effective weighted away sample
    home_hits: np.ndarray         # (n_teams, 62) raw home hit counts
    home_counts: np.ndarray       # (n_teams,) raw home match counts
    away_hits: np.ndarray         # (n_teams, 62) raw away hit counts
    away_counts: np.ndarray       # (n_teams,) raw away match counts
    league_counts: np.ndarray     # (62,) raw league sample sizes

    def probabilities(self, home_index: np.ndarray, away_index: np.ndarray) -> np.ndarray:
        z = self.league_logit[None, :] + self.home_dev[home_index] + self.away_dev[away_index]
        return sigmoid(z)

    def league_rates(self) -> np.ndarray:
        return sigmoid(self.league_logit)


def fit(arrays: MatchArrays, reference_day: float, half_life_days: float, k: float) -> CountsModel:
    n_teams = len(arrays.teams)
    weights = recency_weights(arrays.dates, reference_day, half_life_days)

    applicable = arrays.applicable.astype(np.float64)
    hits = arrays.hits.astype(np.float64)

    denominator = (weights[:, None] * applicable).sum(axis=0)
    league_rate = np.where(denominator > 0, (weights[:, None] * hits).sum(axis=0) / np.maximum(denominator, EPS), 0.5)
    league_logit = logit(league_rate)

    def venue_deviation(indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        weighted_hits = weights[:, None] * hits * applicable
        weighted_n = weights[:, None] * applicable
        numerator = team_sums(indices, weighted_hits, n_teams)
        samples = team_sums(indices, weighted_n, n_teams)[:, 0]
        rates = np.where(samples[:, None] > 0, numerator / np.maximum(samples[:, None], EPS), league_rate[None, :])
        deviation = logit(rates) - league_logit[None, :]
        shrink = (samples / (samples + k))[:, None]
        return shrink * deviation, samples

    home_dev, n_home = venue_deviation(arrays.home)
    away_dev, n_away = venue_deviation(arrays.away)

    def raw_counts(indices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        hit_sums = team_sums(indices, hits * applicable, n_teams)
        match_counts = team_sums(indices, applicable, n_teams)[:, 0]
        return hit_sums, match_counts

    home_hits, home_counts = raw_counts(arrays.home)
    away_hits, away_counts = raw_counts(arrays.away)

    return CountsModel(
        half_life_days=float(half_life_days),
        k=float(k),
        league_logit=league_logit,
        home_dev=home_dev,
        away_dev=away_dev,
        n_home=n_home,
        n_away=n_away,
        home_hits=home_hits,
        home_counts=home_counts,
        away_hits=away_hits,
        away_counts=away_counts,
        league_counts=applicable.sum(axis=0),
    )
