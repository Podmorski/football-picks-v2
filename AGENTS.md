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
6. **Site** — `web/` (Next.js static export) reads `web/public/data/*.json`. Best bets = the live
   list: Any bet uses ANY_RULE; a group or single market uses Ranked — all candidates by default, or
   optional Strict checks only (TYPE_RULE exactly). Round, League, Bet (Any / group / market), minimum
   fair odds: Any bet defaults to 1.70; group and single-market views default to Any odds when the URL
   has no explicit min; 1.40/1.70/2.00/2.50 remain available. Ranked group = one candidate per match
   by highest displayed probability; a single market = every eligible fixture; both sorted by
   probability. Strict = TYPE_RULE one pick per match. Strong = probability >= 55% in every Best bets
   view; Possible otherwise. Cards show probability, fair, min play (`ceil_2dp(1.05/p)`),
   Strong/Possible and a Value badge; the Mozzart price appears only in the opened details. Counts
   follow the current league, mode and minimum odds; zero states distinguish no candidates, min-odds
   filtering (with Show all odds) and strict zero (with Show ranked candidates and the
   highest-probability failed checks). Opened group details list all Ranked (or strict-passing) group
   options for the match, with neutral diagnostics and Pass / Does not pass. Correct score is hidden.
   Tickets and Value are unchanged. Top nav is Best bets | Value bets | Explore | Report; Record/Report
   cover calibration, combos, Mozzart returns and value tracking; Report's TYPE_RULE table is the
   STRICT_checks cohort, not Ranked.
7. **Mozzart prices (private)** — `pipeline/mozzart/` fetches one pass per round (Sat 08:00, Tue
   16:00 UTC) into the **private** repo `Podmorski/football-picks-prices` (`rounds/`, `frozen/`,
   `record.json`, `usage.json`). The v2 hard cap is 90 requests/month; it refuses when the provider
   reports < 60 left. At build time `web/scripts/fetch-prices.mjs` clones the private repo over SSH
   (deploy key in Vercel env `PRICES_SSH_KEY`, `PRICED=1` in Production) and writes the gitignored
   `mozzart-prices.json` / `mozzart-record.json`. Prices are never committed to the public repo.
   Production is protected by Vercel Authentication (`ssoProtection: all`).

## Schedule (update.yml, UTC)

- Tue 10:00, 14:00, 16:00 — Tuesday round retries; Wed 06:00, 12:00 — Tuesday settlement retries.
- Fri 15:00, 18:00, 21:00 — publish BOTH weekend rounds when their fixtures exist.
- Sat 05:00, 08:00; Sun 05:00, 08:00 — weekend retries.
- Sun 12:00, 18:00 — settle-only retries for Saturday and every earlier eligible round.
- Mon 06:00, 12:00 — settle only (Sunday, Saturday and every earlier eligible round), never publish.
- Round days are Tuesday, Saturday and Sunday; Friday is never a round day. Every run also attempts every
  eligible past round; missing football-data results stay Pending for the next retry rather than becoming void.
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
  settled rounds carry frozen prices. Both `vetted_record.py` and `value_record.py` key prices by
  `(round_date, div, home, away, market)`, so a repeated fixture uses only its own round's snapshot;
  historical snapshots are used as-is (no migration or refetch).
- Production is private (Vercel Authentication; 302), priced (`PRICED=1` + read-only `vercel-read`).
- 262 tests passing. `npm run build` green (50 pages).
- Rounds fixes (21 Nov): `web/lib/vetted.ts` is now the single selection used by Best bets and
  `/rounds` (`DEFAULT_RULE`, min fair 1.70, one passing pick per match, highest probability).
  `/rounds` dedupes by date, reads the `*.full.json` companion first (the page does), and shows
  "Results pending" until a row is landed/lost. `index.json` was regenerated (3 rounds, one per
  date). Under that rule the 14 Nov example is 10 of 26 landed; 21 Nov is 70 passing picks, all
  pending; 22 Nov is 19 passing, all pending. The old "13 of 15 landed" was the 14 Nov example
  under the superseded top-15/pc>0.8 rule.
- Mozzart surfaces: Best bets and Explore no longer show the Mozzart price, vs-fair label, red
  flags, "Only where Mozzart pays..." toggle or C7 tick on the main lists. The price appears only
  in the tap-open details (Best bets card details, Explore row expansion, per-match drill-down).
  Price fetching and "Record at Mozzart prices" are unchanged. `tests/test_explore.py` pins the new
  `Picker.tsx` hash; the pin was updated because this task required the Explore label cleanup. The
  ticket calculator at the bottom of a page is treated as an opened detail surface and still shows
  combined Mozzart/payout.
