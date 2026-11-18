"""Stacking and calibration behaviour on synthetic data."""
from __future__ import annotations

import numpy as np
import pytest

from pipeline.model.blend import Blend, fit_platt, fit_stack
from pipeline.outcomes import OUTCOMES

SIZE = len(OUTCOMES)


def sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-value))


def log_loss(probabilities: np.ndarray, labels: np.ndarray) -> float:
    p = np.clip(probabilities, 1e-6, 1 - 1e-6)
    return float(np.mean(-(labels * np.log(p) + (1 - labels) * np.log(1 - p))))


def brier(probabilities: np.ndarray, labels: np.ndarray) -> float:
    return float(np.mean((probabilities - labels) ** 2))


def synthetic(seed: int = 11, n: int = 12000) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    signal = rng.normal(0, 1, n)
    truth = sigmoid(1.5 * signal - 0.2)
    labels = (rng.random(n) < truth).astype(np.float64)
    counts = sigmoid(0.8 * signal + rng.normal(0, 0.7, n))
    goals = sigmoid(1.1 * signal + rng.normal(0, 0.5, n))
    return labels, counts, goals, truth


def test_platt_calibration_reduces_log_loss() -> None:
    labels, counts, _goals, _truth = synthetic()
    raw = np.clip(counts, 0.01, 0.99)
    probabilities = np.repeat(raw[:, None], SIZE, axis=1)
    target = np.repeat(labels[:, None], SIZE, axis=1)

    parameters = fit_platt(probabilities, target)
    calibrated = Blend(stack={}, platt=parameters).calibrate(probabilities)

    assert log_loss(calibrated[:, 0], labels) < log_loss(raw, labels)
    assert (calibrated[:, 0] >= 0).all() and (calibrated[:, 0] <= 1).all()


def test_calibration_is_monotone() -> None:
    labels, counts, _goals, _truth = synthetic(seed=5)
    raw = np.clip(counts, 0.01, 0.99)
    probabilities = np.repeat(raw[:, None], SIZE, axis=1)
    target = np.repeat(labels[:, None], SIZE, axis=1)

    calibrated = Blend(stack={}, platt=fit_platt(probabilities, target)).calibrate(probabilities)[:, 0]
    order = np.argsort(raw)
    differences = np.diff(calibrated[order])
    assert (differences >= -1e-12).all()


def test_stacking_beats_each_engine_alone() -> None:
    labels, counts, goals, _truth = synthetic(seed=17)
    probabilities_counts = np.repeat(counts[:, None], SIZE, axis=1)
    probabilities_goals = np.repeat(goals[:, None], SIZE, axis=1)
    target = np.repeat(labels[:, None], SIZE, axis=1)

    stack = fit_stack(probabilities_counts, probabilities_goals, target)
    blended = Blend(stack=stack, platt={}).stack_probabilities(probabilities_counts, probabilities_goals)

    blended_brier = brier(blended[:, 0], labels)
    assert blended_brier < brier(counts, labels)
    assert blended_brier < brier(goals, labels)
    assert blended_brier < 0.24


def test_stack_weights_are_directional() -> None:
    labels, counts, goals, _truth = synthetic(seed=23)
    target = np.repeat(labels[:, None], SIZE, axis=1)
    stack = fit_stack(
        np.repeat(counts[:, None], SIZE, axis=1),
        np.repeat(goals[:, None], SIZE, axis=1),
        target,
    )
    for weights in stack.values():
        assert weights[0] > 0 and weights[1] > 0


def test_chosen_component_is_used_per_group() -> None:
    labels, counts, goals, _truth = synthetic(seed=31, n=200)
    probabilities = np.repeat(counts[:, None], SIZE, axis=1)
    other = np.repeat(goals[:, None], SIZE, axis=1)
    base = np.full_like(probabilities, 0.42)

    live = {group: "base" for group in group_names()}
    out = Blend(stack={}, platt={}, live=live).apply(base, probabilities, other, other)
    assert np.allclose(out, 0.42)

    live = {group: "counts" for group in group_names()}
    out = Blend(stack={}, platt={}, live=live).apply(base, probabilities, other, other)
    assert np.allclose(out, probabilities)


def group_names() -> list[str]:
    return list(dict.fromkeys(outcome.group for outcome in OUTCOMES))
