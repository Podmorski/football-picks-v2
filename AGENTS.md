# AGENTS.md — football-picks-v2 handover

Read this first. It is the durable context for any worker on this repo.

## Product

Private web app that, for each Tuesday, Saturday and Sunday round, ranks football bets by statistical
probability. It shows a probability-sorted picker: choose League and Bet (Any bet, a whole group, or
one market), sorted high-to-low, with a ticket builder and suggested 2-5 leg tickets. It is a
statistics app — probabilities, not certainties — covering every Mozzart market that can be settled
from half-time and full-time scores. Next goal: show Mozzart's actual price next to our fair odds.

## Locations

- Repo: `/home/nikola/code/Work/football-picks-v2` (GitHub `Podmorski/football-picks-v2`, PUBLIC, `main`).
- Python venv: `/home/nikola/.venvs/picks-v2` (Python 3.12). Node 24. Next.js app in `web/` (static export).
- Live: https://football-picks-v2.vercel.app — Vercel project `football-picks-v2`, Root Directory `web`,
  GitHub connected (push to `main` deploys). Repo secret `VERCEL_DEPLOY_HOOK`: `update.yml` POSTs it
  after a data commit by `github-actions[bot]`. Never print secrets or tokens.
- v1 project `/home/nikola/code/Work/Betting` is READ-ONLY reference (on hold). Never modify it.

## Environment quirks

- No file-creation tool: create with `printf 'PLACEHOLDER\n' > path`, then fill with `edit_file`.
- Terminal cannot `cd` inside a command: use the working-directory option or
  `env -C /home/nikola/code/Work/football-picks-v2 ...`; git via `git -C <repo> ...`.
- No shell substitutions (`$VAR`, `$(...)`, backticks, `<(...)`).
- `npx vercel deploy --prod` is blocked; `--environment production` works. Do NOT bypass permission
  rules (no `--dangerously-skip-permissions` or similar) — if blocked, STOP and ask.
- Vercel CLI deploys must run from the **repo root** (Root Directory is `web`); running from `web/`
  fails with "Root Directory web does not exist". Use `VERCEL_ORG_ID`/`VERCEL_PROJECT_ID` from
  `web/.vercel/project.json` when there is no root link.
- Screenshots: Playwright with `--no-save` only, and only if `ldd` on chrome-headless-shell shows no
  "not found" (currently libnspr4/libnss3/libnssutil3/libasound missing → skip). Screenshots go to
  "/mnt/c/Users/Nikola/Desktop/Zed Backup/screens/", never into the repo.

## Timing guards (no pushes)

- Sat/Sun 04:30-10:00, Tue 12:30-18:00, Fri 14:30-21:30 UTC. The step-0 price dispatches are exempt.

## Hard rules

- Never commit raw downloaded CSVs (`data/raw/` is gitignored). Commit code and derived JSON only.
- Mozzart prices are NEVER committed to the public GitHub repo.
- Downloads: https://football-data.co.uk/ (no www), User-Agent
  `football-picks-v2 (+https://github.com/Podmorski/football-picks-v2)`, ≥ 1 s between requests,
  past seasons cached.
- Model inputs use only matches before the fixture date; odds inputs use PRE-MATCH columns only
  (never closing columns `PSC*`/`AvgC*`/`B365C*`).
- Never publish a synthetic round to production. A round file with picks is never edited (only
  settled). An empty round file is replaced when fixtures appear.
- Never leave `main` broken: pytest and `npm run build` green before each push.
- Footer: "Data: football-data.co.uk" and "Predictions are probabilities, not certainties. 18+
  BeGambleAware.org".
- No paid services, no new data sources unless a task says so.

## Owner decisions (do not reverse)

- No favourites flag or switch. No forced 1.70 floor. No 5-10 / 10+ bands on the dashboard.
- Stand-out, Best combos and By play views were removed; do not bring them back.
- Higher-paying bets are wanted; heavy short-priced favourites are not the goal.

## Architecture: data → model → calibration → ranking → round files → site

1. **Data** — `pipeline/download.py` + `pipeline/run.py` fetch 22 main football-data.co.uk divisions
   (E0–EC, SC0–SC3, D1–D2, I1–I2, SP1–SP2, F1–F2, N1, B1, P1, T1, G1) with HT scores and pre-match
   odds, seasons 2015-16 onward (`pipeline/leagues.yaml`). 16 "extra" leagues (`new/*.csv`) are
   FT-only, stats only, no round picks. Only divisions present in `fixtures.csv` get round picks.
2. **Model** — `pipeline/model/` per-division, odds-anchored Dixon-Coles goals engine per half
   (`goals_engine.py`); every market is priced from one half-score grid (`grid.py`). Tuning and
   decisions live in `pipeline/model/decisions.json` (half_life_days 365, k 20).
