"""Walk-forward backtest, component ablation and per-group decisions.

For every target season 2019-20..2025-26 the components are fitted only on earlier
seasons, the stack is fitted on the season before the target and the Platt mapping is
fitted on that same held-out season. Nothing in a prediction can see its own season.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..outcomes import OUTCOMES
from . import blend as blend_module
from .counts_engine import fit as fit_counts, logit, sigmoid
from .data import MatchArrays, build_arrays, day_number, subset
from .goals_engine import fit as fit_goals

BACKTEST_YEARS = tuple(range(2019, 2026))
COMPONENTS = ("base", "counts", "goals", "odds", "full")

BIN_LOW = 0.30
BIN_WIDTH = 0.05
BIN_COUNT = 12
BIN_EDGES = [round(BIN_LOW + BIN_WIDTH * i, 2) for i in range(BIN_COUNT)]

HALF_LIFE_GRID = (365.0, 730.0, 1095.0)
K_GRID = (5.0, 10.0, 20.0)
TUNING_OUTCOMES = ("ft_1", "ht_x", "tg_3plus", "tg_2plus", "btts_yes", "c1")
TUNING_OUTCOME_INDEX = {outcome.id: index for index, outcome in enumerate(OUTCOMES)}


@dataclass(slots=True)
class DivisionData:
    code: str
    matches: list
    season_starts: np.ndarray
    arrays: MatchArrays


def prepare(code: str, matches: list, season_of_match) -> DivisionData:
    ordered = sorted(matches, key=lambda m: (m.date, m.home, m.away))
    starts = np.array([season_of_match(m) for m in ordered], dtype=np.int32)
    return DivisionData(code=code, matches=ordered, season_starts=starts, arrays=build_arrays(ordered))


@dataclass(slots=True)
class Board:
    brier: dict[str, np.ndarray] = field(default_factory=lambda: {c: np.zeros(len(OUTCOMES)) for c in COMPONENTS})
    logloss: dict[str, np.ndarray] = field(default_factory=lambda: {c: np.zeros(len(OUTCOMES)) for c in COMPONENTS})
    n: np.ndarray = field(default_factory=lambda: np.zeros(len(OUTCOMES)))
    bins: dict[str, dict[str, dict[str, list]]] = field(
        default_factory=lambda: {
            source: {group: {"n": [0] * BIN_COUNT, "hits": [0] * BIN_COUNT} for group in blend_module.GROUP_NAMES}
            for source in ("full", "odds")
        }
    )
    fixtures: int = 0

    def accumulate(self, component: str, probabilities: np.ndarray, labels: np.ndarray, applicable: np.ndarray) -> None:
        p = np.clip(probabilities, 1e-6, 1.0 - 1e-6)
        self.brier[component] += ((p - labels) ** 2 * applicable).sum(axis=0)
        self.logloss[component] += (
            -(labels * np.log(p) + (1.0 - labels) * np.log(1.0 - p)) * applicable
        ).sum(axis=0)

    def accumulate_bins(self, source: str, probabilities: np.ndarray, labels: np.ndarray, applicable: np.ndarray) -> None:
        index = np.floor((probabilities - BIN_LOW) / BIN_WIDTH).astype(np.int32)
        valid = (index >= 0) & (index < BIN_COUNT) & (applicable > 0)
        for group, columns in blend_module.GROUP_COLUMNS.items():
            for position in range(BIN_COUNT):
                mask = valid[:, columns] & (index[:, columns] == position)
                if not mask.any():
                    continue
                self.bins[source][group]["n"][position] += int(mask.sum())
                self.bins[source][group]["hits"][position] += int((labels[:, columns] * mask).sum())


def _predict_components(counts, goals, part: MatchArrays) -> dict[str, np.ndarray]:
    base = np.repeat(counts.league_rates()[None, :], len(part), axis=0)
    return {
        "base": base,
        "counts": counts.probabilities(part.home, part.away),
        "goals": goals.probabilities(part.home, part.away, part.odds, use_odds=False),
        "odds": goals.probabilities(part.home, part.away, part.odds, use_odds=True),
    }


def tune_hyperparameters(divisions: list[DivisionData], tune_year: int = 2019) -> dict:
    """Grid-search the recency half-life and shrinkage k on the pre-backtest seasons."""
    results = []
    for half_life in HALF_LIFE_GRID:
        for k in K_GRID:
            logloss = 0.0
            samples = 0.0
            for division in divisions:
                arrays = division.arrays
                train_idx = np.where(division.season_starts < tune_year)[0]
                test_idx = np.where(division.season_starts == tune_year)[0]
                if len(train_idx) == 0 or len(test_idx) == 0:
                    continue
                train = subset(arrays, train_idx)
                test = subset(arrays, test_idx)
                reference = float(test.dates.min())
                counts = fit_counts(train, reference, half_life, k)
                probabilities = np.clip(counts.probabilities(test.home, test.away), 1e-6, 1 - 1e-6)
                labels = test.hits.astype(np.float64)
                applicable = test.applicable.astype(np.float64)
                for outcome_id in TUNING_OUTCOMES:
                    column = TUNING_OUTCOME_INDEX[outcome_id]
                    mask = applicable[:, column]
                    if mask.sum() == 0:
                        continue
                    p = probabilities[:, column]
                    logloss += float(
                        (-(labels[:, column] * np.log(p) + (1 - labels[:, column]) * np.log(1 - p)) * mask).sum()
                    )
                    samples += float(mask.sum())
            results.append(
                {"half_life_days": half_life, "k": k, "logloss": round(logloss / samples, 6) if samples else None}
            )
    best = min((row for row in results if row["logloss"] is not None), key=lambda row: row["logloss"])
    return {"best": best, "grid": results}


def run_division(division: DivisionData, half_life: float, k: float, board: Board) -> None:
    arrays = division.arrays
    labels_all = arrays.hits.astype(np.float64)
    applicable_all = arrays.applicable.astype(np.float64)

    for target in BACKTEST_YEARS:
        train_idx = np.where(division.season_starts < target)[0]
        previous_idx = np.where(division.season_starts < target - 1)[0]
        calib_idx = np.where(division.season_starts == target - 1)[0]
        test_idx = np.where(division.season_starts == target)[0]
        if min(len(train_idx), len(previous_idx), len(calib_idx), len(test_idx)) == 0:
            continue

        train = subset(arrays, train_idx)
        previous = subset(arrays, previous_idx)
        calib = subset(arrays, calib_idx)
        test = subset(arrays, test_idx)

        counts_previous = fit_counts(previous, float(calib.dates.min()), half_life, k)
        goals_previous = fit_goals(previous, float(calib.dates.min()), half_life)
        calib_parts = _predict_components(counts_previous, goals_previous, calib)

        # Stack on the two seasons before the target, each predicted by components that
        # never saw it. Platt is fitted on the most recent held-out season only.
        pair_counts = [calib_parts["counts"]]
        pair_goals = [calib_parts["odds"]]
        pair_labels = [calib.hits.astype(np.float64)]

        older_test_idx = np.where(division.season_starts == target - 2)[0]
        older_train_idx = np.where(division.season_starts < target - 2)[0]
        if len(older_test_idx) and len(older_train_idx):
            older_train = subset(arrays, older_train_idx)
            older_test = subset(arrays, older_test_idx)
            counts_older = fit_counts(older_train, float(older_test.dates.min()), half_life, k)
            goals_older = fit_goals(older_train, float(older_test.dates.min()), half_life)
            older_parts = _predict_components(counts_older, goals_older, older_test)
            pair_counts.insert(0, older_parts["counts"])
            pair_goals.insert(0, older_parts["odds"])
            pair_labels.insert(0, labels_all[older_test_idx])

        stack = blend_module.fit_stack(
            np.vstack(pair_counts), np.vstack(pair_goals), np.vstack(pair_labels)
        )
        blender = blend_module.Blend(stack=stack, platt={})
        platt = blend_module.fit_platt(
            blender.stack_probabilities(pair_counts[-1], pair_goals[-1]), pair_labels[-1]
        )
        blender.platt = platt

        counts_train = fit_counts(train, float(test.dates.min()), half_life, k)
        goals_train = fit_goals(train, float(test.dates.min()), half_life)
        parts = _predict_components(counts_train, goals_train, test)
        full = blender.apply(parts["base"], parts["counts"], parts["goals"], parts["odds"])

        labels = labels_all[test_idx]
        applicable = applicable_all[test_idx]
        for component in COMPONENTS:
            probabilities = full if component == "full" else parts[component]
            board.accumulate(component, probabilities, labels, applicable)
        board.n += applicable.sum(axis=0)
        board.accumulate_bins("full", full, labels, applicable)
        board.accumulate_bins("odds", parts["odds"], labels, applicable)
        board.fixtures += len(test_idx)


def run(divisions: list[DivisionData], half_life: float, k: float, progress=None) -> Board:
    board = Board()
    for division in divisions:
        run_division(division, half_life, k, board)
        if progress:
            progress(division.code, board.fixtures)
    return board


def group_summary(board: Board) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for group, columns in blend_module.GROUP_COLUMNS.items():
        samples = float(board.n[columns].sum())
        entry: dict[str, dict] = {}
        for component in COMPONENTS:
            entry[component] = {
                "brier": round(float(board.brier[component][columns].sum() / samples), 6) if samples else None,
                "logloss": round(float(board.logloss[component][columns].sum() / samples), 6) if samples else None,
            }
        entry["n"] = int(samples)
        summary[group] = entry
    return summary


def outcome_summary(board: Board) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for index, outcome in enumerate(OUTCOMES):
        n = float(board.n[index])
        entry = {"n": int(n)}
        for component in COMPONENTS:
            entry[component] = round(float(board.brier[component][index] / n), 6) if n else None
        summary[outcome.id] = entry
    return summary


def bin_table(board: Board, source: str = "full") -> dict[str, dict]:
    table: dict[str, dict] = {}
    for group, bins in board.bins[source].items():
        rows = []
        for position in range(BIN_COUNT):
            low = BIN_LOW + BIN_WIDTH * position
            high = low + BIN_WIDTH
            n = bins["n"][position]
            hits = bins["hits"][position]
            rows.append(
                {
                    "bin": f"{int(low * 100)}-{int(high * 100)}",
                    "shown": round((low + high) / 2.0, 4),
                    "n": n,
                    "hits": hits,
                    "landed": round(hits / n, 4) if n else None,
                }
            )
        table[group] = {"bins": rows}
    return table


def selected_bin_table(board: Board, groups: dict[str, dict]) -> dict[str, dict]:
    """Calibration bins for whichever component each group's live model uses."""
    full = bin_table(board, "full")
    odds = bin_table(board, "odds")
    selected: dict[str, dict] = {}
    for group in blend_module.GROUP_NAMES:
        uses_full = groups.get(group, {}).get("live_component") == "full"
        selected[group] = (full if uses_full else odds)[group]
    return selected


