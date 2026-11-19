'use client';

import { useEffect, useMemo, useState } from 'react';
import { Check, ChevronDown, Minus, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
  buildPriceIndex,
  isOld,
  priceKey,
  signedPct,
  snapshotFor,
  utcTime,
  vsFairPct,
  type MozzartPricesFile,
} from '@/lib/prices';
import type { MarketMeta, RankFile, RankRow } from '@/lib/types';

const LEVELS = [
  { key: 'any', label: 'Any', low: 1.5 },
  { key: '2.00+', label: '2.00+', low: 2.0 },
  { key: '2.50+', label: '2.50+', low: 2.5 },
  { key: '3.00+', label: '3.00+', low: 3.0 },
];
const FAIR_MIN = 1.5;
const FAIR_MAX = 4.0;
const GROUPS = ['Combos', 'HT/FT', 'Goals', 'BTTS', 'Half-time', 'Team goals', 'Result & double chance', 'Correct score'];
const QUICK = [
  { key: 'any', label: 'Any' },
  { key: 'group:Combos', label: 'Combos' },
  { key: 'group:HT/FT', label: 'HT/FT' },
  { key: 'group:BTTS', label: 'BTTS' },
  { key: 'market:GOAL_RANGE_FT:2+', label: 'Over 2.5' },
  { key: 'group:Half-time', label: 'Goal in 1st half' },
];
const LADDER_LABELS: Record<string, string> = {
  'GOAL_RANGE_FT:1+': 'FT 1+ goals',
  'GOAL_RANGE_FT:2+': 'FT 2+ goals',
  'GOAL_RANGE_FT:3+': 'FT 3+ goals',
  'GOAL_RANGE_FT:4+': 'FT 4+ goals',
  'GOAL_RANGE_FT:5+': 'FT 5+ goals',
  'GOAL_RANGE_FT:0-1': 'Under 1.5',
  'GOAL_RANGE_FT:0-2': 'Under 2.5',
  'GOAL_RANGE_FT:0-3': 'Under 3.5',
  'GOAL_RANGE_1H:I1+': '1st half 1+',
  'GOAL_RANGE_1H:I2+': '1st half 2+',
  'BTTS:GG': 'Both teams score',
};

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function shownOf(row: RankRow, strategy: string): number {
  return strategy === 'lean' ? row.pl ?? row.p : row.pp ?? row.p;
}

function fairOf(row: RankRow, strategy: string): number {
  return 1 / Math.max(shownOf(row, strategy), 0.0001);
}

