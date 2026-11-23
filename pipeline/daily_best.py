"""daily-best-v1: frozen default list, settlement and forward paper record.

The forward record covers only the default All-leagues / actual-odds 1.70-2.30
list. League, band, Show all and exact-market exploration are interactive views
and are never added to this record. Actual leg prices stay private; the public
aggregate contains counts, identities and aggregate statistics only.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

from . import ranking
from .markets import MARKET_BY_ID
from .model.ranked_backtest import _clustered_mean_ci
from .model.ranking_backtest import RETURN_BOOTSTRAP_RESAMPLES, RETURN_BOOTSTRAP_SEED

RULE_VERSION = "daily-best-v1"
ACTIVATION_MARKER = "daily-best-v1"
# Feature date. Pre-activation snapshots are exempt and are never backfilled.
ACTIVATION_DATE = "2026-11-23"
BAND_LOW = 1.70
BAND_HIGH = 2.30
MIN_ODDS = 1.20
DAILY_LIMIT = 12
HIDDEN_PREFIX = "CORRECT_SCORE:"
ODDS_AGGREGATE_MIN_SETTLED = 10
MIN_BOOTSTRAP_ROUNDS = 30
SCHEMA_VERSION = 1


def fixture_key(leg: dict) -> tuple:
    return (leg["d"], leg["h"], leg["a"])


def leg_key(leg: dict) -> tuple:
    return (leg["d"], leg["h"], leg["a"], leg["m"])


def _pc(row: dict) -> float:
    value = row.get("pc")
    if value is None:
        value = row.get("p", 0.0)
    return float(value)


def _group(market: str) -> str:
    item = MARKET_BY_ID.get(market)
    return item.group if item is not None else ""


def candidate_menu(document: dict, snapshot: dict) -> list[dict]:
    """Priced, unstarted production markets with 0<pc<1 on every fixture."""
    by_fixture: dict[tuple, list[dict]] = {}
    for row in document.get("rows", []):
        by_fixture.setdefault((row["d"], row["h"], row["a"]), []).append(row)
    started = {
        (row.get("div"), row.get("home"), row.get("away"))
        for row in snapshot.get("started_not_priced", [])
    }
    menu = []
    for fixture in snapshot.get("fixtures", []):
        key = (fixture.get("div"), fixture.get("home"), fixture.get("away"))
        if key in started or not fixture.get("prices"):
            continue
        for row in by_fixture.get(key, []):
            market = str(row.get("m", ""))
            if market.startswith(HIDDEN_PREFIX):
                continue
            probability = _pc(row)
            if not 0.0 < probability < 1.0:
                continue
            odds = fixture["prices"].get(market)
            if not isinstance(odds, (int, float)) or float(odds) <= 1.0:
                continue
            menu.append({
                "d": row["d"], "h": row["h"], "a": row["a"], "k": row.get("k"),
                "m": market, "pc": probability, "fair": 1.0 / probability,
                "odds": float(odds), "group": _group(market),
            })
    return menu


def daily_pool(candidates: list[dict]) -> list[dict]:
    return [
        candidate for candidate in candidates
        if float(candidate["odds"]) >= MIN_ODDS and 0.0 < float(candidate["pc"]) < 1.0
    ]


def in_band(odds: float) -> bool:
    return BAND_LOW <= odds <= BAND_HIGH


def band_distance(odds: float) -> float:
    if in_band(odds):
        return 0.0
    value = math.log(max(odds, 1e-9))
    return min(
        abs(value - math.log(BAND_LOW)),
        abs(value - math.log(BAND_HIGH)),
    )


def _probability_order(candidate: dict) -> tuple:
    ev = float(candidate["pc"]) * float(candidate["odds"]) - 1.0
    return (-float(candidate["pc"]), -ev, leg_key(candidate))


def _fixtures(candidates: list[dict]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = {}
    for candidate in candidates:
        out.setdefault(fixture_key(candidate), []).append(candidate)
    return out


def choose_one_per_fixture(candidates: list[dict]) -> list[dict]:
    chosen = []
    for items in _fixtures(candidates).values():
        inside = [candidate for candidate in items if in_band(float(candidate["odds"]))]
        if inside:
            chosen.append(sorted(inside, key=_probability_order)[0])
            continue
        chosen.append(sorted(items, key=lambda candidate: (
            band_distance(float(candidate["odds"])), _probability_order(candidate),
        ))[0])
    return chosen


def select_daily(candidates: list[dict]) -> dict:
    """Mirror of the Phase-1 TypeScript per-fixture/global ranking."""
    pool = daily_pool(candidates)
    fixtures = _fixtures(pool)
    in_band_fixtures = sum(
        1 for items in fixtures.values() if any(in_band(float(candidate["odds"])) for candidate in items)
    )
    chosen = choose_one_per_fixture(pool)
    inside = sorted(
        (candidate for candidate in chosen if in_band(float(candidate["odds"]))), key=_probability_order,
    )
    outside = sorted(
        (candidate for candidate in chosen if not in_band(float(candidate["odds"]))),
        key=lambda candidate: (band_distance(float(candidate["odds"])), _probability_order(candidate)),
    )
    priced = [candidate for candidate in candidates if candidate.get("odds") is not None]
    return {
        "rows": inside + outside,
        "inside": inside,
        "outside": outside,
        "in_band_fixtures": in_band_fixtures,
        "eligible_fixtures": len(fixtures),
        "rejected": len(priced) - len(pool),
    }


def visible_rows(selection: dict, limit: int = DAILY_LIMIT) -> list[dict]:
    return list(selection["rows"][:limit])


def _load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")


def activation_path(prices_dir: Path) -> Path:
    return prices_dir / "daily-best" / "activation.json"


def frozen_path(prices_dir: Path, round_date: str) -> Path:
    return prices_dir / "daily-best" / f"{round_date}.json"


def load_activation(prices_dir: Path) -> dict | None:
    payload = _load_json(activation_path(prices_dir), None)
    if not isinstance(payload, dict):
        return None
    return payload if payload.get("marker") == ACTIVATION_MARKER else None


def _snapshot_identity(snapshot: dict) -> dict:
    return {"round_date": snapshot.get("round_date"), "fetched_at": snapshot.get("fetched_at")}


def ensure_daily_best(
    round_date: str, document: dict, snapshot: dict, prices_dir: Path,
) -> dict | None:
    """Freeze the default Daily-best list once, after activation."""
    if not snapshot.get("fixtures"):
        return None
    marker = load_activation(prices_dir)
    if marker is None:
        if round_date < ACTIVATION_DATE:
            return None
        marker = {
            "schema_version": SCHEMA_VERSION,
            "marker": ACTIVATION_MARKER,
            "rule_version": RULE_VERSION,
            "activation_date": ACTIVATION_DATE,
            "activated_round": round_date,
            "snapshot_identity": _snapshot_identity(snapshot),
        }
        _write_json(activation_path(prices_dir), marker)
    activated_round = str(marker.get("activated_round") or ACTIVATION_DATE)
    if round_date < activated_round:
        return None
    path = frozen_path(prices_dir, round_date)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    selection = select_daily(candidate_menu(document, snapshot))
    rows = visible_rows(selection)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "activation_marker": ACTIVATION_MARKER,
        "round_date": round_date,
        "snapshot_identity": _snapshot_identity(snapshot),
        "band": {"low": BAND_LOW, "high": BAND_HIGH},
        "min_odds": MIN_ODDS,
        "limit": DAILY_LIMIT,
        "eligible_counts": {
            "fixtures": selection["eligible_fixtures"],
            "in_band": selection["in_band_fixtures"],
            "outside": selection["outside"],
            "rejected": selection["rejected"],
        },
        "selected": len(rows),
        "in_band_selected": len([row for row in rows if in_band(float(row["odds"]))]),
        "fallback_selected": len([row for row in rows if not in_band(float(row["odds"]))]),
        "rows": rows,
    }
    _write_json(path, payload)
    return payload


def _valid_frozen(payload: dict, round_date: str) -> bool:
    if not isinstance(payload, dict):
        return False
    rows = payload.get("rows")
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("rule_version") != RULE_VERSION:
        return False
    if payload.get("round_date") != round_date or not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict):
            return False
        if not all(key in row for key in ("d", "h", "a", "m", "pc", "odds")):
            return False
    return True


def missing_daily_best(prices_dir: Path) -> list[str]:
    marker = load_activation(prices_dir)
    if marker is None:
        return []
    activated_round = str(marker.get("activated_round") or ACTIVATION_DATE)
    missing = []
    rounds_dir = prices_dir / "rounds"
    if not rounds_dir.exists():
        return []
    for path in sorted(rounds_dir.glob("*.json")):
        snapshot = _load_json(path, {})
        round_date = str(snapshot.get("round_date", ""))
        if round_date < activated_round or not snapshot.get("fixtures"):
            continue
        payload = _load_json(frozen_path(prices_dir, round_date), {})
        if not _valid_frozen(payload, round_date):
            missing.append(round_date)
    return missing


class DailyBestReadinessError(RuntimeError):
    pass


def validate_daily_best(prices_dir: Path) -> None:
    missing = missing_daily_best(prices_dir)
    if missing:
        raise DailyBestReadinessError(
            f"missing frozen Daily best data for snapshot round(s): {', '.join(missing)} "
            f"(marker {ACTIVATION_MARKER})"
        )


def _status_map(picks_dir: Path, round_date: str) -> tuple[dict[tuple, str], bool]:
    for name in (f"{round_date}.full.json", f"{round_date}.json"):
        path = picks_dir / name
        if not path.exists():
            continue
        try:
            document = ranking.load(path)
        except (ValueError, KeyError):
            return {}, False
        rows = document.get("rows", [])
        return {leg_key(row): row.get("st", "pending") for row in rows}, bool(rows)
    return {}, False


def _empty_stats() -> dict:
    return {
        "selected": 0, "settled": 0, "landed": 0, "lost": 0, "void": 0, "pending": 0,
        "staked": 0.0, "returned": 0.0, "net": 0.0,
    }


def _add_stats(target: dict, stats: dict) -> None:
    for key in ("selected", "settled", "landed", "lost", "void", "pending"):
        target[key] = target.get(key, 0) + stats.get(key, 0)
    for key in ("staked", "returned", "net"):
        target[key] = target.get(key, 0.0) + stats.get(key, 0.0)


def _roi(stats: dict) -> float | None:
    return round(stats["net"] / stats["staked"], 6) if stats["staked"] > 0 else None


def settle_round(frozen: dict, statuses: dict[tuple, str], data_available: bool) -> dict:
    stats = _empty_stats()
    by_group: dict[str, dict] = {}
    band_split = {"in_band": _empty_stats(), "fallback": _empty_stats()}
    rows = []
    expected_landed = 0.0
    expected_landed_settled = 0.0
    settled_odds = []
    settled_ev = []
    for frozen_row in frozen.get("rows", []):
        status = statuses.get(leg_key(frozen_row), "pending")
        status = status if status in ("landed", "lost", "void", "pending") else "pending"
        group = frozen_row.get("group") or _group(str(frozen_row.get("m", "")))
        band = "in_band" if in_band(float(frozen_row["odds"])) else "fallback"
        key = group or "Unknown"
        bucket = by_group.setdefault(key, _empty_stats())
        stats["selected"] += 1
        bucket["selected"] += 1
        band_split[band]["selected"] += 1
        expected_landed += float(frozen_row["pc"])
        rows.append({
            "d": frozen_row["d"], "h": frozen_row["h"], "a": frozen_row["a"],
            "m": frozen_row["m"], "pc": round(float(frozen_row["pc"]), 8),
            "group": group, "in_band": band == "in_band", "st": status,
        })
        if status == "pending":
            stats["pending"] += 1
            bucket["pending"] += 1
            band_split[band]["pending"] += 1
            continue
        stats["settled"] += 1
        bucket["settled"] += 1
        band_split[band]["settled"] += 1
        stats[status] += 1
        bucket[status] += 1
        band_split[band][status] += 1
        expected_landed_settled += float(frozen_row["pc"])
        staked = 1.0
        returned = float(frozen_row["odds"]) if status == "landed" else 1.0 if status == "void" else 0.0
        net = returned - staked
        stats["staked"] += staked
        stats["returned"] += returned
        stats["net"] += net
        bucket["staked"] += staked
        bucket["returned"] += returned
        bucket["net"] += net
        band_split[band]["staked"] += staked
        band_split[band]["returned"] += returned
        band_split[band]["net"] += net
        settled_odds.append(float(frozen_row["odds"]))
        settled_ev.append(float(frozen_row["pc"]) * float(frozen_row["odds"]) - 1.0)
    stats["roi"] = _roi(stats)
    bucket_rows = {key: {**value, "roi": _roi(value)} for key, value in sorted(by_group.items())}
    band_rows = {key: {**value, "roi": _roi(value)} for key, value in band_split.items()}
    terminal = stats["pending"] == 0
    state = "unavailable" if not data_available else "pending" if stats["settled"] == 0 else "partial" if not terminal else "settled"
    return {
        "round_date": frozen["round_date"],
        "snapshot_identity": frozen.get("snapshot_identity"),
        "selected": stats["selected"], "settled": stats["settled"],
        "landed": stats["landed"], "lost": stats["lost"], "void": stats["void"], "pending": stats["pending"],
        "expected_landed": round(expected_landed, 6),
        "expected_landed_settled": round(expected_landed_settled, 6),
        "staked": round(stats["staked"], 6), "returned": round(stats["returned"], 6),
        "net": round(stats["net"], 6), "roi": stats["roi"],
        "pending_exposure": float(stats["pending"]),
        "state": state, "terminal": terminal,
        "round_data_available": data_available,
        "source_pending": stats["pending"] > 0,
        "in_band_selected": frozen.get("in_band_selected", 0),
        "fallback_selected": frozen.get("fallback_selected", 0),
        "eligible_counts": frozen.get("eligible_counts", {}),
        "by_group": bucket_rows,
        "band_split": band_rows,
        "rows": rows,
        "_settled_odds": settled_odds,
        "_settled_ev": settled_ev,
    }


def _sum_rounds(rounds: list[dict]) -> dict:
    stats = _empty_stats()
    expected_landed = 0.0
    expected_landed_settled = 0.0
    pending_exposure = 0.0
    in_band_selected = fallback_selected = 0
    by_group: dict[str, dict] = {}
    band_split = {"in_band": _empty_stats(), "fallback": _empty_stats()}
    for record in rounds:
        _add_stats(stats, record)
        expected_landed += float(record["expected_landed"])
        expected_landed_settled += float(record["expected_landed_settled"])
        pending_exposure += float(record["pending_exposure"])
        in_band_selected += int(record["in_band_selected"])
        fallback_selected += int(record["fallback_selected"])
        for group, value in record["by_group"].items():
            _add_stats(by_group.setdefault(group, _empty_stats()), value)
        for band, value in record["band_split"].items():
            _add_stats(band_split[band], value)
    stats["roi"] = _roi(stats)
    terminal = [
        record for record in rounds
        if record["terminal"] and float(record["staked"]) > 0
    ]
    date_rows = [[float(record["staked"]), float(record["net"])] for record in terminal]
    if len(date_rows) >= MIN_BOOTSTRAP_ROUNDS:
        _mean, bounds = _clustered_mean_ci(
            date_rows, 0, 1, resamples=RETURN_BOOTSTRAP_RESAMPLES, seed=RETURN_BOOTSTRAP_SEED,
        )
        return_ci = [None if value is None else round(value, 6) for value in bounds]
        interval_state = "available"
    else:
        return_ci = [None, None]
        interval_state = "insufficient forward rounds for an interval"
    result = {
        "selected": stats["selected"], "settled": stats["settled"],
        "landed": stats["landed"], "lost": stats["lost"], "void": stats["void"], "pending": stats["pending"],
        "expected_landed": round(expected_landed, 6),
        "expected_landed_settled": round(expected_landed_settled, 6),
        "staked": round(stats["staked"], 6), "returned": round(stats["returned"], 6),
        "net": round(stats["net"], 6), "roi": stats["roi"],
        "pending_exposure": round(pending_exposure, 6),
        "settled_rounds": len(date_rows), "terminal_rounds": len(terminal),
        "return_ci": return_ci, "interval_state": interval_state,
        "in_band_selected": in_band_selected, "fallback_selected": fallback_selected,
        "by_group": {key: {**value, "roi": _roi(value)} for key, value in sorted(by_group.items())},
        "band_split": {key: {**value, "roi": _roi(value)} for key, value in band_split.items()},
        "mean_actual_odds": None, "median_actual_odds": None, "mean_model_ev": None,
        "odds_aggregate_state": "insufficient settled picks for odds aggregates",
    }
    return result


def aggregate(prices_dir: Path, picks_dir: Path) -> dict:
    marker = load_activation(prices_dir)
    rounds = []
    settled_odds: list[float] = []
    settled_ev: list[float] = []
    daily_dir = prices_dir / "daily-best"
    if marker is not None and daily_dir.exists():
        for path in sorted(daily_dir.glob("*.json")):
            if path.name == "activation.json":
                continue
            frozen = _load_json(path, {})
            round_date = str(frozen.get("round_date", path.stem))
            if marker and round_date < str(marker.get("activated_round") or ACTIVATION_DATE):
                continue
            if not _valid_frozen(frozen, round_date):
                continue
            statuses, available = _status_map(picks_dir, round_date)
            record = settle_round(frozen, statuses, available)
            settled_odds.extend(record.pop("_settled_odds", []))
            settled_ev.extend(record.pop("_settled_ev", []))
            rounds.append(record)
    rounds.sort(key=lambda record: record["round_date"])
    cumulative = _sum_rounds(rounds)
    cumulative["settled_forward_rows"] = cumulative["settled"]
    if len(settled_odds) >= ODDS_AGGREGATE_MIN_SETTLED:
        cumulative["mean_actual_odds"] = round(statistics.fmean(settled_odds), 6)
        cumulative["median_actual_odds"] = round(statistics.median(settled_odds), 6)
        cumulative["mean_model_ev"] = round(statistics.fmean(settled_ev), 6)
        cumulative["odds_aggregate_state"] = "available"
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "activation_marker": ACTIVATION_MARKER,
        "band": {"low": BAND_LOW, "high": BAND_HIGH},
        "min_odds": MIN_ODDS,
        "limit": DAILY_LIMIT,
        "activation": marker,
        "rounds": rounds,
        "cumulative": cumulative,
        "note": (
            "Forward frozen-price paper return. One unit per frozen pick; landed returns the frozen "
            "actual price, lost 0, void 1, pending is excluded from settled staked/returned/net and "
            "shown as pending exposure. Not an executable bookmaker return and not guaranteed profit."
        ),
        "prices_published": False,
    }


def write(prices_dir: Path, picks_dir: Path, web_dir: Path) -> dict:
    payload = aggregate(prices_dir, picks_dir)
    _write_json(web_dir / "daily-best-record.json", payload)
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.daily_best")
    parser.add_argument("command", choices=["aggregate"])
    parser.add_argument("--prices-dir", required=True, type=Path)
    parser.add_argument("--picks-dir", type=Path, default=Path("picks"))
    parser.add_argument("--web-dir", type=Path, default=Path("web/public/data"))
    args = parser.parse_args(argv)
    try:
        validate_daily_best(args.prices_dir)
    except DailyBestReadinessError as exc:
        print(f"ERROR: {exc}")
        return 4
    payload = write(args.prices_dir, args.picks_dir, args.web_dir)
    print(
        f"daily best record: {len(payload['rounds'])} frozen rounds, "
        f"{payload['cumulative']['selected']} selected, {payload['cumulative']['settled']} settled"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