- Screenshots: the PUBLIC `screens.yml` builds WITHOUT prices and never checks out the private repo;
  its `screens` artifact is unpriced (the Value page shows its unpriced empty state). Priced
  screenshots run in the PRIVATE repo `Podmorski/football-picks-prices` workflow `screens.yml`: it
  checks out the public repo read-only, builds with `PRICED=1` and `PRICES_LOCAL_DIR` (the private
  checkout), captures the same pages including /value at 1280x800 and 390x844, and uploads the
  `screens-priced` artifact with 3-day retention. Screenshots are never committed. Local Playwright is
  still blocked by the four missing system libraries.
- Privacy (21 Nov): all public `screens` artifacts were deleted (6, priced). The public workflow is
  unpriced; the 34 public runs in the previous 24h and the full public git history contain no price
  values or committed Mozzart price files. Priced screenshots are artifact-only in the private repo.
- Task 8 (21 Nov): Correct score is hidden from the Best bets and Explore UI (dropdowns, lists,
  match views, tickets) but stays in `markets.py` / `markets.json` and Record history.
  `web/lib/vetted.ts` exposes `isHiddenMarketId` (prefix `CORRECT_SCORE:`) and both pickers filter it.
- Two rules: `ANY_RULE` (alias of `DEFAULT_RULE`, used when Bet = Any bet) and `TYPE_RULE` (used when
  a group or one market is chosen). TYPE_RULE has no probability floor and no minimum odds: lift
  `p >= usual x 1.25` and `p >= usual + 3 pts`; home-at-home and away-at-away records each >= usual
  with n >= 8; `|model - empirical| <= max(5 pts, 0.25 x p)` where empirical is the team-based count
  estimate (home-at-home and away-at-away, each shrunk to the league usual by n/(n+20), then
  averaged), not the league usual; `fair <= 6.00`. The two definitions live in
  `pipeline/vetting.py` (`type_evaluate`) and `web/lib/vetting.ts` (`evaluateTypeCandidate`).
  `lift = pc / league usual` and is displayed only. A group shows one passing bet per match with the
  highest probability, a single market every passing fixture; both sort by probability. Strong under
  TYPE_RULE is the top third (`ceil(n/3)`) of the displayed passing rows; under ANY_RULE it stays
  probability >= 55%. The min-fair-odds selector is hidden when a type rule is active.
- Bet dropdown counts (Best bets): each group and single-market option shows the number of matches
  passing TYPE_RULE for the current round + league, e.g. `HT/FT (36)`. Zero-count options stay
  selectable and show the empty state plus up to 3 closest candidates with the failed check and value.
  Counts reflect the min-fair dropdown (default 1.70). On 21 Nov (all leagues) the group counts are
  Combos 45, HT/FT 46, Goals 18, BTTS 14, Half-time 45, Team goals 54, Result & double chance 31.
- `/report` (49th page) shows: (a) the TYPE_RULE group backtest from
  `web/public/data/type_backtest.json` (walk-forward goals model and empirical rates before every round,
  calibration from `picker.json` season factors, seasons 2019-20..2025-26, one pick per match per group
  by highest probability, return at fair odds, 95% CI over round dates, 2000 resamples, seed 20261025);
  (b) Best bets ANY_RULE results per settled round and cumulative from
  `web/public/data/best-bets-record.json`, rebuilt by `pipeline/report.py` after every `run_model` pass
  (including the Monday settle): passing, settled, landed, expected and the Strong/Possible split;
  (c) Record at Mozzart prices (cumulative aggregates from `mozzart-vetted-record.json`) and price
  status (per-round priced/matched/unmatched, monthly requests vs 90, last price run) from
  `mozzart-status.json`, both embedded only in the priced build; (d) a Last updated time; (e) Value
  tracking from `value-record.json`. Top nav is Best bets | Value bets | Explore | Report. Regenerate the TYPE_RULE table with half-life 365 after picker factors
  change:
  `python -c "import json; from pathlib import Path; from pipeline.config import RAW_DIR, WEB_DATA_DIR, load_divisions, load_extras; from pipeline.run import cached_seasons; from pipeline.run_model import load_by_division; from pipeline.model import type_backtest; d=load_divisions(); by=load_by_division(RAW_DIR,d,load_extras(),cached_seasons(RAW_DIR)); f=json.loads((WEB_DATA_DIR/'picker.json').read_text())['season_factors']; type_backtest.write({l.code: by.get(l.code,[]) for l in d}, 365.0, WEB_DATA_DIR/'type_backtest.json', f)`.
  Explore keeps its M4/M5 picker behaviour; only the correct-score removal applies there.
