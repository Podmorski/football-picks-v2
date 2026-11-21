"""Pure picker and ticket maths (mirrors web/components/Picker.tsx and lib/ticket.ts)."""
from __future__ import annotations

EXCLUDED = {"RESULT:1", "RESULT:2"}
DEFAULT_FLOOR = 1.50


def pc(row: dict) -> float:
    return float(row.get("pc", row.get("p", 0.0)))


def fair(row: dict) -> float:
    return 1.0 / max(pc(row), 1e-4)


def pick_rows(
    rows: list[dict], bet: str, league: str = "all", groups: dict[str, str] | None = None,
    min_fair: float = DEFAULT_FLOOR,
) -> list[dict]:
    groups = groups or {}
    filtered = [
        row for row in rows
        if (league == "all" or row.get("d") == league) and fair(row) >= min_fair
    ]
    if bet == "any":
        best: dict[tuple, dict] = {}
        for row in filtered:
            if row.get("m") in EXCLUDED:
                continue
            key = (row.get("h"), row.get("a"))
            if key not in best or pc(row) > pc(best[key]):
                best[key] = row
        return list(best.values())
    if bet.startswith("group:"):
        group = bet.split(":", 1)[1]
        best = {}
        for row in filtered:
            if groups.get(row.get("m")) != group:
                continue
            key = (row.get("h"), row.get("a"))
            if key not in best or pc(row) > pc(best[key]):
                best[key] = row
        return list(best.values())
    market_id = bet.split(":", 1)[1]
    return [row for row in filtered if row.get("m") == market_id]


def below_floor_count(rows: list[dict], bet: str, league: str = "all", min_fair: float = DEFAULT_FLOOR) -> int:
    """Matches whose single-market row is below the floor (hidden and counted)."""
    if not bet.startswith("market:"):
        return 0
    market_id = bet.split(":", 1)[1]
    by_match: dict[tuple, float] = {}
    for row in rows:
        if league != "all" and row.get("d") != league:
            continue
        if row.get("m") != market_id:
            continue
        by_match[(row.get("h"), row.get("a"))] = fair(row)
    return sum(1 for value in by_match.values() if value < min_fair)


def top_n(rows: list[dict], n: int = 10) -> list[dict]:
    return sorted(rows, key=lambda row: -pc(row))[:n]


def match_best(rows: list[dict], home: str, away: str, min_fair: float = DEFAULT_FLOOR, n: int = 10) -> list[dict]:
    candidates = [
        row for row in rows
        if row.get("h") == home and row.get("a") == away and fair(row) >= min_fair
    ]
    return sorted(candidates, key=lambda row: -pc(row))[:n]


def ticket_status(statuses: list[str | None]) -> str:
    """Any leg lost => lost; otherwise any pending => pending; else landed."""
    if any(status == "lost" for status in statuses):
        return "lost"
    if any(status is None or status == "pending" for status in statuses):
        return "pending"
    return "landed"


def _metric(row: dict, key: str, price_index: dict | None) -> float | str:
    price = (price_index or {}).get(f"{row.get('d')}|{row.get('h')}|{row.get('a')}|{row.get('m')}")
    if key == "fair":
        return fair(row)
    if key == "mozzart":
        return float(price["odds"]) if price else -1.0
    if key == "vsfair":
        return (float(price["odds"]) / fair(row) - 1.0) if price else -9.9
    if key == "vsusual":
        return (pc(row) / row["lr"] - 1.0) if row.get("lr") else -9.9
    if key == "kickoff":
        return row.get("k") or ""
    return pc(row)


def sort_rows(rows: list[dict], key: str = "pc", direction: str = "desc", price_index: dict | None = None) -> list[dict]:
    sign = 1 if direction == "asc" else -1
    return sorted(rows, key=lambda row: _metric(row, key, price_index), reverse=(sign == -1))


def combined_probability(legs: list[dict]) -> float:
    total = 1.0
    for leg in legs:
        total *= pc(leg)
    return total


def combined_fair(legs: list[dict]) -> float:
    total = 1.0
    for leg in legs:
        total *= fair(leg)
    return total


def combined_mozzart(legs: list[dict]) -> float | None:
    if not legs or any(leg.get("odds") is None for leg in legs):
        return None
    total = 1.0
    for leg in legs:
        total *= float(leg["odds"])
    return total


def ticket_vs_fair(legs: list[dict], bonus: float = 0.0) -> float | None:
    mozzart = combined_mozzart(legs)
    if mozzart is None:
        return None
    return mozzart * (1.0 + bonus / 100.0) / combined_fair(legs) - 1.0


def payout(stake: float, legs: list[dict], bonus: float = 0.0) -> float | None:
    mozzart = combined_mozzart(legs)
    if mozzart is None:
        return None
    return stake * mozzart * (1.0 + bonus / 100.0)


def same_match_warning(legs: list[dict]) -> bool:
    seen = set()
    for leg in legs:
        key = (leg.get("h"), leg.get("a"))
        if key in seen:
            return True
        seen.add(key)
    return False
