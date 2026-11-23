"""Pre-registration contract: versions, formulas, protocol, no prices."""
from __future__ import annotations

import json

from pipeline import bankroll, preregistration, proposed_tickets, ticket_construction


def test_versions_and_formulas_are_frozen() -> None:
    payload = preregistration.build()
    assert payload["construction_version"] == ticket_construction.CONSTRUCTION_VERSION_V3 == "ticket-construction-v3"
    assert payload["policy_version"] == bankroll.POLICY_VERSION == "mel-v1"
    assert payload["proposal_schema_version"] == proposed_tickets.SCHEMA_VERSION == 3
    assert payload["activation_date"] == proposed_tickets.PROPOSAL_ACTIVATION_DATE
    assert payload["mel"]["drawdown_scale"] == 0.20
    assert payload["mel"]["base_fraction"] == 0.0025
    assert payload["mel"]["slope"] == 0.0175
    assert payload["comparators"]["flat"]["shares"] == [0.5, 0.3, 0.2]
    assert payload["primary_comparison"] == ["flat", "mel"]
    assert "fixed_fractional" in payload["exploratory"]
    assert payload["evaluation_id"] == "ticket-construction-v3+mel-v1"
    assert payload["evaluation"]["pooling_rule"] == "v2 and v3 performance records are never pooled"
    assert payload["ticket_construction"]["preferred_min_individual_odds"] == 1.20


def test_protocol_is_preregistered_and_complete() -> None:
    protocol = preregistration.build()["protocol"]
    assert protocol["alpha_one_sided"] == 0.05
    assert protocol["power"] == 0.80
    assert protocol["meaningful_roi_equivalent"] == 0.02
    assert "N*" in protocol["n_star_unavailable"]
    assert "156" in protocol["inconclusive_rule"]
    assert protocol["no_early_efficacy_stopping"] is True
    assert protocol["safety_review_drawdown"] == 0.20
    assert "owner's loss budget" in protocol["stop_adaptive_rule"]


def test_public_file_is_price_free() -> None:
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    text = (root / "web" / "public" / "data" / "preregistration.json").read_text(encoding="utf-8").lower()
    assert '"odds"' not in text and '"price"' not in text and '"prices"' not in text
    assert json.loads(text)["version_rule"]
