"""Pure failure conditions for update.yml and prices.yml.

A returned message is printed as ALERT and makes the workflow step fail, so
GitHub emails the owner. These are deliberately conservative: only a round with
fixtures, a price fetch that actually ran, or a settle with unused results can
trigger.
"""
from __future__ import annotations


def missing_publication(round_date, fixtures: int, published_now: int, already_published: bool) -> str | None:
    if fixtures <= 0 or already_published or published_now > 0:
        return None
    return f"{round_date}: {fixtures} fixtures but nothing was published"


def low_price_coverage(priced: int, total: int, fetched: bool) -> str | None:
    if not fetched or total <= 0 or priced >= 0.5 * total:
        return None
    return f"price pass priced {priced}/{total} fixtures (<50%)"


def stale_settle(round_date, results: int, changed: bool, pending_with_results: int) -> str | None:
    """Source-backed rows still pending after settlement are a pipeline defect.

    ``changed=False`` preserves the original unused-results alert. ``changed=True``
    also fails when only part of the available results were applied.
    """
    if results <= 0 or pending_with_results <= 0:
        return None
    if not changed:
        return f"{round_date}: {results} results but settling changed nothing ({pending_with_results} pending)"
    return f"{round_date}: {pending_with_results} source-backed rows still pending after settlement"