- Reporting: weekly reporting is automatic via `/report` (rebuilt by every `run_model` pass, including
  the Monday settle); screenshots via `screens.yml` (artifact only, never committed).
- Cards/colours (21 Nov): Best bets cards and opened details have no check ticks or condition chips;
  Strong/Possible are neutral badges. Green is used only for Landed, red only for Lost, grey for
  Pending/Void (Best bets and Explore). The Value badge is amber; min play text is neutral.
- Task 9 (21 Nov): agreement "empirical" is the team-based count estimate (`team_empirical` in
  `pipeline/vetting.py`, `teamEmpirical` in `web/lib/vetting.ts`): home-at-home and away-at-away, each
  shrunk to the league usual by n/(n+20), then averaged. C4 and T4 use it; card details label it
  "team empirical". Before/after group counts on 21 Nov (league usual -> team empirical, no min fair):
  Combos 27->51, HT/FT 23->55, Goals 11->20, BTTS 9->14, Half-time 37->53, Team goals 41->64,
  Result & DC 24->51. With the default min fair 1.70 the dropdown counts are 45/46/18/14/45/54/31.
- Min fair odds is shown in every Bet view (Any, group, single market): 1.40/1.70/2.00/2.50, URL
  `?min=`, default 1.70, applied before the per-match best; dropdown counts reflect it. Dropdowns are
  full width on mobile; round buttons are oldest-left; /report says "Walk-forward over
  2019-20..2025-26" and footnotes "highest probability".
- Min play: `min_play = ceil_2dp(1.05 / p)` (floating-point-safe epsilon). Every Best bets card and
  Explore row shows "Play only at odds >= X.XX"; the opened card adds "needs N in 10 at that price;
  our chance P%". Neutral colour. Value rows are those with Mozzart >= min_play.
- Value bets (`/value`, top nav "Value bets"): Mozzart snapshot price >= min_play, team records and
  agreement pass, fair <= 6; one per match by highest edge `price x p - 1`, sorted edge. Amber Value
  badge. The Best bets ticket builder has "Value legs only" (default ON) and shows combined min play.
- Value tracking: `pipeline/mozzart/value_record.py` runs in `update.yml` after `run_model` (the
  workflow checks out the private store as `prices-private`). It writes
  `web/public/data/value-record.json` (aggregates only): bets, landed, needed (sum 1/price), profit
  units, return, 95% CI over round dates (2000, seed 20261025), split by group and odds band, cumulative
  profit series. `/report` renders it. It is empty until the 21/22 Nov settle. The settled cohort matches
  the web `selectValue` exactly: t3 team records, t4 agreement and t6 fair <= 6; t1 lift is not required
  and the UI min-fair dropdown is not applied; min_play and fair <= 6 apply, one per match by highest
  edge, sorted by edge.
- Task 11 (21 Nov): fixed two reporting defects. (a) `value_record.py` selected the complete TYPE_RULE
  (including t1 lift) while the web Value selection used only t3/t4/t6; the pipeline now matches the web
  contract (t1 not required, no min-fair dropdown, min_play + fair <= 6, one per match highest edge,
  sorted edge). (b) both `value_record.py` and `vetted_record.py` keyed prices by fixture/market without
  the round date; both now key by `(round_date, div, home, away, market)`. Tests in
  `tests/test_value_record.py` and `tests/test_vetted_record.py` include the web contract source check,
  t1=false inclusion, each required-check exclusion, min-play/fair-cap exclusions, one-per-match/edge
  ordering, pending/void/unpriced semantics and two-date price isolation.
- Task 12 (21 Nov): Best bets and Value distinguish loading, fetch failure, unpriced build, no snapshot
  for the active round, snapshot-but-no-qualifying bets, and available bets. Best bets stays usable
  without prices; the price state is a separate note, and league/group counts depend only on round +
  markets, not prices. Round headings/labels/kind come from the active client round via `roundMeta`
  (including a directly linked example not in the buttons); page h1s are generic (`Best bets`,
  `Value bets`, `Explore`). Empty states are factual (no candidates / none at the minimum fair odds /
  `0 of N candidates passed` with `Highest-probability candidates that failed`). Strong/Possible
  definitions sit beside the Best bets list. How-it-works, Record and Report copy is current
  (Tuesday/Saturday/Sunday, division coverage, minimum playable odds, Mozzart snapshots, unproven
  Value); Report's single TYPE_RULE research table is labelled before the UI minimum-fair filter,
  highest probability and fair-odds returns. ComboRecord's Mozzart footnote is conditional.
