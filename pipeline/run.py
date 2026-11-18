"""Run the pipeline: download -> parse -> count -> write derived JSON.

Usage: python -m pipeline.run [--divisions E1,E2] [--offline]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from .config import (
    FIRST_SEASON_START,
    RAW_DIR,
    WEB_DATA_DIR,
    load_leagues,
    season_code,
    season_label,
    season_start_year,
)
from .counts import TEAM_SCOPES, league_counts, team_counts, top_ten
from .download import DownloadError, Fetcher, SeasonFetcher, probe_season_exists
from .outcomes import OUTCOMES
from .parse import MissingColumns, parse_season_csv
from .quality import missing_season, season_quality, totals

SCHEMA = {
    "version": 1,
    "stat": "[n, hits, rate, lo, hi] — Wilson 95% CI, rate and bounds rounded to 4dp; null when n=0",
    "weekday_buckets": {"tue": "Tuesday", "sat": "Saturday", "other": "all other days"},
    "team_scopes": list(TEAM_SCOPES),
    "top10": "ranked by Wilson lower bound, minimum n=5, top 10 per scope",
}

HEADLINE_OUTCOMES = ("tg_3plus", "btts_yes", "ht_x", "c1", "c2", "c3")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pipeline", description="Build football-picks-v2 data")
    parser.add_argument("--divisions", help="comma-separated division codes (default: all in leagues.yaml)")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR, help="download cache directory")
    parser.add_argument("--out-dir", type=Path, default=WEB_DATA_DIR, help="JSON output directory")
    parser.add_argument("--offline", action="store_true", help="use only already-cached files")
    parser.add_argument("--today", help="override today's date (YYYY-MM-DD), for tests")
    return parser.parse_args(argv)


def write_json(path: Path, payload: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path.write_text(text + "\n", encoding="utf-8")
    return path.stat().st_size


def table_cell(stat: list) -> str:
    n, _hits, rate, lo, hi = stat
    if not n or rate is None:
        return "-"
    return f"{rate * 100:.1f}% n={n} [{lo * 100:.1f}-{hi * 100:.1f}]"


def determine_current_start(fetcher: Fetcher, today: dt.date) -> int | None:
    """Newest season the archive actually holds (probed on E1)."""
    guess = today.year if today.month >= 7 else today.year - 1
    for candidate in range(guess, FIRST_SEASON_START - 1, -1):
        if probe_season_exists(fetcher, candidate):
            return candidate
    return None


def cached_seasons(raw_dir: Path) -> int | None:
    found: list[int] = []
    if raw_dir.exists():
        for child in raw_dir.iterdir():
            if child.is_dir() and len(child.name) == 4 and child.name.isdigit():
                found.append(2000 + int(child.name[:2]))
    return max(found) if found else None


def print_quality(division_rows: dict[str, dict]) -> None:
    print("\nDATA QUALITY (per division-season)")
    print(f"{'div':<5}{'season':<10}{'status':>7}{'rows':>6}{'ht_missing':>12}{'dups':>6}{'teams':>7}  date range")
    for code in sorted(division_rows):
        for season in sorted(division_rows[code]["seasons"], key=season_start_year):
            row = division_rows[code]["seasons"][season]
            span = f"{row['date_min']}..{row['date_max']}" if row["date_min"] else "-"
            print(
                f"{code:<5}{season:<10}{row['status']:>7}{row['rows']:>6}"
                f"{row['ht_missing']:>12}{row['duplicates']:>6}{row['teams']:>7}  {span}"
            )


def print_pooled(index_rows: list[dict], outcome_ids: tuple[str, ...]) -> None:
    print("\nPOOLED LEAGUE RATES (all seasons)")
    labels = {outcome.id: f"{outcome.id} {outcome.label}" for outcome in OUTCOMES}
    for group in (outcome_ids[:3], outcome_ids[3:]):
        print("")
        header = f"{'div':<5}{'league':<24}" + "".join(f"{labels[oid]:<30}" for oid in group)
        print(header)
        for row in index_rows:
            cells = "".join(f"{table_cell(row['headline'][oid]):<30}" for oid in group)
            print(f"{row['code']:<5}{row['name'][:23]:<24}{cells}")


def compact_teams(teams: dict) -> dict:
    """Drop n=0 stats and zero streaks: absence means "no sample".

    Keeps the JSON small without losing information — a stat with n=0 has no
    rate or interval, and a streak of 0 is the same statement as no key.
    """
    compact: dict[str, dict] = {}
    for team, data in teams.items():
        entry: dict[str, dict] = {"current": {}, "previous": {}, "streak": {}}
        for scope, stats in data["current"].items():
            kept = {oid: stat for oid, stat in stats.items() if stat[0] > 0}
            if kept:
                entry["current"][scope] = kept
        for scope, stats in data["previous"].items():
            kept = {oid: stat for oid, stat in stats.items() if stat[0] > 0}
            if kept:
                entry["previous"][scope] = kept
        entry["streak"] = {oid: value for oid, value in data["streak"].items() if value}
        compact[team] = entry
    return compact


def build_division(
    league,
    matches: list,
    seasons: list[str],
    current_label: str | None,
    focus: str | None,
    previous: str | None,
) -> dict:
    league_stats = league_counts(matches, OUTCOMES)
    teams = team_counts(matches, OUTCOMES, focus, previous)
    top10s = top_ten(teams, OUTCOMES)

    return {
        "schema": SCHEMA,
        "code": league.code,
        "name": league.name,
        "country": league.country,
        "tier": league.tier,
        "seasons": seasons,
        "current_season": current_label,
        "focus_season": focus,
        "previous_season": previous,
        "matches": len(matches),
        "team_count": len(teams),
        "outcomes": [
            {"id": outcome.id, "label": outcome.label, "group": outcome.group, "needs_ht": outcome.needs_ht}
            for outcome in OUTCOMES
        ],
        "league": league_stats,
        "teams": compact_teams(teams),
        "top10": top10s,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    leagues = load_leagues()
    if args.divisions:
        wanted = [code.strip() for code in args.divisions.split(",") if code.strip()]
        known = {league.code for league in leagues}
        unknown = [code for code in wanted if code not in known]
        if unknown:
            print(f"unknown division codes: {unknown}", file=sys.stderr)
            return 2
        leagues = [league for league in leagues if league.code in wanted]

    fetcher = Fetcher()
    season_fetcher = SeasonFetcher(fetcher, args.raw_dir)

    if args.offline:
        current_start = cached_seasons(args.raw_dir)
    else:
        current_start = determine_current_start(fetcher, today)

    if current_start is None:
        print("STOP: could not determine a current season from the archive.", file=sys.stderr)
        return 3

    starts = list(range(FIRST_SEASON_START, current_start + 1))
    seasons = [season_label(start) for start in starts]
    current_label = season_label(current_start)
    print(f"current season: {current_label} (code {season_code(current_start)})")
    print(f"seasons: {seasons[0]} .. {seasons[-1]} ({len(seasons)})")

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    index_rows: list[dict] = []
    division_quality: dict[str, dict] = {}
    missing_files: list[str] = []

    for league in leagues:
        matches: list = []
        quality: dict[str, dict] = {}

        for start in starts:
            label = season_label(start)
            code = season_code(start)
            try:
                if args.offline:
                    path = season_fetcher.path_for(code, league.code)
                    status = 200 if path.exists() else 404
                    path = path if path.exists() else None
                else:
                    status, path = season_fetcher.season_file(start, league.code, current_start)
            except DownloadError as exc:
                print(f"STOP: football-data.co.uk refused a download: {exc}", file=sys.stderr)
                return 4

            if path is None:
                quality[label] = missing_season(label, status)
                missing_files.append(f"{code}/{league.code}")
                continue

            try:
                parsed = parse_season_csv(path, label)
            except MissingColumns as exc:
                print(f"STOP: {exc}")
                print(f"columns present: {exc.available}", file=sys.stderr)
                return 5

            matches.extend(parsed.matches)
            quality[label] = season_quality(parsed, status)

        if not matches:
            print(f"{league.code}: no matches available, skipping")
            continue

        present = sorted({match.season for match in matches}, key=season_start_year)
        focus = current_label if current_label in present else present[-1]
        focus_start = season_start_year(focus)
        previous = season_label(focus_start - 1) if focus_start - 1 >= FIRST_SEASON_START else None

        document = build_division(league, matches, present, current_label, focus, previous)
        size = write_json(out_dir / f"{league.code}.json", document)

        division_quality[league.code] = {
            "name": league.name,
            "country": league.country,
            "tier": league.tier,
            "seasons": quality,
            "totals": totals(quality),
        }

        pooled = document["league"]["pooled"]
        index_rows.append(
            {
                "code": league.code,
                "name": league.name,
                "country": league.country,
                "tier": league.tier,
                "matches": len(matches),
                "teams": len(document["teams"]),
                "focus_season": focus,
                "headline": {oid: pooled[oid] for oid in HEADLINE_OUTCOMES},
            }
        )
        print(f"{league.code}: {len(matches)} matches, {len(document['teams'])} teams, {size / 1024:.0f} KB")

    if not args.offline:
        try:
            status, fixtures_path = season_fetcher.fixtures()
            print(
                f"fixtures.csv: status {status}"
                + (f", stored {fixtures_path.stat().st_size} bytes" if fixtures_path else ", not stored")
            )
        except DownloadError as exc:
            print(f"STOP: football-data.co.uk refused the fixtures download: {exc}", file=sys.stderr)
            return 4

    index_payload = {
        "schema": SCHEMA,
        "seasons": seasons,
        "current_season": current_label,
        "divisions": sorted(index_rows, key=lambda row: row["code"]),
    }
    quality_payload = {
        "schema": SCHEMA,
        "seasons": seasons,
        "current_season": current_label,
        "missing_files": missing_files,
        "divisions": division_quality,
    }
    write_json(out_dir / "leagues.json", index_payload)
    write_json(out_dir / "data_quality.json", quality_payload)

    print_quality(division_quality)
    print_pooled(sorted(index_rows, key=lambda row: row["code"]), HEADLINE_OUTCOMES)
    print(f"\nrequests this run: {fetcher.request_count}")
    print(f"downloaded: {len(season_fetcher.downloaded)}, from cache: {len(season_fetcher.cached)}")
    if missing_files:
        print(f"missing files ({len(missing_files)}): {missing_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
