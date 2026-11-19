# AGENTS.md — football-picks-v2 handover

Read this first. It is the durable context for any worker on this repo.

## Product

Private web app that, for each Tuesday and Saturday round, ranks football bets by statistical
probability. For a chosen League and Bet type it shows the 15 strongest picks. It leans toward
higher-paying bets (combos, HT/FT, goal lines), not heavy short-priced favourites. It is a
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
- Screenshots: Playwright with `--no-save` only, and only if `ldd` on chrome-headless-shell shows no
  "not found" (currently libnspr4/libnss3/libnssutil3/libasound missing → skip). Screenshots go to
  "/mnt/c/Users/Nikola/Desktop/Zed Backup/screens/", never into the repo.

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
4. **Ranking** — `pipeline/ranking.py`: "Strongest lean" (default) = log-odds lift
   `logit(p) − logit(league rate shrunk to pooled rate by n/(n+20))`, lift ≥ 0.20, league n ≥ 200,
   tie-break p; "Most likely" = by p. Dashboard shows fair odds 1.50–4.00 only.
5. **Round files** — `picks/YYYY-MM-DD.json` (compact: fixtures once + array rows, ~800 KB for 45
   fixtures). Published and settled by `run_model.py`; only real fixtures from `fixtures.csv`.
6. **Site** — `web/` (Next.js static export) reads `web/public/data/*.json`. Dashboard: League, Bet
   (grouped), Minimum odds Any/2.00+/2.50+/3.00+ (`?minodds=`), Show filter; landed/lost/pending/void
   + HT/FT score; expanded row = goal ladder + "Other strong bets in this match"; `/rounds`; `/record`.

## Schedule (update.yml, UTC)

- Tue 14:00 + 16:00, Fri 18:00 + 21:00, Sat 08:00 — publish/settle.
- Mon 12:00 — settle only, never publish.
- First live round expected Sat 21 Nov 2026 (fixtures usually appear Friday).

## Current state

- Milestone 3e complete. Record page now reports the per-pick return at fair odds (mean, plus a
  95% CI bootstrapped over round dates, seed 20261025); the old "break-even" / "landed − BE"
  columns are gone. 113 tests passing. `npm run build` green (46 pages).
- Clean working tree on `main`; no live round published yet.

## Open items

- **M1 (in progress): Mozzart price feasibility** — read-only study of how v1 fetches Mozzart odds,
  budget, coverage, storage and a design for showing "Mozzart x.xx (time)" next to fair odds.
- Round check for Sat 21 Nov 2026 once the publish window opens.
