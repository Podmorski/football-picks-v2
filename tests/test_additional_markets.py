"""Research candidate definitions: grid, settlement, equivalence and catalogue."""
from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pytest

from pipeline.markets import MARKET_BY_ID, MARKET_GROUPS, MARKETS, result
from pipeline.mozzart.mapping import VALID_IDS
from pipeline.model import additional_markets as additional
from pipeline.model.additional_market_backtest import CandidateStats, GroupImpact
from pipeline.model.grid import N_CELLS, N_HALF

ROOT = Path(__file__).resolve().parents[1]
GRID = tuple(itertools.product(range(N_HALF), repeat=4))


def cells(market_id: str) -> set[tuple[int, int, int, int]]:
    spec = additional.CANDIDATE_BY_ID[market_id]
    return {
        (h1, a1, h2, a2) for h1, a1, h2, a2 in GRID
        if additional.settle_candidate(spec, h1 + h2, a1 + a2, h1, a1)
    }


def feasible(market_id: str) -> bool:
    return bool(cells(market_id))


def test_candidate_registry_is_research_only_and_uses_existing_groups() -> None:
    assert len(additional.CANDIDATES) == 23
    assert len(additional.CANDIDATE_BY_ID) == len(additional.REQUESTED_IDS) == 23
    assert set(additional.REQUESTED_IDS).isdisjoint(VALID_IDS)
    assert set(additional.REQUESTED_IDS).isdisjoint(MARKET_BY_ID)
    assert all(spec.group in MARKET_GROUPS for spec in additional.CANDIDATES)
    assert all(spec.group in {"Combos", "HT/FT"} for spec in additional.CANDIDATES)
    assert all(not spec.id.startswith("CORRECT_SCORE:") for spec in additional.CANDIDATES)
    assert len(MARKETS) == 178


def test_exhaustive_grid_support_and_probability_consistency() -> None:
    mask = additional.candidate_mask()
    assert mask.shape == (N_CELLS, len(additional.CANDIDATES))
    assert set(np.unique(mask)) <= {0.0, 1.0}
    assert all(feasible(candidate_id) for candidate_id in additional.REQUESTED_IDS)
    uniform = np.full(N_CELLS, 1.0 / N_CELLS)
    probabilities = additional.candidate_probabilities(uniform)
    assert probabilities.shape == (len(additional.CANDIDATES),)
    assert np.isfinite(probabilities).all()
    assert ((probabilities >= 0.0) & (probabilities <= 1.0)).all()
    expected = mask.sum(axis=0) / N_CELLS
    assert np.allclose(probabilities, expected)
    assert np.isclose(uniform.sum(), 1.0)


def test_every_candidate_settles_identically_on_the_same_grid_cells() -> None:
    for spec in additional.CANDIDATES:
        for h1, a1, h2, a2 in GRID:
            direct = bool(spec.market.settle(h1 + h2, a1 + a2, h1, a1))
            settled = additional.settle_candidate(spec, h1 + h2, a1 + a2, h1, a1)
            assert settled is direct


def test_four_htft_btts_candidates_are_exact_existing_market_duplicates() -> None:
    expected = {
        "HTFT_COMBO:1-X&gg": "HTFT:1-X",
        "HTFT_COMBO:1-2&gg": "HTFT:1-2",
        "HTFT_COMBO:2-1&gg": "HTFT:2-1",
        "HTFT_COMBO:2-X&gg": "HTFT:2-X",
    }
    for candidate_id, existing_id in expected.items():
        spec = additional.CANDIDATE_BY_ID[candidate_id]
        assert spec.equivalent_existing_id == existing_id
        existing = MARKET_BY_ID[existing_id]
        for h1, a1, h2, a2 in GRID:
            assert existing.settle(h1 + h2, a1 + a2, h1, a1) == spec.market.settle(
                h1 + h2, a1 + a2, h1, a1
            )
    assert additional.EQUIVALENT_IDS == frozenset(expected)
    assert additional.EQUIVALENT_IDS.isdisjoint(additional.AUGMENTED_IDS)
    assert len(additional.AUGMENTED_CANDIDATES) == 19


