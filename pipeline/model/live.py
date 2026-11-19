"""Live predictor: fitted on everything strictly before a cutoff date."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

from . import blend as blend_module
from .counts_engine import fit as fit_counts
from .data import build_arrays, subset
from .empirical import Empirical, build as build_empirical
from .goals_engine import fit as fit_goals
from .grid import joint_vector

from .. import markets as market_module


def season_start_of(match) -> int:
    return int(str(match.season).split("-")[0])


@dataclass(slots=True)
class Predictor:
    counts: object
    goals: object
    blender: blend_module.Blend
    team_index: dict[str, int]
    unknown_index: int
    cutoff: dt.date
    trained_matches: int
    empirical: Empirical

    def probabilities(self, home: list[str], away: list[str], odds: list[dict]) -> dict[str, np.ndarray]:
        home_index = np.array([self.team_index.get(name, self.unknown_index) for name in home], dtype=np.int32)
        away_index = np.array([self.team_index.get(name, self.unknown_index) for name in away], dtype=np.int32)
        base = np.repeat(self.counts.league_rates()[None, :], len(home), axis=0)
        counts_p = self.counts.probabilities(home_index, away_index)
        goals_p = self.goals.probabilities(home_index, away_index, odds, use_odds=False)
        odds_p = self.goals.probabilities(home_index, away_index, odds, use_odds=True)
        full = self.blender.apply(base, counts_p, goals_p, odds_p)
        return {
            "base": base,
            "counts": counts_p,
            "goals": goals_p,
            "odds": odds_p,
            "full": full,
            "n_home": self.counts.n_home[home_index],
            "n_away": self.counts.n_away[away_index],
        }


    def market_probabilities(self, home: list[str], away: list[str], odds: list[dict]):
        """(fixtures, markets) grid probabilities plus the league baseline vector."""
        home_index = np.array([self.team_index.get(name, self.unknown_index) for name in home], dtype=np.int32)
        away_index = np.array([self.team_index.get(name, self.unknown_index) for name in away], dtype=np.int32)
        home_lambda, away_lambda = self.goals.anchored_lambdas(home_index, away_index, odds, use_odds=True)

        out = np.zeros((len(home), len(market_module.MARKETS)))
        for row in range(len(home)):
            lh = float(home_lambda[row])
            la = float(away_lambda[row])
            joint = joint_vector(
                lh * self.goals.share_home,
                la * self.goals.share_away,
                lh * (1.0 - self.goals.share_home),
                la * (1.0 - self.goals.share_away),
                self.goals.rho,
            )
            out[row] = market_module.probabilities(joint)
        return out, self.market_baseline()

    def market_baseline(self):
        """What an average match in this league looks like, market by market."""
        lh = float(self.goals.league_home)
        la = float(self.goals.league_away)
        joint = joint_vector(
            lh * self.goals.share_home,
            la * self.goals.share_away,
            lh * (1.0 - self.goals.share_home),
            la * (1.0 - self.goals.share_away),
            self.goals.rho,
        )
        return market_module.probabilities(joint)


def _pad_counts(model) -> int:
    """Append a zero-effect row so unseen teams can still be predicted."""
    model.home_dev = np.vstack([model.home_dev, np.zeros((1, model.home_dev.shape[1]))])
    model.away_dev = np.vstack([model.away_dev, np.zeros((1, model.away_dev.shape[1]))])
    model.home_hits = np.vstack([model.home_hits, np.zeros((1, model.home_hits.shape[1]))])
    model.away_hits = np.vstack([model.away_hits, np.zeros((1, model.away_hits.shape[1]))])
    model.n_home = np.append(model.n_home, 0.0)
    model.n_away = np.append(model.n_away, 0.0)
    model.home_counts = np.append(model.home_counts, 0.0)
    model.away_counts = np.append(model.away_counts, 0.0)
    return model.home_dev.shape[0] - 1


def build_predictor(
    matches: list,
    cutoff: dt.date,
    half_life: float,
    k: float,
    decisions: dict | None = None,
) -> Predictor:
    train = [match for match in matches if match.date < cutoff]
    if not train:
        raise ValueError("no matches before the cutoff date")

    arrays = build_arrays(train)
    season_starts = np.array([season_start_of(match) for match in train], dtype=np.int32)
    reference = float((cutoff - dt.date(2000, 1, 1)).days)

    counts = fit_counts(arrays, reference, half_life, k)
    goals = fit_goals(arrays, reference, half_life)
    empirical = build_empirical(arrays, reference, half_life)

    latest = int(season_starts.max())
    calib_mask = np.where(season_starts == latest)[0]
    previous_mask = np.where(season_starts < latest)[0]

    fallback: dict[str, str] = {}
    if decisions:
        for group, entry in decisions.get("groups", {}).items():
            component = entry.get("live_component")
            if component:
                fallback[group] = component

    if len(calib_mask) > 0 and len(previous_mask) > 0:
        calib = subset(arrays, calib_mask)
        previous = subset(arrays, previous_mask)
        counts_prev = fit_counts(previous, float(calib.dates.min()), half_life, k)
        goals_prev = fit_goals(previous, float(calib.dates.min()), half_life)
        calib_counts = counts_prev.probabilities(calib.home, calib.away)
        calib_odds = goals_prev.probabilities(calib.home, calib.away, calib.odds, use_odds=True)
        stack = blend_module.fit_stack(calib_counts, calib_odds, calib.hits.astype(np.float64))
        blender = blend_module.Blend(stack=stack, platt={})
        stacked = blender.stack_probabilities(calib_counts, calib_odds)
        blender.platt = blend_module.fit_platt(stacked, calib.hits.astype(np.float64))
    else:
        prior = {group: np.array([1.0, 1.0, 0.0]) for group in blend_module.GROUP_NAMES}
        identity = {group: (1.0, 0.0) for group in blend_module.GROUP_NAMES}
        blender = blend_module.Blend(stack=prior, platt=identity)

    blender.live = fallback

    unknown_index = _pad_counts(counts)
    empirical.home_rate = np.vstack([empirical.home_rate, np.zeros((1, empirical.home_rate.shape[1]))])
    empirical.away_rate = np.vstack([empirical.away_rate, np.zeros((1, empirical.away_rate.shape[1]))])
    empirical.home_n = np.append(empirical.home_n, 0.0)
    empirical.away_n = np.append(empirical.away_n, 0.0)
    goals.att = np.append(goals.att, 1.0)
    goals.dfn = np.append(goals.dfn, 1.0)
    goals.played = np.append(goals.played, 0.0)

    team_index = dict(arrays.team_index)
    team_index["\u0000unknown"] = unknown_index

    return Predictor(
        counts=counts,
        goals=goals,
        blender=blender,
        team_index=team_index,
        unknown_index=unknown_index,
        cutoff=cutoff,
        trained_matches=len(train),
        empirical=empirical,
    )