3. **Calibration** — `pipeline/model/empirical.py` computes league / home-at-home / away-at-away
   rates for all markets; `pipeline/model/ranking_backtest.py` fits a multiplicative factor per
   ranking × group × minimum-odds level, walk-forward, and writes `model.json`.
4. **Picker** — `pipeline/ranking.py` builds every one of the 178 markets per fixture with the model
   probability, league rate and a calibrated `pc` (group × 20-80% band, walk-forward from
   `pipeline/model/picker_backtest.py`; `picker.json` also carries the per-season factors). The
   dashboard sorts by probability and keeps "vs league usual" as a column. An odds floor (`?min=`,
   default 1.50) is applied to fair odds before the best-per-match pick; there is no >80% rule.
5. **Round files** — `picks/YYYY-MM-DD.json` (compact: fixtures once + array rows). Published and
   settled by `run_model.py`; future rounds carry every market. The already-published 21/22 Nov
   rounds are never edited; their all-market companions are `picks/<date>.full.json`, verified on the
   model fields (19,076/19,076 and 6,810/6,810 identical, 0 different).
6. **Site** — `web/` (Next.js static export) reads `web/public/data/*.json`. Dashboard = the live
   **vetted list** (`vetting.DEFAULT_RULE`: C1 0.45, C2-C4, C6; C7 flag): Round, League, Bet (Any / a
   group / one market, default Any bet). "Best bets this round" = passing picks, one per match, sorted
   by probability, Strong (>= 55%) / Possible; card shows Mozzart vs fair (red below fair), check ticks,
   result/score, details (team records n, league usual n, goal ladder). Empty state names the filter and
   the 3 closest candidates with the failed check. "Only where Mozzart pays at least fair" (`?mozzart=1`).
   Tickets are built only from passing picks (target 3/5/10). The old odds floor, Show filter and sort
   are gone; Leagues/Record/Rounds/Tickets are small links. Record: picker calibration, combos, Mozzart
   return, and "Record at Mozzart prices" (all passing / passing+value / any value, return CI).
7. **Mozzart prices (private)** — `pipeline/mozzart/` fetches one pass per round (Sat 08:00, Tue
   16:00 UTC) into the **private** repo `Podmorski/football-picks-prices` (`rounds/`, `frozen/`,
   `record.json`, `usage.json`). The v2 hard cap is 90 requests/month; it refuses when the provider
   reports < 60 left. At build time `web/scripts/fetch-prices.mjs` clones the private repo over SSH
   (deploy key in Vercel env `PRICES_SSH_KEY`, `PRICED=1` in Production) and writes the gitignored
   `mozzart-prices.json` / `mozzart-record.json`. Prices are never committed to the public repo.
   Production is protected by Vercel Authentication (`ssoProtection: all`).

## Schedule (update.yml, UTC)

- Tue 10:00, 14:00, 16:00 — Tuesday round retries.
- Fri 15:00, 18:00, 21:00 — publish BOTH weekend rounds when their fixtures exist.
- Sat 05:00, 08:00; Sun 05:00, 08:00 — weekend retries.
- Mon 12:00 — settle only (settles both weekend rounds), never publish.
- Round days are Tuesday, Saturday and Sunday; Friday is never a round day.
- `prices.yml`: Sat/Sun 05:00, 06:30, 08:00, 09:30; Tue 13:00, 14:30, 16:00, 17:30 — one pass per
  round. A round that already has a snapshot exits with 0 requests; fixtures kicking off within 20 min
  of the fetch are marked started and not priced.

## Current state

- Milestone 5b. Picker calibration factors are walk-forward per target season (2019-20..2025-26 +
  the live 2026-27 factors fitted on all prior seasons); `picker.json` exposes `season_factors` and
  the combo backtest uses them. The Record picker table was already walk-forward and is unchanged.
- Odds floor `?min=` (default 1.50) is applied to fair odds before the best-per-match pick; the
  Any-bet >80% rule is gone. Target-payout tickets (`?target=`, `?legs=`) replace the best 2-5
  suggestions; the combo backtest is per target × max legs, one ticket per round date across all
  divisions playing that date (walk-forward, floor 1.50), with a return 95% CI bootstrapped over dates.
- 21 Nov (122 fixtures, 19,076 rows) and 22 Nov (44 fixtures, 6,810 rows) are published; companions
  (`picks/*.full.json`) add 2,640 / 1,022 market rows and are verified on the model fields.
- Dashboard UI (5d): top 10 + Show all (N = matches), per-match view (`?match=`), per-leg/ticket
  results on target tickets, and "Suggested tickets — past rounds" with per-target tallies.
