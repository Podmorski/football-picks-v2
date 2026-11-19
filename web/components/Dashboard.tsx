'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

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

type Row = {
  div: string;
  league: string;
  kickoff: string | null;
  home: string;
  away: string;
  market: string;
  family: string;
  group: string;
  mozzart: string;
  plain: string;
  probability: number;
  fair_odds: number;
  league_rate: number;
  band: string;
  confidence: 'High' | 'Medium' | 'Low';
  no_odds: boolean;
  landed?: boolean | null;
  result?: string;
};

type RoundFile = {
  date: string;
  label: string;
  fixtures: number;
  leagues: number;
  rows: Row[];
  market_bands?: Record<string, { landed: number; shown: number; n: number }>;
};

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
  const [data, setData] = useState<RoundFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [league, setLeague] = useParam('league', 'all');
  const [bet, setBet] = useParam('bet', 'any');
  const [band, setBand] = useParam('band', '2.00-3.00');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sheet, setSheet] = useState<'league' | 'bet' | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/data/rounds/${date}.json`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((payload: RoundFile) => {
        if (!cancelled) setData(payload);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'failed to load');
      });
    return () => {
      cancelled = true;
    };
  }, [date]);

  const rows = data?.rows ?? [];

  const marketOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const row of rows) if (!seen.has(row.market)) seen.set(row.market, row.plain);
    return Array.from(seen.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [rows]);

  const picks = useMemo(() => {
    let filtered = rows.filter((row) => row.band === band);
    if (league !== 'all') filtered = filtered.filter((row) => row.div === league);
    if (bet.startsWith('market:')) {
      const id = bet.slice(7);
      return filtered.filter((row) => row.market === id).sort((a, b) => b.probability - a.probability).slice(0, 15);
    }
    if (bet.startsWith('group:')) {
      const group = bet.slice(6);
      filtered = filtered.filter((row) => row.group === group);
    }
    filtered = filtered.sort((a, b) => b.probability - a.probability);
    const seen = new Set<string>();
    const out: Row[] = [];
    for (const row of filtered) {
      const key = `${row.home}|${row.away}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(row);
      if (out.length >= 15) break;
    }
    return out;
  }, [rows, league, bet, band]);

  const betLabel =
    bet === 'any' ? 'Any' : bet.startsWith('group:') ? bet.slice(6) : marketOptions.find(([id]) => id === bet.slice(7))?.[1] ?? 'Bet';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 rounded-xl border p-3">
        <select
          value={league}
          onChange={(event) => setLeague(event.target.value)}
          className="hidden rounded-md border bg-background px-2 py-1.5 text-sm sm:block"
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
          className="hidden rounded-md border bg-background px-2 py-1.5 text-sm sm:block"
        >
          <option value="any">Any bet</option>
          {GROUPS.map((group) => (
            <optgroup key={group} label={group}>
              <option value={`group:${group}`}>{group} (all)</option>
              {marketOptions
                .filter(([id]) => rows.find((row) => row.market === id)?.group === group)
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

      <p className="text-sm text-muted-foreground">
        {picks.length} most likely picks · {band} · {data?.fixtures ?? 0} matches checked in {data?.leagues ?? 0} leagues ·{' '}
        {data?.label ?? date}
        {kind === 'example' ? ' · Example round' : ''}
      </p>

      {error ? <p className="text-sm text-destructive">Could not load the round: {error}</p> : null}
      {!data && !error ? <p className="text-sm text-muted-foreground">Loading the round…</p> : null}

      <ul className="divide-y rounded-xl border">
        {picks.map((row) => {
          const key = `${row.home}|${row.away}|${row.market}`;
          const bandRow = data?.market_bands?.[`${row.group}|${row.band}`];
          const open = expanded === key;
          return (
            <li key={key} className="px-3 py-2.5">
              <button type="button" onClick={() => setExpanded(open ? null : key)} className="flex w-full items-center gap-3 text-left">
                <span className="w-10 shrink-0 text-xs text-muted-foreground">{row.kickoff ?? ''}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {row.home} <span className="text-muted-foreground">v</span> {row.away}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {row.league} · {row.plain} <span className="opacity-70">({row.mozzart})</span>
                  </span>
                </span>
                <span className="tabular shrink-0 text-sm font-semibold">{pct(row.probability)}</span>
                <span className="tabular hidden w-12 shrink-0 text-right text-sm text-muted-foreground sm:block">
                  {row.fair_odds.toFixed(2)}
                </span>
                <Badge
                  variant={row.confidence === 'High' ? 'success' : row.confidence === 'Medium' ? 'warning' : 'secondary'}
                  className="shrink-0"
                >
                  {row.confidence[0]}
                </Badge>
                <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
              </button>

              {open ? (
                <div className="mt-2 space-y-1 rounded-md bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                  <p>League usual: <span className="tabular text-foreground">{pct(row.league_rate)}</span></p>
                  <p>Fair odds {row.fair_odds.toFixed(2)} · lands about 1 in {Math.max(1, Math.round(1 / row.probability))}</p>
                  {bandRow ? (
                    <p>
                      Past picks like this: <span className="tabular text-foreground">{pct(bandRow.landed)}</span> of{' '}
                      {bandRow.n.toLocaleString('en-GB')} in {row.group} at {row.band}
                    </p>
                  ) : (
                    <p>Past history: not enough data for this group and price range yet.</p>
                  )}
                  {row.no_odds ? <p>No pre-match odds: goals model used without odds anchoring.</p> : null}
                  {row.landed !== null && row.landed !== undefined ? (
                    <p>Result: {row.result} — {row.landed ? 'landed' : 'missed'}</p>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      {data && picks.length === 0 ? (
        <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
          No play in this price range for these filters.
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
                      .filter(([id]) => rows.find((row) => row.market === id)?.group === group)
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
        Bet: {betLabel}. One pick per match unless a single bet is chosen. Nothing under fair odds 1.70 is shown.
      </p>
    </div>
  );
}
