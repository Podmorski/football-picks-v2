"""Failure conditions for update.yml and prices.yml."""
from __future__ import annotations

from pathlib import Path

from pipeline import alerts

ROOT = Path(__file__).resolve().parents[1]


def test_missing_publication_needs_fixtures_and_no_published_rows() -> None:
    assert alerts.missing_publication("2026-11-21", 122, 0, False)
    assert alerts.missing_publication("2026-11-21", 122, 0, True) is None
    assert alerts.missing_publication("2026-11-21", 122, 10, False) is None
    assert alerts.missing_publication("2026-11-21", 0, 0, False) is None


def test_low_price_coverage_needs_a_fetch_below_half() -> None:
    assert alerts.low_price_coverage(1, 122, True)
    assert alerts.low_price_coverage(61, 122, True) is None
    assert alerts.low_price_coverage(1, 122, False) is None
    assert alerts.low_price_coverage(0, 0, True) is None


def test_stale_settle_needs_results_and_pending_rows() -> None:
    assert alerts.stale_settle("2026-11-21", 10, False, 10)
    assert "still pending" in alerts.stale_settle("2026-11-21", 10, True, 10)
    assert alerts.stale_settle("2026-11-21", 0, False, 10) is None
    assert alerts.stale_settle("2026-11-21", 10, False, 0) is None
    assert alerts.stale_settle("2026-11-21", 10, True, 0) is None


def test_price_cli_wires_the_coverage_alert() -> None:
    source = (ROOT / "pipeline" / "mozzart" / "cli.py").read_text(encoding="utf-8")
    assert "low_price_coverage" in source
    assert "return 5" in source


def test_run_model_wires_publication_and_settle_alerts() -> None:
    source = (ROOT / "pipeline" / "run_model.py").read_text(encoding="utf-8")
    assert "missing_publication" in source
    assert "stale_settle" in source
    assert "return 3" in source


def test_prices_workflow_commits_the_private_store_on_failure() -> None:
    source = (ROOT / ".github" / "workflows" / "prices.yml").read_text(encoding="utf-8")
    assert "if: always()" in source


def test_screens_workflow_exists_and_keeps_the_artifact_for_three_days() -> None:
    source = (ROOT / ".github" / "workflows" / "screens.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in source
    assert "workflow_run" in source
    assert "npx playwright install --with-deps chromium" in source
    assert "retention-days: 3" in source
    assert "path: web/screens" in source