- Settle runs now also settle `picks/<date>.full.json` companions (the dashboard reads them), and
  `rebuild_index` ignores `*.full.json` (no duplicate rounds). The example round is restricted to the
  22 main divisions, so the FT-only extra leagues never enter picks, match lists or tickets.
- Prices (Sat 21 Nov): the scheduled Sat 08:00 `prices.yml` run did not fire (GitHub's scheduler
  delayed the Fri update runs to 23:26/02:00); the first kickoff was 10:30, under the 2 h guard, so it
  was not dispatched. The private store is empty, the prebuild embeds 0 snapshots, site 302.
- Prices (21 Nov): the 09:51 first pass was cut to 1 page by the rate-limit header
  (`X-RateLimit-Limit=1, X-RateLimit-Remaining=0, X-RateLimit-Reset=1` — 1 req/s). The client now
  waits/reset with up to 3 retries and ignores rate-limit signals as quota. A 10:06 completion fetch
  merged 93 priced fixtures (the first T1 price kept, new fixtures stamped 10:06), 29 unmatched,
  0 started; 20 pages, budget 21/90. Aliases were added for the 29 unmatched names (future fetches
  only; 21 Nov is not re-fetched).
- Vetting engine: `pipeline/vetting.py` has C1-C12 as pure checks (C7 a flag, never a filter) and a
  `DEFAULT_RULE` (C1 0.45, C2-C4, C6, C7 flag). The dashboard is now the live vetted list using that
  rule; the old picker UI is unused. **Cancelled**: the Stage A/B rule backtest and C9 (there is no
  xG/AxG in the football-data.co.uk CSVs; coverage is 0).
- `/explore` keeps the pre-M6 M4/M5 picker (filters, sorting, Show all, odds floor, match
  view, tickets, past-ticket results); the FIX TASK removed its main-list Mozzart labels. Top nav is
  "Best bets | Explore". The Best bets page has a "Minimum fair odds" dropdown (1.40/1.70/2.00, URL
  `?min=`, default 1.70) applied before the per-match best; on 21 Nov that gives 71/54/19 passing
  matches at 1.40/1.70/2.00.
- Record has "Record at Mozzart prices" (all passing / passing+value / any value; per round and
  cumulative; return at the Mozzart price with a CI bootstrapped over round dates). It is empty until
  settled rounds carry frozen prices.
- Production is private (Vercel Authentication; 302), priced (`PRICED=1` + read-only `vercel-read`).
- 231 tests passing. `npm run build` green (49 pages).
- Rounds fixes (21 Nov): `web/lib/vetted.ts` is now the single selection used by Best bets and
  `/rounds` (`DEFAULT_RULE`, min fair 1.70, one passing pick per match, highest probability).
  `/rounds` dedupes by date, reads the `*.full.json` companion first (the page does), and shows
  "Results pending" until a row is landed/lost. `index.json` was regenerated (3 rounds, one per
  date). Under that rule the 14 Nov example is 8 of 21 landed; 21 Nov is 54 passing picks, all
  pending; 22 Nov is 15 passing, all pending. The old "13 of 15 landed" was the 14 Nov example
  under the superseded top-15/pc>0.8 rule.
- Mozzart surfaces: Best bets and Explore no longer show the Mozzart price, vs-fair label, red
  flags, "Only where Mozzart pays..." toggle or C7 tick on the main lists. The price appears only
  in the tap-open details (Best bets card details, Explore row expansion, per-match drill-down).
  Price fetching and "Record at Mozzart prices" are unchanged. `tests/test_explore.py` pins the new
  `Picker.tsx` hash; the pin was updated because this task required the Explore label cleanup. The
  ticket calculator at the bottom of a page is treated as an opened detail surface and still shows
  combined Mozzart/payout.
- Screenshots run in GitHub Actions via `screens.yml` (workflow_dispatch plus workflow_run after CI on
  main, i.e. after a deploy): ubuntu runner, `npx playwright install --with-deps chromium`, build
  `web/` without the price file, serve `web/out`, capture 1280x800 and 390x844 PNGs of Best bets (latest
  round), Best bets with Bet=HT/FT, one card opened, Explore, /rounds, /report and /tickets, upload the
  `screens` artifact with 3-day retention. Screenshots are never committed. Local Playwright is still
  blocked by the four missing system libraries.
- Task 8 (21 Nov): Correct score is hidden from the Best bets and Explore UI (dropdowns, lists,
  match views, tickets) but stays in `markets.py` / `markets.json` and Record history.
  `web/lib/vetted.ts` exposes `isHiddenMarketId` (prefix `CORRECT_SCORE:`) and both pickers filter it.