- Validation limits (21 Nov): local Playwright remains blocked by the four missing system libraries.
  The state/round-identity/label contracts are source- and build-tested and captured in the private
  priced screenshots; delayed-fetch, keyboard, mobile interactions, the Ranked/Strict toggles, the
  all-options match details and the odds reset were not exercised locally.
- Task 13 (21 Nov): Best-bets group/single-market views are market-first. Ranked — all candidates is
  the default; Strict checks only is optional and is the existing TYPE_RULE exactly. Ranked applies
  only league + visible minimum odds, then group one-per-match by highest displayed probability /
  single market every eligible fixture, sorted by probability; no TYPE_RULE gate. Correct score stays
  hidden. Strong is probability >= 55% in every Best-bets view (top-third removed). The min control has
  Any odds; group/market default any odds when the URL has no min, Any bet defaults 1.70, explicit
  numeric minima are preserved. Counts follow league + mode + min odds; min-odds zero shows the
  available count and Show all odds; strict zero shows Show ranked candidates and the
  highest-probability failed checks. Opened group details list all Ranked (or strict-passing) options
  per match, plus neutral diagnostics (league usual/lift, team records, team empirical/agreement, fair,
  Pass / Does not pass). Report's TYPE_RULE table is the STRICT_checks cohort, not Ranked; Ranked
  profitability is not established.
- Task 14 (21 Nov): the complete Ranked/Strict walk-forward audit is
  `pipeline/model/ranked_backtest.py`, with synthetic contracts in `tests/test_ranked_backtest.py` and
  aggregate-only output in `web/public/data/ranked_backtest.json`. It uses the same 22 divisions,
  2019-20..2025-26, Tuesday/Saturday/Sunday rounds, half-life 365, pre-round goals/empirical fitting and
  `picker.json` target-season factors as the TYPE_RULE backtest. Displayed probability is calibrated `pc`
  (raw p × group/band factor, clipped to .001-.999), fair is `1/pc`, and raw p is used only by t4. Any odds
  means no floor. Strict reproduced every compared field in `type_backtest.json` exactly before the file
  was written. Ranked is one highest-pc candidate per match; Strict is one highest-pc passing candidate;
  the separate rejected diagnostic is EVERY settleable visible candidate failing Strict before selection,
  not a strategy or paired causal cohort. Return CIs use 2000 date-cluster bootstrap draws, seed 20261025.
  Full run: 9m03s, Strict parity exact; 42,904/42,939 eligible fixtures per group depending on HT coverage.
  Strict fixture coverage is Combos 37.98%, HT/FT 42.30%, Goals 13.96%, BTTS 4.37%, Half-time 34.59%,
  Team goals 43.24%, Result & DC 36.17%. Ranked landed/predicted is respectively
  .5893/.5883, .6814/.6821, .9353/.9324, .8077/.8115, .8865/.8872, .8035/.7994, .7724/.7717;
  Strict is .5011/.4922, .5366/.5373, .4043/.3987, .3601/.3739, .5510/.5483, .5487/.5489,
  .6094/.6027. The rejected candidate cohorts are 94.75%-99.28% of eligible candidates by group and
  their predicted-minus-landed differences range from -0.88 to +0.17 percentage points. Strict therefore
  removes substantial coverage without a consistent calibration improvement; this is descriptive, not a
  causal or profitability conclusion. Non-exclusive t1/t3/t4/t6 counts, fixture counts, sample sizes,
  outcomes and all fair-return CIs are in the JSON; t1 and t3 are the broadest checks, and overlaps matter.
  All 31 visible HT/FT-group markets are reported separately as secondary exploratory cohorts, including
  zero-selection Strict markets and small-sample warnings. Seven have zero Strict selections; the Strict
  HTFT_COMBO:X-1&ng, X-2&ng and HTFT_DC:X2-1X cohorts have only 44, 2 and 30 selections. Do not cherry-pick
  the positive fair-return tails across these multiple comparisons. HT/FT realised historical return is
  not measurable from current data.
  Exact historical actual-bookmaker mappings are only RESULT:1/X/2 -> Bet365 PRE-MATCH B365H/D/A,
  GOAL_RANGE_FT:3+ -> B365>2.5 and GOAL_RANGE_FT:0-2 -> B365<2.5. No average/closing/similar-market or
  Mozzart substitution. No primary Ranked cohort has a mapped selected row, so its realised return is
  unknown. Strict Goals has 1,487 priced of 5,996 selections (24.80%), actual-subset return +0.68%,
  95% CI -2.96%..+4.49%; Strict Result & DC has 4,639 of 15,531 (29.87%), -3.05%, CI -5.69%..-0.18%.
  These are priced subsets, not whole-group realised returns. Other markets lack exact historical prices.
  Fair-odds return is model-price accounting, never evidence of positive expected value by itself.
  Regenerate the complete audit (no season/division shortening) with
  `/home/nikola/.venvs/picks-v2/bin/python -m pipeline.model.ranked_backtest` from the repo root. It refuses
  to write if Strict parity differs. The site does not read `ranked_backtest.json`; no selection, rule,
  threshold, UI, workflow, price or existing generated-data behaviour was changed.
