'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { MarketMeta, RankFile, RankRow } from '@/lib/types';

const BANDS = ['1.70-2.00', '2.00-3.00', '3.00-5.00', '5.00-10.00', '10.00+'];
const GROUPS = ['Combos', 'HT/FT', 'Goals', 'BTTS', 'Half-time', 'Team goals', 'Result & double chance', 'Correct score'];
const QUICK = [
  { key: 'any', label: 'Any' },
  { key: 'group:Combos', label: 'Combos' },
  { key: 'group:HT/FT', label: 'HT/FT' },
  { key: 'group:BTTS', label: 'BTTS' },
  { key: 'market:GOAL_RANGE_FT:2+', label: 'Over 2.5' },
  { key: 'group:Half-time', label: 'Goal in 1st half' },
];

function bandOf(fair: number): string {
  if (fair < 2) return '1.70-2.00';
  if (fair < 3) return '2.00-3.00';
  if (fair < 5) return '3.00-5.00';
  if (fair < 10) return '5.00-10.00';
  return '10.00+';
}

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
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
  const [band, setBand] = useParam('band', '2.00-3.00');
  const [rank, setRank] = useParam('rank', 'lean');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sheet, setSheet] = useState<'league' | 'bet' | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/data/rounds/${date}.json`)
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
              d: fixture.d,
              k: fixture.k,
              h: fixture.h,
              a: fixture.a,
              m: values[1],
              p: values[2],
              f: values[3],
              lr: values[4],
              ln: values[5],
              hr: values[6],
              hn: values[7],
              ar: values[8],
              an: values[9],
              c: values[10],
              s: values[11],
              ld: values[12],
              rs: values[13],
            } as RankRow;
          }) as RankRow[];
        }
        setData(payload);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'failed to load');
      });
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
  }, [date]);

  const leagueNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const [code, name] of leagueOptions) map[code] = name;
    return map;
  }, [leagueOptions]);

  const rows = data?.rows ?? [];

  const marketOptions = useMemo(() => {
    const seen = new Set<string>();
    for (const row of rows) seen.add(row.m);
    return Array.from(seen)
      .map((id) => [id, markets[id]?.plain ?? id] as [string, string])
      .sort((a, b) => a[1].localeCompare(b[1]));
  }, [rows, markets]);

  const picks = useMemo(() => {
    const filterLean = (row: RankRow) => row.ln >= 200 && row.lr > 0 && row.p >= row.lr * 1.1;
    let filtered = rows.filter((row) => bandOf(row.f) === band);
    if (league !== 'all') filtered = filtered.filter((row) => row.d === league);
    if (rank === 'lean') filtered = filtered.filter(filterLean);

    const sortRows = (items: RankRow[]) =>
      rank === 'lean'
        ? items.sort((a, b) => b.s - a.s || b.p - a.p)
        : items.sort((a, b) => b.p - a.p);

    if (bet.startsWith('market:')) {
      const id = bet.slice(7);
      return sortRows(filtered.filter((row) => row.m === id)).slice(0, 15);
    }
    if (bet.startsWith('group:')) {
      const group = bet.slice(6);
      filtered = filtered.filter((row) => (markets[row.m]?.group ?? '') === group);
    }
    const ordered = sortRows(filtered);
    const seen = new Set<string>();
    const out: RankRow[] = [];
    for (const row of ordered) {
      const key = `${row.h}|${row.a}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(row);
      if (out.length >= 15) break;
    }
    return out;
  }, [rows, league, bet, band, rank, markets]);

  const betLabel =
    bet === 'any'
      ? 'Any'
      : bet.startsWith('group:')
        ? bet.slice(6)
        : markets[bet.slice(7)]?.plain ?? 'Bet';

  return (
    <div className="space-y-4">
      <div className="space-y-2 rounded-xl border p-3">
        <div className="flex flex-wrap gap-1.5">
          {[
            { key: 'lean', label: 'Strongest lean' },
            { key: 'probability', label: 'Most likely' },
          ].map((option) => (
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
          <div className="flex flex-wrap gap-1">
            {BANDS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setBand(option)}
                className={cn(
                  'rounded-full border px-2.5 py-1 text-xs font-medium',
                  band === option ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground',
                )}
              >
                {option}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5">
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
        </div>
      </div>

      <p className="text-sm text-muted-foreground">
        {picks.length} {rank === 'lean' ? 'strongest leans' : 'most likely picks'} · {band} · {data?.fixtures ?? 0}{' '}
        matches checked in {data?.leagues ?? 0} leagues · {data?.label ?? date}
        {kind === 'example' ? ' · Example round' : ''}
      </p>

      {error ? <p className="text-sm text-destructive">Could not load the round: {error}</p> : null}
      {!data && !error ? <p className="text-sm text-muted-foreground">Loading the round…</p> : null}

      <ul className="divide-y rounded-xl border">
        {picks.map((row) => {
          const meta = markets[row.m];
          const key = `${row.h}|${row.a}|${row.m}`;
          const bandRow = data?.market_bands?.[`${meta?.group ?? ''}|${bandOf(row.f)}`];
          const open = expanded === key;
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
                </span>
                <span className="tabular shrink-0 text-right text-sm">
                  <span className="block font-semibold">{pct(row.p)}</span>
                  <span className="block text-xs text-muted-foreground">usual {pct(row.lr)}</span>
                </span>
                <span className="tabular hidden w-12 shrink-0 text-right text-sm text-muted-foreground sm:block">
                  {row.f.toFixed(2)}
                </span>
                <Badge
                  variant={row.c === 'High' ? 'success' : row.c === 'Medium' ? 'warning' : 'secondary'}
                  className="shrink-0"
                >
                  {row.c[0]}
                </Badge>
                <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
              </button>

              {open ? (
                <div className="mt-2 space-y-1 rounded-md bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                  <p>
                    This match {pct(row.p)} vs league usual {pct(row.lr)} (n={row.ln.toLocaleString('en-GB')}) · lean{' '}
                    {row.s.toFixed(2)}x
                  </p>
                  <p>
                    Home at home {pct(row.hr)} ({row.hn}) · away away {pct(row.ar)} ({row.an})
                  </p>
                  <p>Fair odds {row.f.toFixed(2)} · lands about 1 in {Math.max(1, Math.round(1 / row.p))}</p>
                  {bandRow ? (
                    <p>
                      Past picks like this: <span className="tabular text-foreground">{pct(bandRow.landed)}</span> of{' '}
                      {bandRow.n.toLocaleString('en-GB')} in {meta?.group} at {bandOf(row.f)}
                    </p>
                  ) : (
                    <p>Past history: not enough data for this group and price range yet.</p>
                  )}
                  {row.o ? <p>No pre-match odds: goals model used without odds anchoring.</p> : null}
                  {row.ld !== null && row.ld !== undefined ? (
                    <p>
                      Result: {row.rs} — {row.ld ? 'landed' : 'missed'}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      {data && picks.length === 0 ? (
        <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
          No play passes these filters in this price range.
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
        Bet: {betLabel}. Strongest lean = model probability divided by the league&apos;s usual rate, needing 1.10x and
        200+ league matches. One pick per match unless a single bet is chosen. Nothing under fair odds 1.70.
      </p>
    </div>
  );
}