def test_impossible_htft_btts_combinations_are_absent_and_never_occur() -> None:
    for impossible in additional.IMPOSSIBLE_IDS:
        assert impossible not in additional.CANDIDATE_BY_ID
        assert impossible not in MARKET_BY_ID
        ht, ft = impossible.split(":", 1)[1].split("&", 1)[0].split("-")
        assert not any(
            result(h1, a1) == ht and result(h1 + h2, a1 + a2) == ft
            and not (h1 + h2 > 0 and a1 + a2 > 0)
            for h1, a1, h2, a2 in GRID
        )


def test_xx_btts_and_xx_goal_bands_have_distinct_score_coverage() -> None:
    ng = cells("HTFT_COMBO:X-X&ng")
    two_plus = cells("HTFT_AND_GOALS:X-X&2+")
    three_plus = cells("HTFT_AND_GOALS:X-X&3+")
    assert ng and two_plus and three_plus
    assert ng.isdisjoint(two_plus)
    assert three_plus < two_plus
    assert two_plus != three_plus
    assert all(result(h1, a1) == "X" and result(h1 + h2, a1 + a2) == "X" for h1, a1, h2, a2 in ng)
    assert all(h1 + a1 + h2 + a2 >= 3 for h1, a1, h2, a2 in three_plus)
    assert all(h1 + a1 + h2 + a2 >= 2 for h1, a1, h2, a2 in two_plus)


def test_all_result_dc_btts_and_btts_goal_bands_are_feasible_and_correct() -> None:
    result_codes = ("1", "X", "2", "1X", "12", "X2")
    for code in result_codes:
        for suffix in ("gg", "ng"):
            family = "RESULT_AND_BTTS" if len(code) == 1 else "DC_AND_BTTS"
            market_id = f"{family}:{code}&{suffix}"
            assert feasible(market_id)
            for h1, a1, h2, a2 in cells(market_id):
                fthg, ftag = h1 + h2, a1 + a2
                assert result(fthg, ftag) in code
                assert (fthg > 0 and ftag > 0) == (suffix == "gg")

    for btts_code in ("GG", "NG"):
        for band in ("0-2", "3+"):
            market_id = f"BTTS_AND_GOALS:{btts_code}&{band}"
            assert feasible(market_id)
            for h1, a1, h2, a2 in cells(market_id):
                fthg, ftag = h1 + h2, a1 + a2
                assert (fthg > 0 and ftag > 0) == (btts_code == "GG")
                assert (fthg + ftag <= 2) == (band == "0-2")
    assert cells("BTTS_AND_GOALS:GG&0-2") == {
        (h1, a1, h2, a2) for h1, a1, h2, a2 in GRID if h1 + h2 == 1 and a1 + a2 == 1
    }


def test_catalogue_status_matches_existing_snapshot_evidence() -> None:
    assert additional.CONFIRMED_IDS == {
        "RESULT_AND_BTTS:1&gg",
        "RESULT_AND_BTTS:2&gg",
        "DC_AND_BTTS:1X&gg",
        "DC_AND_BTTS:X2&gg",
        "BTTS_AND_GOALS:GG&3+",
        "HTFT_AND_GOALS:X-X&3+",
    }
    assert "HTFT_COMBO:X-X&ng" not in additional.CONFIRMED_IDS
    assert "HTFT_AND_GOALS:X-X&2+" not in additional.CONFIRMED_IDS
    summary = additional.catalogue_summary()
    assert summary["current_private_snapshot_checked"] is False
    assert summary["existing_evidence"]["date"] == "2026-09-24T21:33:44Z"
    assert len(summary["candidates"]) == 23
    for row in summary["candidates"]:
        assert row["exists_in_production"] is False
        if row["id"] in additional.CONFIRMED_IDS:
            assert row["evidence"] and row["evidence"]["section"] and row["evidence"]["selection"]
        else:
            assert row["evidence"] is None
        assert "odds" not in row and "price" not in row