- Task 15 (22 Nov): automatic next-day settlement uses `run_model --settle-only` and the shared
  `settle_round_files` path for every eligible past round and its `.full.json` companion. Only `st`, `ht`
  and `ft` may change; same-day/future rounds are never settled, real rounds are never regenerated as
  examples, and `pipeline.run` preserves existing team `upcoming` predictions until a normal publish run
  replaces them. Missing football-data results stay Pending (`SOURCE PENDING`) for the next retry; an
  available FT result can still void only HT-dependent rows. Source-backed rows still Pending after a
  pass alert/fail, including partial settlement. Index, public Record/Report and the workflow's Value
  record use the existing rebuild/commit/deploy-hook path. New settle-only cron retries are Sun 12:00
  and 18:00, Mon 06:00 and Wed 06:00/12:00 UTC; Mon 12:00 remains settle-only and every other update
  also attempts every earlier eligible round. Focused schedule/settlement/alert tests: 15 passing.
  Full validation: 281 pytest tests passing; `npm run build` green (50 pages).
  Live verification after the Sunday guard: the normal download made 39 requests and refreshed all 22
  current-season main files, but the latest main-division result date was still 16 Nov with no 21 Nov
  results. Saturday therefore changed 0 landed / 0 lost / 0 void and left all 40,792 main+companion
  rows Pending across 122 fixtures. No timestamp-only data commit was made; Sun 12:00/18:00 remain
  the next trusted retries.
- Task 16 (22 Nov): opened match details now show descriptive HT/FT history from
  `pipeline/descriptive.py`, generated as sidecars in `web/public/data/descriptive/YYYY-MM-DD.json`.
  Cutoff is strict: completed matches before the fixture date only; same-day/later results and missing FT
  rows never count. Each team gets overall and venue-specific last-6/last-12 windows with actual n
  (never padded), W/D/L, goals and per-match rates, 3/1/0 points, BTTS and over-2.5 frequencies, FT/HT
  `1/X/2` frequencies (historical match perspective) and all nine HT/FT frequencies (HT-applicable n).
  Streaks run from the most recent completed match backwards and are 0 when the latest result does not
  satisfy: win, unbeaten, winless, losing, drawing, BTTS, no-BTTS, over-2.5, under-2.5, overall and
  venue-specific. H2H covers prior loaded main-division league meetings: total n and current-home W/D/L,
  goals, BTTS/over-2.5, plus up to 6 recent dates/scores; reversed home/away meetings use the current
  home perspective. No H2H and n=0 rates are available-data states (`null`), never zero chances.
  Sidecar schema is `schema_version: 1`, `definitions_version: descriptive-v1`, with no generated
  timestamp; identical inputs produce byte-identical JSON. `run_model` backfills every indexed round
  after settlement and before index/report rebuilding, so published round files and companions are read
  only and never modified. Coverage: 14 Nov 48 fixtures, 21 Nov 122, 22 Nov 44. `MatchStats.tsx` is the
  single shared component embedded only inside opened details in Best bets and Explore, with independent
  loading/error/unavailable states. Frequencies are labelled historical, not calibrated chances. No
  probability, Ranked/Strict, dropdown, ticket, price, settlement, ranking or filter behaviour changes;
  these statistics do not currently influence rankings.
