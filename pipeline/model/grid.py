"""Exact outcome probabilities from a half-by-half Poisson goal grid.

Every registry outcome (combos included) is evaluated on one consistent grid, so
probabilities within a group are additive by construction. The grid assigns mass
to each (first half, second half) score pair; FT is the sum of the halves and HT
is the first half, so HT/FT and second-half outcomes cannot contradict each other.
"""
from __future__ import annotations

import math

import numpy as np

from ..outcomes import OUTCOMES

# Goals per half are truncated at 7 (P(8+ in a half) is below 1e-6 for our lambdas).
MAX_GOALS_PER_HALF = 7
N_HALF = MAX_GOALS_PER_HALF + 1
N_CELLS = N_HALF ** 4
FT_GRID_SIZE = 15

_K = np.arange(N_HALF, dtype=np.float64)
_FACT = np.array([math.factorial(int(k)) for k in range(max(N_HALF, FT_GRID_SIZE))], dtype=np.float64)


def poisson_pmf(lam: float, size: int = N_HALF) -> np.ndarray:
    lam = float(max(lam, 1e-6))
    k = np.arange(size, dtype=np.float64)
    return np.exp(-lam) * (lam ** k) / _FACT[:size]


def _tau(g: np.ndarray, lh: float, la: float, rho: float) -> np.ndarray:
    """Dixon-Coles low-score correction on the (0,0), (0,1), (1,0), (1,1) cells."""
    if rho:
        g[0, 0] *= max(1e-6, 1.0 - lh * la * rho)
        g[0, 1] *= max(1e-6, 1.0 + lh * rho)
        g[1, 0] *= max(1e-6, 1.0 + la * rho)
        g[1, 1] *= max(1e-6, 1.0 - rho)
    return g


def half_grid(lh: float, la: float, rho: float) -> np.ndarray:
    g = _tau(np.outer(poisson_pmf(lh), poisson_pmf(la)), lh, la, rho)
    return g / g.sum()


def _ft_grid(lh: float, la: float, rho: float) -> np.ndarray:
    g = _tau(np.outer(poisson_pmf(lh, FT_GRID_SIZE), poisson_pmf(la, FT_GRID_SIZE)), lh, la, rho)
    return g / g.sum()


def _build_outcome_mask() -> np.ndarray:
    mask = np.zeros((N_CELLS, len(OUTCOMES)), dtype=np.float32)
    for h1 in range(N_HALF):
        for a1 in range(N_HALF):
            for h2 in range(N_HALF):
                for a2 in range(N_HALF):
                    index = (((h1 * N_HALF) + a1) * N_HALF + h2) * N_HALF + a2
                    fthg, ftag = h1 + h2, a1 + a2
                    for position, outcome in enumerate(OUTCOMES):
                        mask[index, position] = 1.0 if outcome.fn(fthg, ftag, h1, a1) else 0.0
    return mask


def _build_anchor_mask() -> np.ndarray:
    """[home win, draw, away win, over 2.5] for the same cell ordering."""
    mask = np.zeros((N_CELLS, 4), dtype=np.float32)
    for h1 in range(N_HALF):
        for a1 in range(N_HALF):
            for h2 in range(N_HALF):
                for a2 in range(N_HALF):
                    index = (((h1 * N_HALF) + a1) * N_HALF + h2) * N_HALF + a2
                    fthg, ftag = h1 + h2, a1 + a2
                    mask[index, 0] = 1.0 if fthg > ftag else 0.0
                    mask[index, 1] = 1.0 if fthg == ftag else 0.0
                    mask[index, 2] = 1.0 if fthg < ftag else 0.0
                    mask[index, 3] = 1.0 if fthg + ftag >= 3 else 0.0
    return mask


OUTCOME_MASK = _build_outcome_mask()
ANCHOR_MASK = _build_anchor_mask()


def joint_vector(lh1: float, la1: float, lh2: float, la2: float, rho: float = -0.05) -> np.ndarray:
    """Flat joint distribution over (h1, a1, h2, a2) in grid ordering."""
    g1 = half_grid(lh1, la1, rho)
    g2 = half_grid(lh2, la2, rho)
    return np.outer(g1.ravel(), g2.ravel()).ravel()


def outcome_probabilities(lh1: float, la1: float, lh2: float, la2: float, rho: float = -0.05) -> np.ndarray:
    """Probability of every registry outcome, in OUTCOMES order."""
    return joint_vector(lh1, la1, lh2, la2, rho) @ OUTCOME_MASK


def ft_aggregates(lh: float, la: float, rho: float = -0.05) -> tuple[float, float, float, float]:
    """Cheap (home, draw, away, over 2.5) for anchoring; ignores the half split."""
    g = _ft_grid(lh, la, rho)
    home = float(np.tril(g, -1).sum())
    away = float(np.triu(g, 1).sum())
    draw = float(np.trace(g))
    totals = np.add.outer(np.arange(FT_GRID_SIZE), np.arange(FT_GRID_SIZE))
    over = float(g[totals >= 3].sum())
    return home, draw, away, over


def over_probability(total_mean: float) -> float:
    """P(3+ goals) for a Poisson total — exact and monotone in the mean."""
    lam = max(total_mean, 1e-6)
    return float(1.0 - math.exp(-lam) * (1.0 + lam + lam * lam / 2.0))


def solve_total(target_over: float) -> float:
    """Invert over_probability for the goal-total mean."""
    target = min(max(target_over, 0.02), 0.98)
    low, high = 0.3, 9.0
    for _ in range(40):
        mid = (low + high) / 2.0
        if over_probability(mid) < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def solve_split(total_mean: float, target_home: float, rho: float = -0.05) -> float:
    """Home share of the goal total that matches the target home-win probability."""
    target = min(max(target_home, 0.02), 0.95)
    low, high = 0.05, 0.95
    for _ in range(18):
        mid = (low + high) / 2.0
        home, _draw, _away, _over = ft_aggregates(total_mean * mid, total_mean * (1 - mid), rho)
        if home < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0
