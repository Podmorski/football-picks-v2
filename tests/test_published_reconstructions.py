"""Task 22: published-pick provenance, reconstruction immutability and privacy."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

from pipeline import build_provenance, published_reconstructions as reconstructions, ranking

ROOT = Path(__file__).resolve().parents[1]
DATES = ("2026-11-14", "2026-11-21", "2026-11-22")


def provenance(date: str) -> dict:
    return reconstructions.load_provenance(date)


def test_provenance_commits_rules_and_pre_match_flags() -> None:
    example = provenance("2026-11-14")
    assert example["publication_commit"] == "5c59bf3"
    assert example["kind"] == "example"
    assert example["rule_version"] == "picks-build-round-v1"
    assert example["pre_match_publication"] is False
    assert example["publication_precedes_fixtures"] is False
    assert example["publication_time"][:10] > "2026-11-14"

    for date in ("2026-11-21", "2026-11-22"):
        published = provenance(date)
        assert published["publication_commit"] == "8650c95"
        assert published["kind"] == "round"
        assert published["rule_version"] == "dashboard-lean-top15-v1"
        assert published["pre_match_publication"] is True
        assert published["publication_precedes_fixtures"] is True
        assert published["publication_time"][:10] < date


def test_pool_and_input_hashes_are_reproducible() -> None:
    for date in DATES:
        payload = provenance(date)
        assert len(payload["pool"]) == 15
        assert payload["pool_hash"] == build_provenance.digest(payload["pool"])
        assert payload["prediction_input_hash"].startswith("sha256:")
        assert len(payload["prediction_input_hash"]) == 71
        for leg in payload["pool"]:
            assert abs(leg["fair"] - 1 / leg["pc"]) < 1e-5


def test_prediction_fields_match_publication_apart_from_result_fields() -> None:
    for date in ("2026-11-21", "2026-11-22"):
        payload = provenance(date)
        comparison = payload["current_comparison"]
        assert comparison["match"] is True
        assert comparison["differences"] == []
        assert comparison["checked_fields"] == ["p", "pl", "pp", "lr", "ln", "hr", "hn", "ar", "an", "c", "s", "k"]
        current = ranking.load(ROOT / "picks" / f"{date}.json")
        by_key = {(row["d"], row["h"], row["a"], row["m"]): row for row in current["rows"]}
        for leg in payload["pool"]:
            row = by_key[(leg["d"], leg["h"], leg["a"], leg["m"])]
            assert row["pl"] == leg["pc"]


def test_14_nov_is_a_retrospective_example_with_no_pre_match_claim() -> None:
    payload = provenance("2026-11-14")
    assert payload["current_comparison"]["match"] is False
    assert payload["current_comparison"]["differences"]
    round_doc = reconstructions.build_round(payload, {})
    assert round_doc["kind"] == "example"
    assert round_doc["pre_match_publication"] is False
    assert round_doc["example_disclaimer"] == "Retrospective example round; no pre-match publication."
    assert "Published pick pool reproduced from commit 5c59bf3" in round_doc["disclaimer"]


def test_masked_and_altered_outcomes_leave_every_leg_identical() -> None:
    for date in ("2026-11-21", "2026-11-22"):
        payload = provenance(date)
        masked = reconstructions.build_round(payload, {})
        altered = reconstructions.build_round(
            payload, {(leg["d"], leg["h"], leg["a"], leg["m"]): "landed" for leg in payload["pool"]},
        )
        assert json.dumps([p["legs"] for p in masked["proposals"]], sort_keys=True) == json.dumps(
            [p["legs"] for p in altered["proposals"]], sort_keys=True
        )
        assert json.dumps([p["construction"] for p in masked["proposals"]], sort_keys=True) == json.dumps(
            [p["construction"] for p in altered["proposals"]], sort_keys=True
        )
        assert masked["proposals"][0]["settlement"]["status"] == "pending"
        assert altered["proposals"][0]["settlement"]["status"] == "landed"


def test_selection_and_construction_do_not_read_status_fields() -> None:
    for function in (reconstructions.pool_menu, reconstructions.construct):
        source = inspect.getsource(function)
        for forbidden in ("landed", "lost", "void", '"st"', "settlement"):
            assert forbidden not in source


def test_construction_is_v2_with_one_market_per_fixture_and_no_correct_score() -> None:
    payload = reconstructions.generate_payload()
    for round_doc in payload["rounds"]:
        assert len(round_doc["proposals"]) == 3
        for proposal in round_doc["proposals"]:
            assert proposal["status"] == "available"
            assert proposal["construction"]["algorithm"] == "ticket-construction-v2"
            assert proposal["construction"]["applied_later"] is True
            assert proposal["construction"]["band"] in ("preferred", "outside", "below_floor")
            assert proposal["construction"]["band_message"]
            fixtures = [(leg["d"], leg["h"], leg["a"]) for leg in proposal["legs"]]
            assert len(fixtures) == len(set(fixtures))
            assert not any(leg["m"].startswith("CORRECT_SCORE:") or leg["group"] == "Correct score" for leg in proposal["legs"])
            if proposal["type"] == "best2":
                assert len(proposal["legs"]) == 2
            else:
                assert 2 <= len(proposal["legs"]) <= 5


def test_pricing_mode_is_fair_only_and_never_mixed() -> None:
    payload = reconstructions.generate_payload()
    assert payload["pricing_mode"] == "model-fair"
    for round_doc in payload["rounds"]:
        assert round_doc["provenance"]["pricing_mode"] == "model-fair"
        assert "1/pc" in round_doc["pricing_note"]
        for proposal in round_doc["proposals"]:
            product = 1.0
            for leg in proposal["legs"]:
                assert set(leg) == {"d", "k", "h", "a", "m", "label", "group", "pc", "fair"}
                product *= leg["fair"]
            assert abs(proposal["combined_fair_odds"] - product) < 1e-4


def test_committed_reconstruction_file_has_three_rounds_and_no_money() -> None:
    payload = json.loads((ROOT / "web" / "public" / "data" / "published-reconstructions.json").read_text(encoding="utf-8"))
    assert payload["definition_version"] == "published-pick-reconstruction-v1"
    assert [row["round_date"] for row in payload["rounds"]] == list(DATES)
    assert payload["rounds"][0]["example_disclaimer"]
    assert payload["rounds"][1]["example_disclaimer"] == ""
    assert payload["cumulative"]["not_reconstructed"] == 3
    text = json.dumps(payload).lower()
    for forbidden in ('"odds"', '"prices"', '"price"', '"staked"', '"return"', '"profit"', '"roi"', '"bankroll"', '"mozzart"', '"raw"', '"response"'):
        assert forbidden not in text, forbidden


def test_committed_legs_equal_the_outcome_masked_construction() -> None:
    mask = reconstructions.generate_payload()
    committed = json.loads((ROOT / "web" / "public" / "data" / "published-reconstructions.json").read_text(encoding="utf-8"))
    assert json.dumps([(r["round_date"], [p["legs"] for p in r["proposals"]], [p["construction"] for p in r["proposals"]]) for r in mask["rounds"]], sort_keys=True) == json.dumps(
        [(r["round_date"], [p["legs"] for p in r["proposals"]], [p["construction"] for p in r["proposals"]]) for r in committed["rounds"]], sort_keys=True
    )


def test_reconstructions_do_not_enter_forward_aggregates() -> None:
    forward = (ROOT / "pipeline" / "forward_validation.py").read_text(encoding="utf-8")
    proposals = (ROOT / "pipeline" / "proposed_tickets.py").read_text(encoding="utf-8")
    for source in (forward, proposals):
        assert "published_reconstructions" not in source
        assert "published-reconstruction" not in source
    validation = (ROOT / "web" / "public" / "data" / "forward-validation.json").read_text(encoding="utf-8").lower()
    assert "reconstruction" not in validation
    record = (ROOT / "web" / "public" / "data" / "proposed-tickets-record.json").read_text(encoding="utf-8").lower()
    assert "reconstruction" not in record
