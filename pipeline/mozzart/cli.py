"""Fetch one round's Mozzart prices into the private store.

Run from the price job (GitHub Actions) with the private repo checked out:

    python -m pipeline.mozzart.cli --date 2026-11-21 --prices-dir /path/to/prices

Writes rounds/<date>.json, frozen/<date>.json, record.json and usage.json in
the private dir. Never writes to the public repository.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from ..config import ROOT_DIR
from .. import ranking
from . import client, record, snapshot

PICKS_DIR = ROOT_DIR / "picks"


def _load_picks(date: dt.date) -> dict | None:
    path = PICKS_DIR / f"{date.isoformat()}.json"
    if not path.exists():
        return None
    return ranking.load(path)


def _until(round_date: dt.date, fixtures: list[dict]) -> dt.datetime:
    latest = None
    for fixture in fixtures:
        parsed = snapshot._fixture_kickoff(round_date, fixture.get("k"))
        if parsed is not None and (latest is None or parsed > latest):
            latest = parsed
    end_of_day = dt.datetime.combine(round_date + dt.timedelta(days=1), dt.time(0, 0), tzinfo=dt.timezone.utc)
    if latest is None:
        return end_of_day
    return min(latest + dt.timedelta(hours=1), end_of_day)


def _load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")


def _all_snapshots(prices_dir: Path) -> list[dict]:
    out = []
    for path in sorted((prices_dir / "rounds").glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return out


def _all_rounds() -> list[dict]:
    out = []
    for path in sorted(PICKS_DIR.glob("*.json")):
        try:
            document = ranking.load(path)
        except (ValueError, KeyError):
            continue
        if document.get("kind") == "example":
            continue
        out.append(document)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.mozzart.cli")
    parser.add_argument("--date", help="round date YYYY-MM-DD (default: today)")
    parser.add_argument("--prices-dir", required=True, help="private prices repo checkout")
    parser.add_argument("--force", action="store_true", help="refetch even if a snapshot exists")
    args = parser.parse_args(argv)

    round_date = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    prices_dir = Path(args.prices_dir)
    snapshot_path = prices_dir / "rounds" / f"{round_date.isoformat()}.json"

    document = _load_picks(round_date)
    if document is None:
        print(f"no picks file for {round_date}; nothing to price")
        return 0
    fixtures = snapshot.fixtures_from_round(document)
    if not fixtures:
        print(f"round {round_date} has no fixtures yet; nothing to price")
        return 0

    if snapshot_path.exists() and not args.force:
        print(f"snapshot already frozen for {round_date}; skipping fetch")
        snapshots = _all_snapshots(prices_dir)
    else:
        key = os.environ.get("PULSESCORE_API_KEY")
        if not key:
            print("PULSESCORE_API_KEY is not set")
            return 2
        budget = client.Budget.load(_load_json(prices_dir / "usage.json", None), client.month_key())
        kind = client.round_kind(round_date)
        allowed, reason = client.may_fetch(
            kind, budget.used, budget.monthly_cap, round_date, client.PRIORITY_ESTIMATE[kind]
        )
        if not allowed:
            budget.entries.append(
                {
                    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    "endpoint": "skip",
                    "page": 0,
                    "status": 0,
                    "remaining": None,
                    "note": f"{kind}: {reason}",
                }
            )
            _write_json(prices_dir / "usage.json", budget.dump())
            print(f"budget priority: skipping {kind} fetch: {reason}")
            return 0
        print(f"budget before: {budget.used}/{budget.monthly_cap} requests this month ({kind})")
        until = _until(round_date, fixtures)
        events: list[dict] = []
        try:
            events, pages = client.fetch_events(key, until, budget)
            print(f"fetched {pages} page(s), {len(events)} events")
        except client.BudgetExceeded as exc:
            events = getattr(exc, "partial", [])
            print(f"budget refused: {exc}; using {len(events)} events already fetched")
        except Exception as exc:  # noqa: BLE001 - the price job must never crash publishing
            print(f"fetch failed: {exc}")
            return 1
        fetched_at = dt.datetime.now(dt.timezone.utc)
        snap = snapshot.build(round_date, fixtures, events, fetched_at)
        _write_json(snapshot_path, snap)
        frozen = record.freeze(snap, document)
        _write_json(prices_dir / "frozen" / f"{round_date.isoformat()}.json", frozen)
        _write_json(prices_dir / "usage.json", budget.dump())
        print(f"budget after: {budget.used}/{budget.monthly_cap} requests this month")
        snapshots = _all_snapshots(prices_dir)

    aggregate = record.aggregate(_all_rounds(), snapshots)
    _write_json(prices_dir / "record.json", aggregate)

    latest = _load_json(snapshot_path, {})
    priced = len(latest.get("fixtures", []))
    unmatched = len(latest.get("unmatched_fixtures", []))
    print(f"priced fixtures: {priced}, unmatched fixtures: {unmatched}")
    print(f"record rows: {len(aggregate.get('summary', []))}, priced picks: {aggregate.get('priced_picks', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
