"""Pre-registration of ticket-construction-v3, MEL-v1 and the forward protocol.

This file is the durable contract. Any parameter change must create a new
version and a new forward record; existing audits are hypothesis generation,
not an untouched holdout. Construction-v3 + MEL-v1 is a separate forward
evaluation from the earlier construction-v2 record.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import bankroll, proposed_tickets, ticket_construction

SCHEMA_VERSION = 1
ALPHA_ONE_SIDED = 0.05
POWER = 0.80
MEANINGFUL_ROI_EQUIVALENT = 0.02
MEANINGFUL_LOG_GROWTH = math.log(1.0 + MEANINGFUL_ROI_EQUIVALENT)
INCONCLUSIVE_ROUNDS = 156
SAFETY_DRAWDOWN = 0.20
RUIN_THRESHOLD = 0.50
RUIN_HORIZON = 52
RUIN_UPPER_LIMIT = 0.05
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20261025


def build() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "construction_version": ticket_construction.CONSTRUCTION_VERSION_V3,
        "policy_version": bankroll.POLICY_VERSION,
        "proposal_schema_version": proposed_tickets.SCHEMA_VERSION,
        "activation_date": proposed_tickets.PROPOSAL_ACTIVATION_DATE,
        "evaluation_id": proposed_tickets.EVALUATION_ID,
        "evaluation": {
            "id": proposed_tickets.EVALUATION_ID,
            "construction_version": ticket_construction.CONSTRUCTION_VERSION_V3,
            "policy_version": bankroll.POLICY_VERSION,
            "start_rule": "first eligible round with a frozen schema-3 proposal; pre-existing schema-1/2 proposals stay frozen and are not pooled",
            "pooling_rule": "v2 and v3 performance records are never pooled",
            "unsupported_same_fixture_rule": "flat proposals are retained; new MEL exposure is zero with reason unsupported same-fixture dependence",
        },
        "ticket_construction": {
            "specs": ticket_construction.SPECS,
            "preferred_min_individual_odds": ticket_construction.PREFERRED_MIN_INDIVIDUAL,
            "individual_price_tiers": [
                {"tier": name, "minimum_odds": minimum, "message": message}
                for name, minimum, message in ticket_construction.PRICE_TIERS
            ],
            "exact_combination_cap": ticket_construction.EXACT_COMBINATION_CAP,
            "bounded_dp": {"log_odds_bucket": ticket_construction.DP_LOG_BUCKET,
                            "keep_per_state": ticket_construction.DP_KEEP_PER_STATE},
            "ranking": "combined pc, model_EV, fewer legs; Around 3.00 then log-distance to 3.00; deterministic identity",
            "overlap": "soft no-fixture-reuse, then exact shared legs only, then recorded relaxation; no fixture in all three when avoidable",
            "fallback_labels": ["in preferred band", "outside preferred band",
                                 "below meaningful payout floor; highest available payout",
                                 "no combined-odds target"],
        },
        "mel": {
            "total_stake_formula": "A = max(0, B - U); m = max(0, 1 - D/0.20); S = A * (0.0025 + 0.0175*m)",
            "drawdown_scale": bankroll.MEL_DRAWDOWN_SCALE,
            "base_fraction": bankroll.MEL_BASE_FRACTION,
            "slope": bankroll.MEL_SLOPE,
            "residual_quantile": bankroll.MEL_SHIFT_QUANTILE,
            "residual_fallback": bankroll.MEL_FALLBACK_SHIFT,
            "minimum_residual_dates": bankroll.MEL_MIN_RESIDUAL_DATES,
            "stress_shift": bankroll.MEL_STRESS_SHIFT,
            "q_formula": "q = clamp(pc + cohort_shift, 0.001, 0.999); cohort = market group x 10-point pc band",
            "scenarios": "binary pre-match win/loss over unique legs; cross-fixture conditional independence; exact shared legs reused once; probabilities sum to one",
            "ticket_net": "odds - 1 on a win, -1 on a loss",
            "objective": "maximise sum(scenario probability * log(A + scenario net . stakes))",
            "constraints": "SLSQP; sum(stakes) = S; 0 <= stake <= S/2 (single ticket: S); positive wealth",
            "stress": "simultaneous q - 0.05 re-solve; descriptive, not a bound",
        },
        "comparators": {
            "flat": {"shares": list(bankroll.FLAT_SHARES), "basis": "50/30/20 of the round stake"},
            "fixed_fractional": {"fraction_of_available": bankroll.FIXED_FRACTIONAL_FRACTION},
            "no_forced_kelly": {"fraction": bankroll.NO_FORCED_KELLY_FRACTION,
                                  "ticket_cap": bankroll.NO_FORCED_TICKET_CAP,
                                  "total_cap": bankroll.NO_FORCED_TOTAL_CAP,
                                  "drawdown_multiplier": True, "may_return_zero": True},
            "probability_weighted": "S allocated in proportion to combined ticket probability",
            "minimum_variance": "SLSQP on the joint scenario covariance; duplicate/singular tickets handled under constraints",
            "martingale": {"base": bankroll.MARTINGALE_BASE, "cap": bankroll.MARTINGALE_CAP,
                            "uncapped": "reported for diagnosis only"},
        },
        "settlement": {
            "rules": "any lost leg 0; all legs void 1; mixed landed/void the product of actual prices for landed legs only",
            "round_atomic": "bankroll, peak and drawdown advance once after every available ticket in a round is terminal",
            "unresolved_exposure": "the whole round stake is reserved until then",
        },
        "primary_comparison": ["flat", "mel"],
        "exploratory": ["fixed_fractional", "no_forced_kelly", "probability_weighted",
                          "minimum_variance", "martingale_capped", "martingale_uncapped"],
        "protocol": {
            "alpha_one_sided": ALPHA_ONE_SIDED,
            "power": POWER,
            "meaningful_roi_equivalent": MEANINGFUL_ROI_EQUIVALENT,
            "meaningful_log_growth": round(MEANINGFUL_LOG_GROWTH, 8),
            "n_star_rule": "ceil(((z_0.95 + z_0.80) * sd(round log growth) / log(1.02))**2)",
            "n_star_unavailable": "report N* unavailable rather than invent a value",
            "evidence_rule": "at least N* settled playable rounds and the whole-round bootstrap lower 95% bound on mean log growth above zero",
            "inconclusive_rule": f"report inconclusive after {INCONCLUSIVE_ROUNDS} settled playable rounds without the evidence rule",
            "no_early_efficacy_stopping": True,
            "safety_review_drawdown": SAFETY_DRAWDOWN,
            "safety_review_identity_failure": True,
            "stop_adaptive_rule": f"upper 95% estimate of losing {RUIN_THRESHOLD:.0%} within {RUIN_HORIZON} rounds above {RUIN_UPPER_LIMIT:.0%}, or the owner's loss budget is breached",
            "bootstrap": {"unit": "whole round date", "resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED},
        },
        "research_note": "Existing audits are hypothesis generation, not an untouched holdout. No retrospective fair-odds substitution is used in actual-price results.",
        "version_rule": "Any formula, parameter, scenario or stopping-rule change creates a new version and a new forward record.",
    }


def write(web_dir: Path) -> dict:
    payload = build()
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "preregistration.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8"
    )
    return payload