- Task 17 (23 Nov): 23 additional score-settleable candidates are defined research-only in
  `pipeline/model/additional_markets.py`; they are NOT registered in `markets.py`. Nineteen are unique;
  four requested HT/FT+BTTS candidates (`1-X&gg`, `1-2&gg`, `2-1&gg`, `2-X&gg`) are logically exact
  duplicates of existing `HTFT:1-X`, `1-2`, `2-1`, `2-X` and are excluded from the augmented registry.
  The impossible NG counterparts remain absent. Candidate ids use existing groups only: HT/FT or Combos.
  Catalogue evidence uses the existing read-only v1 Mozzart snapshot dated 24 Sep 2026; no private
  checkout was available locally and no Mozzart request or budget was used. Snapshot-confirmed are
  `RESULT_AND_BTTS:1&gg`, `2&gg`, `DC_AND_BTTS:1X&gg`, `X2&gg`, `BTTS_AND_GOALS:GG&3+` and
  `HTFT_AND_GOALS:X-X&3+`; the other 17 remain unconfirmed or technically blocked. The full
  walk-forward audit in `pipeline/model/additional_market_backtest.py` uses the same 22 divisions,
  2019-20..2025-26, round schedule, half-life 365, pre-round goals/empirical fitting and existing
  target-season picker factors, without refitting or closing odds. It writes aggregate-only
  `web/public/data/additional_markets_backtest.json` (29,398 bytes): every candidate's selections,
  dates, landed/raw-pc calibration, median fair odds, fair return and 2000-date bootstrap CI, plus
  descriptive Ranked-group impact. Full run: 5m43s, 303 MiB peak, 23/23 candidate cohorts. All candidates
  have 42,904 or 42,939 selections over 891 dates and are not small-sample. Combos selection changes on
  2,904/42,939 fixtures (6.76%; additional winners `NG&0-2` 2,882, `1X&ng` 20, `X2&ng` 2); HT/FT changes
  none. Changed selections: current landed .4735 / mean pc .4642; augmented .4793 / .4965. This is
  descriptive, not an improvement or profit claim. Every candidate's realised historical bookmaker
  return is not measurable from current data. Positive fair-return tails are multiple comparisons and
  must not drive activation. Nothing is activated in rounds/UI; production selections, rounds,
  calibration, prices, workflows and existing backtests are unchanged. Regenerate with
  `/home/nikola/.venvs/picks-v2/bin/python -m pipeline.model.additional_market_backtest` from the repo
  root. Activation still requires current-catalogue confirmation and owner review.
- Failure alerts: `pipeline/alerts.py` makes `update.yml` fail when a round has fixtures but nothing was
  published or settling found results but changed nothing (return 3 from `run_model`), and makes
  `prices.yml` fail when a price fetch priced < 50% of fixtures (return 5 from the CLI). `prices.yml`
  commits the private store with `if: always()` so a failed pass is still recorded; the deploy hook
  runs only on success.

## Open items

- **Ranked audit complete; realised profitability remains mostly unmeasured**: Task 14's aggregate
  `ranked_backtest.json` covers Ranked, Strict, rejected-candidate diagnostics and exploratory HT/FT
  markets with fair-return CIs. It is research output only, not presented by the site as a strategy.
  Fair-odds returns are not realised profit; no primary Ranked cohort has exact historical bookmaker
  coverage, and HT/FT actual returns are not measurable from current data. Do not select an optimal
  group/check from observed returns or make causal claims from the different cohorts.

- **Rounds await source results**: football-data had no 21 Nov results after the Sun 10:00 refresh;
  all 40,792 Saturday main+companion rows remain Pending across 122 fixtures (0 landed/lost/void).
  Sunday's round is not eligible until Monday. Sun 12:00/18:00, Mon 06:00/12:00 and later runs retry
  automatically; `/rounds` and Best bets show "Results pending" until trusted results arrive.
- **Record at Mozzart prices / Value tracking** fill after the 21/22 Nov settle (Mon 12:00) and the
  prices are frozen; 21 Nov is 93/122 priced, 22 Nov pending. The Value record is rebuilt by the next
  `update.yml` pass. **Stage A/B backtest and C9 are cancelled** — do not reintroduce them; there is
  no xG/AxG in the data.
- **Recalibration**: `picker.json` and `combo.json` are recomputed once and committed. The combo
  backtest optimises one ticket per round date across all divisions playing that date. `type_backtest.json`
  is static too: regenerate it after recalibration so `/report` matches the live factors.
- **Screenshots**: public `screens` artifacts are unpriced; priced screenshots are artifact-only in
  the private repo's `screens.yml`. Locally Playwright remains blocked by the four missing system
  libraries.