function useParam(key: string, initial: string): [string, (next: string) => void] {
  const [value, setValue] = useState(initial);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const found = params.get(key);
    if (found) setValue(found);
  }, [key]);
  function update(next: string) {
    setValue(next);
    const params = new URLSearchParams(window.location.search);
    params.set(key, next);
    window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`);
  }
  return [value, update];
}

const STATUS_VARIANT = { landed: 'success', lost: 'destructive', pending: 'secondary', void: 'outline' } as const;

function StatusBadge({ status }: { status: RankRow['st'] }) {
  const label = status === 'landed' ? 'Landed' : status === 'lost' ? 'Lost' : status === 'void' ? 'Void' : 'Pending';
  return (
    <Badge variant={STATUS_VARIANT[status] ?? 'secondary'} className="shrink-0">
      {status === 'landed' ? <Check className="h-3 w-3" /> : status === 'lost' ? <X className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
      {label}
    </Badge>
  );
}

export default function Dashboard({
  date,
  kind,
  leagueOptions,
}: {
  date: string;
  kind: string;
  leagueOptions: [string, string, string][];
}) {
  const [data, setData] = useState<RankFile | null>(null);
  const [markets, setMarkets] = useState<Record<string, MarketMeta>>({});
  const [error, setError] = useState<string | null>(null);
  const [league, setLeague] = useParam('league', 'all');
  const [bet, setBet] = useParam('bet', 'any');
  const [minOdds, setMinOdds] = useParam('minodds', 'any');
  const [rank, setRank] = useParam('rank', 'lean');
  const [show, setShow] = useParam('show', 'all');
  const [mozzart, setMozzart] = useParam('mozzart', '0');
  const [roundParam] = useParam('round', date);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sheet, setSheet] = useState<'league' | 'bet' | null>(null);
  const [prices, setPrices] = useState<MozzartPricesFile | null>(null);
  const [priced, setPriced] = useState(false);

  const activeDate = /^\d{4}-\d{2}-\d{2}$/.test(roundParam) ? roundParam : date;

  useEffect(() => {
    let cancelled = false;
    setData(null);
    fetch(`/data/rounds/${activeDate}.json`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((payload: RankFile & { fixture_list?: { d: string; k: string | null; h: string; a: string }[] }) => {
        if (cancelled) return;
        const raw = payload.rows as unknown as (RankRow | unknown[])[];
        if (raw.length && Array.isArray(raw[0])) {
          const fixtures = payload.fixture_list ?? [];
          payload.rows = (raw as unknown[][]).map((values) => {
            const fixture = fixtures[values[0] as number];
            return {
              d: fixture.d, k: fixture.k, h: fixture.h, a: fixture.a,
              m: values[1], p: values[2], pl: values[3], pp: values[4],
              lr: values[5], ln: values[6], hr: values[7], hn: values[8],
              ar: values[9], an: values[10], c: values[11], s: values[12],
              st: values[13], ht: values[14], ft: values[15],
            } as RankRow;
          }) as RankRow[];
        }
        setData(payload);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'failed to load');
      });
    return () => {
      cancelled = true;
    };
  }, [activeDate]);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/markets.json')
      .then((response) => (response.ok ? response.json() : { markets: [] }))
      .then((payload: { markets: MarketMeta[] }) => {
        if (cancelled) return;
        const map: Record<string, MarketMeta> = {};
        for (const market of payload.markets ?? []) map[market.id] = market;
        setMarkets(map);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/mozzart-prices.json')
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: MozzartPricesFile | null) => {
        if (cancelled) return;
        setPrices(payload);
        setPriced(payload !== null);
      })
      .catch(() => {
        if (!cancelled) {
          setPrices(null);
          setPriced(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const leagueNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const [code, name] of leagueOptions) map[code] = name;
    return map;
  }, [leagueOptions]);

  const rows = data?.rows ?? [];
  const priceIndex = useMemo(() => buildPriceIndex(prices, activeDate), [prices, activeDate]);
  const snapshot = useMemo(() => snapshotFor(prices, activeDate), [prices, activeDate]);

  const marketOptions = useMemo(() => {
    const seen = new Set<string>();
    for (const row of rows) seen.add(row.m);
    return Array.from(seen)
      .map((id) => [id, markets[id]?.plain ?? id] as [string, string])
      .sort((a, b) => a[1].localeCompare(b[1]));
  }, [rows, markets]);

  const { pool, picks } = useMemo(() => {
    const levelLow = LEVELS.find((level) => level.key === minOdds)?.low ?? FAIR_MIN;
    let filtered = rows.filter((row) => {
      const fair = fairOf(row, rank);
      return fair >= Math.max(FAIR_MIN, levelLow) && fair <= FAIR_MAX;
    });
    if (league !== 'all') filtered = filtered.filter((row) => row.d === league);
    if (rank === 'lean') filtered = filtered.filter((row) => row.ln >= 200 && row.s >= 0.2);
    if (bet.startsWith('market:')) {
      const id = bet.slice(7);
      filtered = filtered.filter((row) => row.m === id);
    } else if (bet.startsWith('group:')) {
      const group = bet.slice(6);
      filtered = filtered.filter((row) => (markets[row.m]?.group ?? '') === group);
    }
    if (show !== 'all') filtered = filtered.filter((row) => row.st === show);
    if (mozzart === '1') {
      filtered = filtered.filter((row) => {
        const price = priceIndex[priceKey(row.d, row.h, row.a, row.m)];
        return price !== undefined && price.odds > fairOf(row, rank);
      });
    }

    const sorted = [...filtered].sort((a, b) =>
      rank === 'lean' ? b.s - a.s || shownOf(b, rank) - shownOf(a, rank) : shownOf(b, rank) - shownOf(a, rank),
    );
    const top: RankRow[] = [];
    if (bet.startsWith('market:')) {
      return { pool: sorted, picks: sorted.slice(0, 15) };
    }
    const seen = new Set<string>();
    for (const row of sorted) {
      const key = `${row.h}|${row.a}`;
      if (seen.has(key)) continue;
      seen.add(key);
      top.push(row);
      if (top.length >= 15) break;
    }
    return { pool: sorted, picks: top };
  }, [rows, league, bet, minOdds, rank, show, markets, mozzart, priceIndex]);

  const settled = picks.filter((row) => row.st === 'landed' || row.st === 'lost');
  const landed = picks.filter((row) => row.st === 'landed').length;
  const expected = settled.reduce((total, row) => total + shownOf(row, rank), 0);

  const betLabel =
    bet === 'any'
      ? 'Any'
      : bet.startsWith('group:')
        ? bet.slice(6)
        : markets[bet.slice(7)]?.plain ?? 'Bet';

  const levelLabel = LEVELS.find((level) => level.key === minOdds)?.label ?? 'Any';

  return (
    <div className="space-y-4">
      <div className="space-y-2 rounded-xl border p-3">
        <div className="flex flex-wrap gap-1.5">
          {[{ key: 'lean', label: 'Strongest lean' }, { key: 'probability', label: 'Most likely' }].map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setRank(option.key)}
              className={cn(
                'rounded-md border px-3 py-1.5 text-sm font-medium',
                rank === option.key ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap gap-2">
          <select
            value={league}
            onChange={(event) => setLeague(event.target.value)}
            aria-label="League"
            className="hidden max-w-[16rem] rounded-md border bg-background px-2 py-1.5 text-sm sm:block"
          >
            <option value="all">All leagues</option>
            {leagueOptions.map(([code, name, country]) => (
              <option key={code} value={code}>
                {country} — {name}
              </option>
            ))}
          </select>
          <select
            value={bet}
            onChange={(event) => setBet(event.target.value)}
            aria-label="Bet"
            className="hidden max-w-[18rem] rounded-md border bg-background px-2 py-1.5 text-sm sm:block"
          >
            <option value="any">Any bet</option>
            {GROUPS.map((group) => (
              <optgroup key={group} label={group}>
                <option value={`group:${group}`}>{group} (all)</option>
                {marketOptions
                  .filter(([id]) => markets[id]?.group === group)
                  .map(([id, plain]) => (
                    <option key={id} value={`market:${id}`}>
                      {plain}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
          <div className="flex gap-1 sm:hidden">
            <button type="button" onClick={() => setSheet('league')} className="rounded-md border px-2 py-1.5 text-sm">
              League
            </button>
            <button type="button" onClick={() => setSheet('bet')} className="rounded-md border px-2 py-1.5 text-sm">
              Bet
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-xs text-muted-foreground">Min odds</span>
            {LEVELS.map((level) => (
              <button
                key={level.key}
                type="button"
                onClick={() => setMinOdds(level.key)}
                className={cn(
                  'rounded-full border px-2.5 py-1 text-xs font-medium',
                  minOdds === level.key ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground',
                )}
              >
                {level.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {QUICK.map((chip) => (
            <button
              key={chip.key}
              type="button"
              onClick={() => setBet(chip.key)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium',
                bet === chip.key ? 'border-primary bg-accent text-accent-foreground' : 'text-muted-foreground',
              )}
            >
              {chip.label}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-border" />
          {['all', 'landed', 'lost'].map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setShow(option)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium capitalize',
                show === option ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground',
              )}
            >
              {option === 'all' ? 'Show all' : option}
            </button>
          ))}
          {priced ? (
            <button
              key="mozzart"
              type="button"
              onClick={() => setMozzart(mozzart === '1' ? '0' : '1')}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium',
                mozzart === '1' ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground',
              )}
            >
              Only where Mozzart pays more than fair
            </button>
          ) : null}
        </div>
      </div>

      <p className="text-sm text-muted-foreground">
        {picks.length} {rank === 'lean' ? 'strongest leans' : 'most likely picks'} · min odds {levelLabel} ·{' '}
        {data?.fixtures ?? 0} matches checked in {data?.leagues ?? 0} leagues · {data?.label ?? date}
        {kind === 'example' ? ' · Example round' : ''}
      </p>

      {settled.length > 0 ? (
        <p className="text-sm">
          Result: <span className="font-medium">{landed} of {settled.length} landed</span> · expected about{' '}
          {expected.toFixed(1)}
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">Results appear after the matches (usually by Monday)</p>
      )}

      {error ? <p className="text-sm text-destructive">Could not load the round: {error}</p> : null}
      {!data && !error ? <p className="text-sm text-muted-foreground">Loading the round…</p> : null}

      <ul className="divide-y rounded-xl border">
        {picks.map((row) => {
          const meta = markets[row.m];
          const key = `${row.h}|${row.a}|${row.m}`;
          const percent = shownOf(row, rank);
          const open = expanded === key;
          const ladderRows = data?.ladder ?? [];
          const fixtureRows = rows.filter((candidate) => candidate.h === row.h && candidate.a === row.a);
          const ladder = ladderRows.map((id) => fixtureRows.find((candidate) => candidate.m === id)).filter(Boolean) as RankRow[];
          const siblings = pool.filter((candidate) => candidate.h === row.h && candidate.a === row.a && candidate.m !== row.m).slice(0, 3);
          const price = priceIndex[priceKey(row.d, row.h, row.a, row.m)];
          const pricedFixture = snapshot?.fixtures.find((fixture) => fixture.div === row.d && fixture.home === row.h && fixture.away === row.a) ?? null;
          const stale = price ? isOld(price.fetchedAt, pricedFixture?.kickoff ?? null) : false;
          return (
            <li key={key} className="px-3 py-2.5">
              <button type="button" onClick={() => setExpanded(open ? null : key)} className="flex w-full items-center gap-3 text-left">
                <span className="w-10 shrink-0 text-xs text-muted-foreground">{row.k ?? ''}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {row.h} <span className="text-muted-foreground">v</span> {row.a}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {leagueNames[row.d] ?? row.d} · {meta?.plain ?? row.m}{' '}
                    <span className="opacity-70">({meta?.mozzart ?? ''})</span>
                  </span>
                  {priced ? (
                    price ? (
                      <span className="tabular block text-xs text-muted-foreground">
                        Mozzart {price.odds.toFixed(2)} · {utcTime(price.fetchedAt)}
                        {stale ? ' · old' : ''} ·{' '}
                        <span className="font-medium text-foreground">
                          vs fair {signedPct(vsFairPct(price.odds, fairOf(row, rank)))}
                        </span>
                      </span>
                    ) : (
                      <span className="block text-xs text-muted-foreground">no Mozzart price</span>
                    )
                  ) : null}
                  {row.st !== 'pending' && row.ht !== null ? (
                    <span className="tabular block text-xs text-muted-foreground">
                      HT {row.ht} · FT {row.ft}
                    </span>
                  ) : row.ft ? (
                    <span className="tabular block text-xs text-muted-foreground">FT {row.ft}</span>
                  ) : null}
                </span>
                <span className="tabular shrink-0 text-right text-sm">
                  <span className="block font-semibold">{pct(percent)}</span>
                  <span className="block text-xs text-muted-foreground">usual {pct(row.lr)}</span>
                </span>
                <span className="tabular hidden w-12 shrink-0 text-right text-sm text-muted-foreground sm:block">
                  {(1 / percent).toFixed(2)}
                </span>
                <StatusBadge status={row.st} />
                <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
              </button>

              {open ? (
                <div className="mt-2 space-y-3 rounded-md bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                  <div>
                    <p>
                      This match {pct(percent)} (model {pct(row.p)}) vs league usual {pct(row.lr)}{' '}
                      (n={row.ln.toLocaleString('en-GB')}) · lift {row.s.toFixed(2)}
                    </p>
                    <p>
                      Home at home {pct(row.hr)} ({row.hn}) · away away {pct(row.ar)} ({row.an})
                    </p>
                    <p>
                      Fair odds {(1 / percent).toFixed(2)} · lands about 1 in {Math.max(1, Math.round(1 / percent))}
                    </p>
                    {priced ? (
                      <p>
                        Mozzart {price ? `${price.odds.toFixed(2)} · ${utcTime(price.fetchedAt)}` : 'no price'}
                        {price ? ` · vs fair ${signedPct(vsFairPct(price.odds, fairOf(row, rank)))}` : ''}
                      </p>
                    ) : null}
                  </div>

                  <div>
                    <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">Goal ladder</h4>
                    <ul className="grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
                      {ladder.map((line) => (
                        <li
                          key={line.m}
                          className={cn(
                            'flex items-baseline justify-between gap-2 rounded px-1',
                            line.m === row.m && 'bg-accent/60 font-medium text-foreground',
                          )}
                        >
                          <span>{LADDER_LABELS[line.m] ?? line.m}</span>
                          <span className="tabular">
                            {pct(line.p)} <span className="text-xs">· usual {pct(line.lr)} ({line.ln})</span>{' '}
                            <span className="text-xs">· {(1 / line.p).toFixed(2)}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {siblings.length > 0 ? (
                    <div>
                      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">Other strong bets in this match</h4>
                      <ul className="space-y-0.5">
                        {siblings.map((sibling) => (
                          <li key={sibling.m} className="flex items-baseline justify-between gap-2">
                            <span>{markets[sibling.m]?.plain ?? sibling.m}</span>
                            <span className="tabular">
                              {pct(shownOf(sibling, rank))} · {(1 / shownOf(sibling, rank)).toFixed(2)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {row.st === 'void' ? <p>Void — no settlement possible for this fixture.</p> : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      {data && picks.length === 0 ? (
        <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
          No play passes these filters at this minimum odds.
        </p>
      ) : null}

      {sheet ? (
        <div className="fixed inset-0 z-40 flex items-end bg-black/40 sm:hidden" onClick={() => setSheet(null)}>
          <div className="max-h-[75vh] w-full overflow-y-auto rounded-t-2xl bg-background p-4" onClick={(event) => event.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold">{sheet === 'league' ? 'League' : 'Bet'}</h3>
              <button type="button" onClick={() => setSheet(null)} className="text-sm text-muted-foreground">Close</button>
            </div>
            {sheet === 'league' ? (
              <select value={league} onChange={(event) => setLeague(event.target.value)} className="w-full rounded-md border bg-background px-2 py-2 text-sm">
                <option value="all">All leagues</option>
                {leagueOptions.map(([code, name, country]) => (
                  <option key={code} value={code}>
                    {country} — {name}
                  </option>
                ))}
              </select>
            ) : (
              <select value={bet} onChange={(event) => setBet(event.target.value)} className="w-full rounded-md border bg-background px-2 py-2 text-sm">
                <option value="any">Any bet</option>
                {GROUPS.map((group) => (
                  <optgroup key={group} label={group}>
                    <option value={`group:${group}`}>{group} (all)</option>
                    {marketOptions
                      .filter(([id]) => markets[id]?.group === group)
                      .map(([id, plain]) => (
                        <option key={id} value={`market:${id}`}>
                          {plain}
                        </option>
                      ))}
                  </optgroup>
                ))}
              </select>
            )}
            <button type="button" onClick={() => setSheet(null)} className="mt-4 w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
              Show picks
            </button>
          </div>
        </div>
      ) : null}

      <p className="text-xs text-muted-foreground">
        Bet: {betLabel}. Percentages are calibrated on held-out seasons. Strongest lean ranks by log-odds lift over
        the league&apos;s usual rate (0.20 minimum, 200+ league matches). Only fair odds 1.50–4.00 are shown; one pick
        per match unless a single bet is chosen.
      </p>
    </div>
  );
}
