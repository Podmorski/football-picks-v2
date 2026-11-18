'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, SlidersHorizontal } from 'lucide-react';

import RoundList from '@/components/RoundList';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { BandStat, ByPlayFile, ByPlayRow, PlayLeagueRow, RoundDocument, RoundView } from '@/lib/types';

const BANDS = [
  { key: 'any', label: 'Any' },
  { key: '1.50-2.00', label: '1.50–2.00' },
  { key: '2.00-3.00', label: '2.00–3.00' },
  { key: '3.00-5.00', label: '3.00–5.00' },
  { key: '5.00+', label: '5.00+' },
];

const GROUPS = ['Combos', 'Total goals', 'Over/Under', 'BTTS', 'Half goals', 'Team goals', 'HT result', 'HT/FT', 'Double chance', 'FT result', 'More goals', 'Odd/Even'];

function oddsBand(probability: number): string {
  const odds = probability > 0 ? 1 / probability : 999;
  if (odds < 2) return '1.50-2.00';
  if (odds < 3) return '2.00-3.00';
  if (odds < 5) return '3.00-5.00';
  return '5.00+';
}

function pct(value: number | null | undefined) {
  return value === null || value === undefined ? '–' : `${(value * 100).toFixed(1)}%`;
}

function useUrlParam(key: string, initial: string): [string, (next: string) => void] {
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

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
        active ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  );
}

