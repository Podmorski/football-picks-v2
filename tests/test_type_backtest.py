"""TYPE_RULE backtest: the fast predicate mirrors the shared rule; the report is committed."""
from __future__ import annotations

import json
import random
from pathlib import Path

from pipeline.model.type_backtest import passes
from pipeline.vetting import Candidate, type_evaluate

ROOT = Path(__file__).resolve().parents[1]


def test_fast_predicate_matches_the_shared_type_rule() -> None:
    random.seed(1)
    for _ in range(5000):
        usual = random.uniform(0.02, 0.8)
        probability = random.uniform(0.01, 0.99)
        model = random.uniform(0.01, 0.99)
        home_rate = random.uniform(0.0, 1.0)
        away_rate = random.uniform(0.0, 1.0)
        home_n = random.randint(0, 20)
        away_n = random.randint(0, 20)
        fair = 1 / max(probability, 1e-4)
        candidate = Candidate(
            probability=probability, model_probability=model, league_rate=usual, league_n=1000,
            home_rate=home_rate, home_n=home_n, away_rate=away_rate, away_n=away_n, fair_odds=fair,
        )
        assert passes(probability, model, usual, home_rate, home_n, away_rate, away_n, fair) == type_evaluate(candidate)[0]


def test_committed_report_structure() -> None:
    report = json.loads((ROOT / "web" / "public" / "data" / "type_backtest.json").read_text(encoding="utf-8"))
    assert report["seasons"] == ["2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
    assert [row["group"] for row in report["groups"]] == [
        "Combos", "HT/FT", "Goals", "BTTS", "Half-time", "Team goals", "Result & double chance",
    ]
    assert "Correct score" not in [row["group"] for row in report["groups"]]
    assert report["bootstrap"] == {"resamples": 2000, "seed": 20261025, "unit": "round date"}
    assert report["rule"]["max_fair_odds"] == 15.0
    for row in report["groups"]:
        assert row["picks"] > 0 and row["rounds"] > 0
        assert 0 <= row["landed"] <= 1
        assert 0 <= row["predicted"] <= 1
        low, high = row["return_ci"]
        assert low is not None and high is not None and low <= high
