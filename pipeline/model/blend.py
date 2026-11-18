"""Blending: per-group logistic stacking of the counts and goals engines, then
Platt calibration fitted on held-out seasons.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

from ..outcomes import OUTCOMES
from .counts_engine import logit, sigmoid

REGULARISATION = 1e-3
PRIOR = np.array([1.0, 1.0, 0.0])

GROUP_OF_OUTCOME = [outcome.group for outcome in OUTCOMES]
GROUP_NAMES = list(dict.fromkeys(GROUP_OF_OUTCOME))
GROUP_COLUMNS = {group: [i for i, g in enumerate(GROUP_OF_OUTCOME) if g == group] for group in GROUP_NAMES}


def _bce(target: np.ndarray, label: np.ndarray) -> float:
    return float(np.mean(np.logaddexp(0.0, target) - label * target))


def fit_stack(
    counts_p: np.ndarray,
    goals_p: np.ndarray,
    labels: np.ndarray,
) -> dict[str, np.ndarray]:
    """One logistic stack [logit counts, logit goals, intercept] per outcome group."""
    z_counts = logit(counts_p)
    z_goals = logit(goals_p)
    weights: dict[str, np.ndarray] = {}

    for group in GROUP_NAMES:
        columns = GROUP_COLUMNS[group]
        x = np.column_stack([z_counts[:, columns].ravel(), z_goals[:, columns].ravel()])
        x = np.column_stack([x, np.ones(x.shape[0])])
        y = labels[:, columns].ravel().astype(np.float64)

        def objective(w: np.ndarray) -> float:
            return _bce(x @ w, y) + REGULARISATION * float(np.sum((w - PRIOR) ** 2))

        result = minimize(objective, PRIOR.copy(), method="L-BFGS-B")
        weights[group] = result.x

    return weights


def fit_platt(stacked_p: np.ndarray, labels: np.ndarray) -> dict[str, tuple[float, float]]:
    """Per-group Platt scaling: sigmoid(a * logit(p) + b) on held-out seasons."""
    z = logit(stacked_p)
    parameters: dict[str, tuple[float, float]] = {}

    for group in GROUP_NAMES:
        columns = GROUP_COLUMNS[group]
        zz = z[:, columns].ravel()
        y = labels[:, columns].ravel().astype(np.float64)

        def objective(params: np.ndarray) -> float:
            a, b = params
            return _bce(a * zz + b, y)

        result = minimize(
            objective,
            np.array([1.0, 0.0]),
            method="L-BFGS-B",
            bounds=[(0.05, 5.0), (-3.0, 3.0)],
        )
        a, b = result.x
        parameters[group] = (float(a), float(b))

    return parameters


@dataclass(slots=True)
class Blend:
    stack: dict[str, np.ndarray]
    platt: dict[str, tuple[float, float]]
    live: dict[str, str] = field(default_factory=dict)  # group -> base|counts|goals|odds|full

    def stack_probabilities(self, counts_p: np.ndarray, goals_p: np.ndarray) -> np.ndarray:
        z_counts = logit(counts_p)
        z_goals = logit(goals_p)
        out = np.empty_like(counts_p)
        for group in GROUP_NAMES:
            columns = GROUP_COLUMNS[group]
            w = self.stack[group]
            out[:, columns] = sigmoid(w[0] * z_counts[:, columns] + w[1] * z_goals[:, columns] + w[2])
        return out

    def calibrate(self, probabilities: np.ndarray) -> np.ndarray:
        out = probabilities.copy()
        z = logit(probabilities)
        for group in GROUP_NAMES:
            a, b = self.platt[group]
            columns = GROUP_COLUMNS[group]
            out[:, columns] = sigmoid(a * z[:, columns] + b)
        return out

    def apply(
        self,
        base: np.ndarray,
        counts: np.ndarray,
        goals: np.ndarray,
        odds: np.ndarray,
    ) -> np.ndarray:
        """Per group, use whichever component the backtest kept."""
        sources = {"base": base, "counts": counts, "goals": goals, "odds": odds}
        modes = {group: self.live.get(group, "full") for group in GROUP_NAMES}
        if "full" in modes.values():
            sources["full"] = self.calibrate(self.stack_probabilities(counts, odds))
        out = np.empty_like(counts)
        for group, columns in GROUP_COLUMNS.items():
            out[:, columns] = sources[modes[group]][:, columns]
        return out