export default function RoundExplorer({
  round,
  bandStats,
}: {
  round: RoundDocument;
  bandStats: BandStat[];
}) {
  const [mode, setMode] = useUrlParam('mode', 'top15');
  const [view, setView] = useUrlParam('view', 'most_likely');
  const [band, setBand] = useUrlParam('band', 'any');
  const [group, setGroup] = useUrlParam('group', 'Combos');
  const [sortBy, setSortBy] = useUrlParam('sort', 'probability');
  const [play, setPlay] = useState('all');
  const [league, setLeague] = useState('all');
  const [sheet, setSheet] = useState(false);

  const [byPlay, setByPlay] = useState<ByPlayFile | null>(null);
  const [playLeagues, setPlayLeagues] = useState<Record<string, PlayLeagueRow[]>>({});
  const [error, setError] = useState<string | null>(null);

  const views: Record<string, RoundView> =
    round.views ?? { most_likely: { label: 'Most likely', picks: round.picks ?? [], hits: 0, settled_count: 0 } };

  useEffect(() => {
    if (mode !== 'byplay' || byPlay) return;
    let cancelled = false;
    fetch(`/data/by-play/${round.date}.json`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data: ByPlayFile) => {
        if (!cancelled) setByPlay(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'failed to load');
      });
    return () => {
      cancelled = true;
    };
  }, [mode, byPlay, round.date]);

  useEffect(() => {
    if (mode !== 'byplay' || Object.keys(playLeagues).length) return;
    let cancelled = false;
    fetch('/data/play-leagues.json')
      .then((response) => (response.ok ? response.json() : { outcomes: {} }))
      .then((data: { outcomes: Record<string, PlayLeagueRow[]> }) => {
        if (!cancelled) setPlayLeagues(data.outcomes ?? {});
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [mode, playLeagues]);

  const bandStat = useMemo(() => {
    const map: Record<string, BandStat> = {};
    for (const row of bandStats) map[`${row.outcome}|${row.band}`] = row;
    return map;
  }, [bandStats]);

  const filteredPicks = (views[view]?.picks ?? []).filter(
    (pick) => band === 'any' || oddsBand(pick.probability) === band,
  );

  const rows = useMemo(() => {
    if (!byPlay) return [];
    return byPlay.rows
      .filter((row) => row.group === group)
      .filter((row) => play === 'all' || row.outcome === play)
      .filter((row) => band === 'any' || row.band === band)
      .filter((row) => league === 'all' || row.div === league)
      .filter((row) => row.eligible)
      .sort((a, b) => (sortBy === 'lift' ? b.lift - a.lift : b.probability - a.probability));
  }, [byPlay, group, play, band, league, sortBy]);

  const playOptions = useMemo(() => {
    if (!byPlay) return [];
    const seen = new Map<string, string>();
    for (const row of byPlay.rows) {
      if (row.group === group && !seen.has(row.outcome)) seen.set(row.outcome, row.play);
    }
    return Array.from(seen.entries());
  }, [byPlay, group]);

  const leagueOptions = useMemo(() => {
    if (!byPlay) return [];
    const seen = new Map<string, string>();
    for (const row of byPlay.rows) seen.set(row.div, row.league);
    return Array.from(seen.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [byPlay]);

  const sideLeagues = play === 'all' ? [] : (playLeagues[play] ?? []).slice(0, 12);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg bg-muted p-1">
          <button
            type="button"
            onClick={() => setMode('top15')}
            className={cn('rounded-md px-3 py-1.5 text-sm font-medium', mode === 'top15' ? 'bg-background shadow-sm' : 'text-muted-foreground')}
          >
            Top 15
          </button>
          <button
            type="button"
            onClick={() => setMode('byplay')}
            className={cn('rounded-md px-3 py-1.5 text-sm font-medium', mode === 'byplay' ? 'bg-background shadow-sm' : 'text-muted-foreground')}
          >
            By play
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {BANDS.map((option) => (
            <Chip key={option.key} active={band === option.key} onClick={() => setBand(option.key)}>
              {option.label}
            </Chip>
          ))}
        </div>
      </div>

      {mode === 'top15' ? (
        <div className="space-y-6">
          <div className="flex flex-wrap gap-1.5">
            {['most_likely', 'stand_out']
              .filter((key) => views[key])
              .map((key) => (
                <Chip key={key} active={view === key} onClick={() => setView(key)}>
                  {views[key].label} ({views[key].picks.length})
                </Chip>
              ))}
          </div>

          <RoundList picks={filteredPicks} showLift={view === 'stand_out'} />

          {views.best_combos && views.best_combos.picks.length > 0 ? (
            <section className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold">Best combos this round</h2>
                <button
                  type="button"
                  onClick={() => {
                    setMode('byplay');
                    setGroup('Combos');
                  }}
                  className="text-sm text-primary underline underline-offset-2"
                >
                  See all combos →
                </button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {views.best_combos.picks.map((pick) => (
                  <div key={`${pick.home}-${pick.away}`} className="rounded-xl border p-3">
                    <p className="text-xs text-muted-foreground">{pick.league}</p>
                    <p className="text-sm font-semibold">
                      {pick.home} <span className="text-muted-foreground">v</span> {pick.away}
                    </p>
                    <p className="mt-1 text-sm">{pick.play}</p>
                    <div className="mt-2 flex items-center justify-between text-sm">
                      <span className="tabular font-semibold">{(pick.probability * 100).toFixed(1)}%</span>
                      <span className="text-muted-foreground">fair {pick.fair_odds.toFixed(2)}</span>
                      <Badge variant={pick.confidence === 'High' ? 'success' : pick.confidence === 'Medium' ? 'warning' : 'secondary'}>
                        {pick.confidence}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      ) : (
        <div className="space-y-3">
          {error ? <p className="text-sm text-destructive">Could not load the full play list: {error}</p> : null}
          {!byPlay && !error ? <p className="text-sm text-muted-foreground">Loading every play for this round…</p> : null}

          {byPlay ? (
            <>
              <div className="flex flex-wrap gap-1.5">
                {GROUPS.filter((name) => byPlay.rows.some((row) => row.group === name)).map((name) => (
                  <Chip
                    key={name}
                    active={group === name}
                    onClick={() => {
                      setGroup(name);
                      setPlay('all');
                    }}
                  >
                    {name}
                  </Chip>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {/* Desktop: inline selects. Mobile: bottom sheet trigger. */}
                <div className="hidden flex-wrap items-center gap-2 sm:flex">
                  <select
                    value={play}
                    onChange={(event) => setPlay(event.target.value)}
                    className="max-w-[16rem] rounded-md border bg-background px-2 py-1.5 text-sm"
                  >
                    <option value="all">All plays</option>
                    {playOptions.map(([id, label]) => (
                      <option key={id} value={id}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <select
                    value={league}
                    onChange={(event) => setLeague(event.target.value)}
                    className="max-w-[14rem] rounded-md border bg-background px-2 py-1.5 text-sm"
                  >
                    <option value="all">All leagues</option>
                    {leagueOptions.map(([code, name]) => (
                      <option key={code} value={code}>
                        {name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex gap-1.5">
                  <Chip active={sortBy === 'probability'} onClick={() => setSortBy('probability')}>
                    Most likely
                  </Chip>
                  <Chip active={sortBy === 'lift'} onClick={() => setSortBy('lift')}>
                    Stand-out
                  </Chip>
                </div>
                <button
                  type="button"
                  onClick={() => setSheet(true)}
                  className="ml-auto inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm sm:hidden"
                >
                  <SlidersHorizontal className="h-4 w-4" /> Filters
                </button>
              </div>

              <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
                <div className="overflow-x-auto rounded-xl border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                        <th className="px-2 py-2 text-left font-semibold">Match</th>
                        <th className="px-2 py-2 text-left font-semibold">Play</th>
                        <th className="px-2 py-2 text-right font-semibold">This</th>
                        <th className="px-2 py-2 text-right font-semibold">Usual</th>
                        <th className="px-2 py-2 text-right font-semibold">Fair</th>
                        <th className="px-2 py-2 text-right font-semibold">1 in</th>
                        <th className="px-2 py-2 text-right font-semibold">Past</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.slice(0, 60).map((row) => {
                        const past = bandStat[`${row.outcome}|${row.band}`];
                        return (
                          <tr key={`${row.home}-${row.away}-${row.outcome}`} className="border-t">
                            <td className="px-2 py-1.5">
                              <div className="font-medium whitespace-nowrap">
                                {row.home} v {row.away}
                              </div>
                              <div className="text-xs text-muted-foreground">{row.league}</div>
                            </td>
                            <td className="px-2 py-1.5">{row.play}</td>
                            <td className="tabular px-2 py-1.5 text-right font-medium">{(row.probability * 100).toFixed(1)}%</td>
                            <td className="tabular px-2 py-1.5 text-right text-muted-foreground">{(row.league_base * 100).toFixed(1)}%</td>
                            <td className="tabular px-2 py-1.5 text-right">{row.fair_odds.toFixed(2)}</td>
                            <td className="tabular px-2 py-1.5 text-right text-muted-foreground">
                              {Math.round(1 / Math.max(row.probability, 0.01))}
                            </td>
                            <td className="tabular px-2 py-1.5 text-right text-xs">
                              {past && past.picks >= 30 ? (
                                <span title={`${past.hits}/${past.picks}`}>{pct(past.hit_rate)}</span>
                              ) : (
                                <span className="text-muted-foreground">–</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {rows.length === 0 ? (
                    <p className="px-3 py-6 text-sm text-muted-foreground">No play matches these filters.</p>
                  ) : null}
                </div>

                <aside className="rounded-xl border p-3">
                  <h3 className="text-sm font-semibold">Leagues where this play lands most</h3>
                  {play === 'all' ? (
                    <p className="mt-2 text-sm text-muted-foreground">Pick a single play to see the leagues ranked by how often it lands.</p>
                  ) : sideLeagues.length === 0 ? (
                    <p className="mt-2 text-sm text-muted-foreground">Not enough history for this play.</p>
                  ) : (
                    <ul className="mt-2 space-y-1.5 text-sm">
                      {sideLeagues.map((leagueRow) => (
                        <li key={leagueRow.code} className="flex items-baseline justify-between gap-2">
                          <span className="truncate">
                            {leagueRow.name}
                            {leagueRow.ft_only ? <span className="ml-1 text-xs text-muted-foreground">FT only</span> : null}
                          </span>
                          <span className="tabular shrink-0 text-muted-foreground">
                            {(leagueRow.rate * 100).toFixed(1)}% <span className="text-xs">n={leagueRow.n}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </aside>
              </div>
            </>
          ) : null}
        </div>
      )}

      {/* Mobile bottom sheet */}
      {sheet ? (
        <div className="fixed inset-0 z-40 flex items-end bg-black/40 sm:hidden" onClick={() => setSheet(false)}>
          <div className="max-h-[75vh] w-full overflow-y-auto rounded-t-2xl bg-background p-4" onClick={(event) => event.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold">Filter plays</h3>
              <button type="button" onClick={() => setSheet(false)} className="text-sm text-muted-foreground">
                Close
              </button>
            </div>
            <label className="mb-1 block text-xs text-muted-foreground">Play</label>
            <select
              value={play}
              onChange={(event) => setPlay(event.target.value)}
              className="mb-3 w-full rounded-md border bg-background px-2 py-2 text-sm"
            >
              <option value="all">All plays</option>
              {playOptions.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
            <label className="mb-1 block text-xs text-muted-foreground">League</label>
            <select
              value={league}
              onChange={(event) => setLeague(event.target.value)}
              className="w-full rounded-md border bg-background px-2 py-2 text-sm"
            >
              <option value="all">All leagues</option>
              {leagueOptions.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setSheet(false)}
              className="mt-4 w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
            >
              Show {rows.length} plays
            </button>
          </div>
        </div>
      ) : null}

      <p className="text-xs text-muted-foreground">
        Past column: how often this play in this fair-odds band landed in the backtest (shown only with 30+ past picks).
      </p>
    </div>
  );
}