- Two rules: `ANY_RULE` (alias of `DEFAULT_RULE`, used when Bet = Any bet) and `TYPE_RULE` (used when
  a group or one market is chosen). TYPE_RULE has no probability floor and no minimum odds: lift
  `p >= usual x 1.25` and `p >= usual + 3 pts`; home-at-home and away-at-away records each >= usual
  with n >= 8; `|model - empirical| <= max(5 pts, 0.25 x p)`; `fair <= 6.00`. The two definitions live in
  `pipeline/vetting.py` (`type_evaluate`) and `web/lib/vetting.ts` (`evaluateTypeCandidate`).
  `lift = pc / league usual` and is displayed only. A group shows one passing bet per match with the
  highest probability, a single market every passing fixture; both sort by probability. Strong under
  TYPE_RULE is the top third (`ceil(n/3)`) of the displayed passing rows; under ANY_RULE it stays
  probability >= 55%. The min-fair-odds selector is hidden when a type rule is active.
- Bet dropdown counts (Best bets): each group and single-market option shows the number of matches
  passing TYPE_RULE for the current round + league, e.g. `HT/FT (36)`. Zero-count options stay
  selectable and show the empty state plus up to 3 closest candidates with the failed check and value.
  On 21 Nov (all leagues) the group counts are Combos 27, HT/FT 23, Goals 11, BTTS 9, Half-time 37,
  Team goals 41, Result & double chance 24.
- `/report` (49th page) shows: (a) the TYPE_RULE group backtest from
  `web/public/data/type_backtest.json` (walk-forward goals model and empirical rates before every round,
  calibration from `picker.json` season factors, seasons 2019-20..2025-26, one pick per match per group
  by highest probability, return at fair odds, 95% CI over round dates, 2000 resamples, seed 20261025);
  (b) Best bets ANY_RULE results per settled round and cumulative from
  `web/public/data/best-bets-record.json`, rebuilt by `pipeline/report.py` after every `run_model` pass
  (including the Monday settle): passing, settled, landed, expected and the Strong/Possible split;
  (c) Record at Mozzart prices (cumulative aggregates from `mozzart-vetted-record.json`) and price
  status (per-round priced/matched/unmatched, monthly requests vs 90, last price run) from
  `mozzart-status.json`, both embedded only in the priced build; (d) a Last updated time. Top nav is
  Best bets | Explore | Report. Regenerate the TYPE_RULE table with half-life 365 after picker factors
  change:
  `python -c "import json; from pathlib import Path; from pipeline.config import RAW_DIR, WEB_DATA_DIR, load_divisions, load_extras; from pipeline.run import cached_seasons; from pipeline.run_model import load_by_division; from pipeline.model import type_backtest; d=load_divisions(); by=load_by_division(RAW_DIR,d,load_extras(),cached_seasons(RAW_DIR)); f=json.loads((WEB_DATA_DIR/'picker.json').read_text())['season_factors']; type_backtest.write({l.code: by.get(l.code,[]) for l in d}, 365.0, WEB_DATA_DIR/'type_backtest.json', f)`.
  Explore keeps its M4/M5 picker behaviour; only the correct-score removal applies there.
- Cards/colours (21 Nov): Best bets cards and opened details have no check ticks or condition chips;
  Strong/Possible are neutral badges. Green is used only for Landed, red only for Lost, grey for
  Pending/Void (Best bets and Explore).
- Failure alerts: `pipeline/alerts.py` makes `update.yml` fail when a round has fixtures but nothing was
  published or settling found results but changed nothing (return 3 from `run_model`), and makes
  `prices.yml` fail when a price fetch priced < 50% of fixtures (return 5 from the CLI). `prices.yml`
  commits the private store with `if: always()` so a failed pass is still recorded; the deploy hook
  runs only on success.

## Open items

- **Rounds are pending by design**: 21 Nov (54 default passing picks) and 22 Nov (15) have no
  results until the Mon 12:00 settle; `/rounds` and Best bets show "Results pending" until then.
- **Record at Mozzart prices** fills after the 21/22 Nov settle (Mon 12:00) and the prices are frozen;
  21 Nov is 93/122 priced, 22 Nov pending. **Stage A/B backtest and C9 are cancelled** — do not
  reintroduce them; there is no xG/AxG in the data.
- **Recalibration**: `picker.json` and `combo.json` are recomputed once and committed. The combo
  backtest optimises one ticket per round date across all divisions playing that date. `type_backtest.json`
  is static too: regenerate it after recalibration so `/report` matches the live factors.
- **Screenshots**: artifact-only via `screens.yml`; locally Playwright remains blocked by the four
  missing system libraries.