def test_candidate_stats_and_group_impact_arithmetic() -> None:
    stats = CandidateStats()
    stats.add(0.20, 0.22, True, "2026-01-01")
    stats.add(0.30, 0.25, False, "2026-01-02")
    summary = stats.summary(additional.CANDIDATE_BY_ID["RESULT_AND_BTTS:X&ng"])
    assert summary["selections"] == 2
    assert summary["round_dates"] == 2
    assert summary["landed"] == 1
    assert summary["landed_pct"] == 0.5
    assert summary["mean_raw_p"] == 0.25
    assert summary["mean_pc"] == 0.235
    assert summary["landed_minus_raw_p"] == 0.25
    assert summary["landed_minus_pc"] == 0.265
    assert summary["median_fair_odds"] == 4.273
    assert summary["fair_return"] == pytest.approx(1.2727, abs=1e-4)
    assert summary["actual_bookmaker_return"]["measurement"] == "realised historical return not measurable from current data"

    impact = GroupImpact()
    impact.evaluated = 10
    impact.baseline_selections = 9
    impact.augmented_selections = 10
    impact.changed = 2
    impact.additional_wins = 2
    impact.baseline_changed_count = 2
    impact.augmented_changed_count = 2
    impact.baseline_changed_landed = 1
    impact.baseline_changed_pc = 1.0
    impact.augmented_changed_landed = 1
    impact.augmented_changed_pc = 1.1
    result = impact.summary()
    assert result["changed"] == 2
    assert result["changed_share_of_evaluated"] == 0.2
    assert result["baseline_changed"] == {"selections": 2, "landed": 1, "landed_pct": 0.5, "mean_pc": 0.5}
    assert result["augmented_changed"] == {"selections": 2, "landed": 1, "landed_pct": 0.5, "mean_pc": 0.55}


def test_committed_audit_is_complete_and_aggregate_only() -> None:
    import json
    audit = ROOT / "web" / "public" / "data" / "additional_markets_backtest.json"
    payload = json.loads(audit.read_text(encoding="utf-8"))
    assert len(payload["candidates"]) == 23
    assert set(payload["group_selection_impact"]) == {"Combos", "HT/FT"}
    catalogue = payload["catalogue"]
    assert catalogue["current_private_snapshot_checked"] is False
    assert len(catalogue["candidates"]) == 23
    required = {
        "selections", "round_dates", "landed", "landed_pct", "mean_raw_p", "mean_pc",
        "landed_minus_raw_p", "landed_minus_pc", "median_fair_odds", "fair_return",
        "fair_return_ci", "small_sample", "actual_bookmaker_return", "catalogue_status",
    }
    for row in payload["candidates"]:
        assert required <= set(row)
        assert row["selections"] > 0 and row["round_dates"] > 0
        assert row["actual_bookmaker_return"]["measurement"] == "realised historical return not measurable from current data"
    for row in payload["group_selection_impact"].values():
        assert {"changed", "additional_candidate_wins", "baseline_changed", "augmented_changed"} <= set(row)
    def walk(value) -> None:
        if isinstance(value, dict):
            assert not ({"prices", "price", "mozzart_odds"} & set(value))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(payload)
    assert payload["methodology"]["correct_score"] == "Excluded and remains hidden."


def test_augmented_registry_excludes_equivalent_duplicates_only() -> None:
    assert set(additional.AUGMENTED_IDS) == set(additional.REQUESTED_IDS) - set(additional.EQUIVALENT_IDS)
    for candidate_id in additional.AUGMENTED_IDS:
        assert additional.CANDIDATE_BY_ID[candidate_id].equivalent_existing_id is None
    assert additional.REQUESTED_IDS[:5] == (
        "HTFT_COMBO:1-X&gg", "HTFT_COMBO:1-2&gg", "HTFT_COMBO:2-1&gg",
        "HTFT_COMBO:2-X&gg", "HTFT_COMBO:X-X&ng",
    )
