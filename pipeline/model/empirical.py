"""Empirical rates for every market, from real past matches before a cutoff.

Matches are deduplicated by score signature before any predicate runs, so a full
history costs a few thousand evaluations instead of tens of millions. Rates are
recency-weighted (half-life from the tuned decisions) and n is the raw number of
matches that could answer the market (half-time markets exclude rows without a
half-time score).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..markets import MARKETS
from .data import MatchArrays, recency_weights, team_sums

SignatureKey = tuple[int, int, int, int]
_SIGNATURE_CACHE: dict[SignatureKey, tuple[np.ndarray, np.ndarray]] = {}


def signature_hits(fthg: int, ftag: int, hthg: int | None, htag: int | None):
    key = (int(fthg), int(ftag), -1 if hthg is None else int(hthg), -1 if htag is None else int(htag))
    cached = _SIGNATURE_CACHE.get(key)
    if cached is not None:
        return cached

    size = len(MARKETS)
    hits = np.zeros(size, dtype=np.float32)
    applicable = np.zeros(size, dtype=np.float32)
    half_home, half_away = key[2], key[3]
    for position, market in enumerate(MARKETS):
        if market.needs_ht and (half_home < 0 or half_away < 0):
            continue
        applicable[position] = 1.0
        hits[position] = 1.0 if market.settle(key[0], key[1], max(half_home, 0), max(half_away, 0)) else 0.0
    cached = (hits, applicable)
    _SIGNATURE_CACHE[key] = cached
    return cached


@dataclass(slots=True)
class Empirical:
    league_rate: np.ndarray   # (markets,)
    league_n: np.ndarray      # (markets,) raw matches
    home_rate: np.ndarray     # (teams, markets)
    home_n: np.ndarray        # (teams,)
    away_rate: np.ndarray
    away_n: np.ndarray

    def rates_for(self, home_index: int, away_index: int):
        """(league rate, league n, home-at-home rate/n, away-away rate/n) for one fixture."""
        return (
            self.league_rate,
            self.league_n,
            self.home_rate[home_index],
            np.full(self.league_rate.shape, self.home_n[home_index]),
            self.away_rate[away_index],
            np.full(self.league_rate.shape, self.away_n[away_index]),
        )


def build(arrays: MatchArrays, reference_day: float, half_life_days: float) -> Empirical:
    count = len(arrays)
    size = len(MARKETS)
    n_teams = len(arrays.teams)

    hits = np.zeros((count, size), dtype=np.float32)
    applicable = np.zeros((count, size), dtype=np.float32)
    for row in range(count):
        hthg = None if np.isnan(arrays.hthg[row]) else int(arrays.hthg[row])
        htag = None if np.isnan(arrays.htag[row]) else int(arrays.htag[row])
        hits[row], applicable[row] = signature_hits(int(arrays.fthg[row]), int(arrays.ftag[row]), hthg, htag)

    weights = recency_weights(arrays.dates, reference_day, half_life_days).astype(np.float32)
    weighted_hits = weights[:, None] * hits
    weighted_n = weights[:, None] * applicable

    denominator = weighted_n.sum(axis=0)
    league_rate = np.where(denominator > 0, weighted_hits.sum(axis=0) / np.maximum(denominator, 1e-9), 0.0)
    league_n = applicable.sum(axis=0)

    home_rate = team_sums(arrays.home, weighted_hits, n_teams) / np.maximum(
        team_sums(arrays.home, weighted_n, n_teams), 1e-9
    )
    away_rate = team_sums(arrays.away, weighted_hits, n_teams) / np.maximum(
        team_sums(arrays.away, weighted_n, n_teams), 1e-9
    )
    home_n = team_sums(arrays.home, applicable, n_teams)[:, 0]
    away_n = team_sums(arrays.away, applicable, n_teams)[:, 0]

    home_rate[home_n <= 0] = 0.0
    away_rate[away_n <= 0] = 0.0

    return Empirical(
        league_rate=league_rate,
        league_n=league_n,
        home_rate=home_rate,
        home_n=home_n,
        away_rate=away_rate,
        away_n=away_n,
    )