def build_decisions(board: Board, hyperparameters: dict) -> dict:
    summary = group_summary(board)
    per_outcome = outcome_summary(board)
    groups: dict[str, dict] = {}

    for group, entry in summary.items():
        base = entry["base"]["brier"]
        counts = entry["counts"]["brier"]
        goals = entry["goals"]["brier"]
        odds = entry["odds"]["brier"]
        full = entry["full"]["brier"]

        keep_counts = counts is not None and base is not None and counts < base
        reference = counts if keep_counts else base
        keep_goals = goals is not None and reference is not None and goals < reference
        keep_odds = odds is not None and goals is not None and odds < goals
        keep_calibration = full is not None and odds is not None and full < odds

        if not keep_calibration:
            best = min(
                (
                    (name, entry[name]["brier"])
                    for name in ("base", "counts", "goals", "odds")
                    if entry[name]["brier"] is not None
                ),
                key=lambda item: item[1],
            )[0]
        else:
            best = "full"

        groups[group] = {
            "brier": {component: entry[component]["brier"] for component in COMPONENTS},
            "logloss": {component: entry[component]["logloss"] for component in COMPONENTS},
            "keep_counts": bool(keep_counts),
            "keep_goals": bool(keep_goals),
            "keep_odds": bool(keep_odds),
            "keep_calibration": bool(keep_calibration),
            "live_component": best,
            "n": entry["n"],
        }

    worse = [
        outcome_id
        for outcome_id, entry in per_outcome.items()
        if entry["full"] is not None and entry["base"] is not None and entry["full"] > entry["base"]
    ]

    return {
        "backtest_seasons": [f"{year}-{(year + 1) % 100:02d}" for year in BACKTEST_YEARS],
        "fixtures": board.fixtures,
        "hyperparameters": hyperparameters,
        "groups": groups,
        "outcomes": per_outcome,
        "full_worse_than_base": worse,
        "full_worse_than_base_count": len(worse),
    }
