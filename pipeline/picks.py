"""Small shared helpers that survived the move to the ranking-only product.

The old pick views (Most likely / Stand-out / Best combos / By play) and their
picker were removed in milestone 3c; what remains is month names, the confidence
badge and the result lookup used by the ranking pipeline.
"""
from __future__ import annotations

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def confidence_badge(samples: float, gap: float, row: dict | None, min_bin_sample: int) -> str:
    """High / Medium / Low from sample size, a gap term and the calibration of the bin."""
    strong = 0
    weak = 0
    if samples >= 20:
        strong += 1
    elif samples < 12:
        weak += 1

    if gap <= 0.05:
        strong += 1
    elif gap > 0.08:
        weak += 1

    if row is not None and row.get("n", 0) >= min_bin_sample:
        error = abs(row["landed"] - row["shown"])
        if error <= 0.03:
            strong += 1
        elif error > 0.06:
            weak += 1

    if weak:
        return "Low"
    if strong == 3:
        return "High"
    return "Medium"


def read_results(matches: list) -> dict:
    """(iso date, home, away) -> (fthg, ftag, hthg, htag)."""
    return {
        (match.date.isoformat(), match.home, match.away): (match.fthg, match.ftag, match.hthg, match.htag)
        for match in matches
    }
