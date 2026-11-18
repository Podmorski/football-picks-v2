'use client';

import { useEffect, useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ci, nOf, rate } from '@/lib/format';
import type { LeagueFile, ScopeKey, Stat, TeamsFile, Top10Row, UpcomingFixture } from '@/lib/types';

const COLUMNS = [
  { key: 'pooled', label: 'All seasons' },
  { key: 'focus', label: 'This season' },
  { key: 'tue', label: 'Tue' },
  { key: 'sat', label: 'Sat' },
  { key: 'other', label: 'Other' },
] as const;

const SCOPES: { key: ScopeKey; label: string }[] = [
  { key: 'home', label: 'Home only' },
  { key: 'away', label: 'Away only' },
  { key: 'last10', label: 'Last 10' },
];

function statFor(league: LeagueFile, outcomeId: string, column: string): Stat | undefined {
  if (column === 'pooled') return league.league.pooled[outcomeId];
  if (column === 'focus') return league.league.by_season[league.focus_season]?.[outcomeId];
  return league.league.by_weekday[column]?.[outcomeId];
}

function RatesTable({ league }: { league: LeagueFile }) {
  const groups = useMemo(
    () => Array.from(new Set(league.outcomes.map((outcome) => outcome.group))),
    [league.outcomes],
  );

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-3 py-2 text-left font-semibold">Outcome</th>
            {COLUMNS.map((column) => (
              <th key={column.key} className="px-3 py-2 text-right font-semibold whitespace-nowrap">
                {column.key === 'focus' ? league.focus_season : column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <FragmentRows key={group} group={group} league={league} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FragmentRows({ group, league }: { group: string; league: LeagueFile }) {
  const outcomes = league.outcomes.filter((outcome) => outcome.group === group);
  return (
    <>
      <tr className="bg-muted/40">
        <td colSpan={COLUMNS.length + 1} className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {group}
        </td>
      </tr>
      {outcomes.map((outcome) => (
        <tr key={outcome.id} className="border-t hover:bg-muted/30">
          <td className="px-3 py-1.5 whitespace-nowrap">
            {outcome.label}
            {outcome.needs_ht ? <span className="ml-1 text-xs text-muted-foreground">✻</span> : null}
          </td>
          {COLUMNS.map((column) => {
            const stat = statFor(league, outcome.id, column.key);
            return (
              <td key={column.key} className="px-3 py-1.5 text-right whitespace-nowrap">
                <div className="tabular font-medium">{rate(stat)}</div>
                <div className="tabular text-xs text-muted-foreground">
                  n={nOf(stat)} · {ci(stat)}
                </div>
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}

function TopTable({ title, rows }: { title: string; rows: Top10Row[] }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      {rows.length === 0 ? (
        <p className="rounded-lg border border-dashed px-3 py-4 text-sm text-muted-foreground">
          No team reaches n = 5 yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-2 py-1.5 text-left font-semibold">#</th>
                <th className="px-2 py-1.5 text-left font-semibold">Team</th>
                <th className="px-2 py-1.5 text-right font-semibold">Rate</th>
                <th className="px-2 py-1.5 text-right font-semibold">n</th>
                <th className="px-2 py-1.5 text-right font-semibold">95% CI</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.team} className="border-t">
                  <td className="px-2 py-1.5 text-muted-foreground">{index + 1}</td>
                  <td className="px-2 py-1.5">{row.team}</td>
                  <td className="tabular px-2 py-1.5 text-right font-medium">{(row.rate * 100).toFixed(1)}%</td>
                  <td className="tabular px-2 py-1.5 text-right">{row.n}</td>
                  <td className="tabular px-2 py-1.5 text-right text-xs text-muted-foreground">
                    {(row.lo * 100).toFixed(1)}–{(row.hi * 100).toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function UpcomingList({ fixtures }: { fixtures: UpcomingFixture[] }) {
  if (fixtures.length === 0) {
    return (
      <p className="rounded-lg border border-dashed px-3 py-6 text-sm text-muted-foreground">
        No upcoming fixtures published for this division yet.
      </p>
    );
  }
  return (
    <ul className="divide-y rounded-lg border">
      {fixtures.map((fixture) => (
        <li key={`${fixture.date}-${fixture.home}-${fixture.away}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 text-sm">
          <span className="w-24 shrink-0 text-xs text-muted-foreground">
            {fixture.date.slice(5)} {fixture.time ?? ''}
          </span>
          <span className="min-w-0 flex-1 truncate">
            {fixture.home} <span className="text-muted-foreground">v</span> {fixture.away}
          </span>
          {fixture.best ? (
            <span className="flex items-center gap-2">
              <span className="text-muted-foreground">{fixture.best.play}</span>
              <Badge variant="secondary" className="tabular">
                {(fixture.best.probability * 100).toFixed(1)}%
              </Badge>
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">no qualifying play</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function LeagueTabs({ league }: { league: LeagueFile }) {
  const [tab, setTab] = useState('rates');
  const [teams, setTeams] = useState<TeamsFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outcomeId, setOutcomeId] = useState('c3');

  useEffect(() => {
    if (tab === 'rates' || teams) return;
    let cancelled = false;
    fetch(`/data/teams/${league.code}.json`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data: TeamsFile) => {
        if (!cancelled) setTeams(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'failed to load');
      });
    return () => {
      cancelled = true;
    };
  }, [tab, teams, league.code]);

  const groups = useMemo(
    () => Array.from(new Set(league.outcomes.map((outcome) => outcome.group))),
    [league.outcomes],
  );

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList>
        <TabsTrigger value="rates">Rates</TabsTrigger>
        <TabsTrigger value="teams">Top teams</TabsTrigger>
        <TabsTrigger value="upcoming">Upcoming</TabsTrigger>
      </TabsList>

      <TabsContent value="rates">
        <p className="mb-2 text-xs text-muted-foreground">
          Rate, sample size and 95% Wilson interval. “This season” is {league.focus_season}. ✻ needs half-time scores.
        </p>
        <RatesTable league={league} />
      </TabsContent>

      <TabsContent value="teams">
        {error ? <p className="text-sm text-destructive">Could not load team data: {error}</p> : null}
        {!teams && !error ? <p className="text-sm text-muted-foreground">Loading team data…</p> : null}
        {teams ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="outcome" className="text-sm text-muted-foreground">
                Outcome
              </label>
              <select
                id="outcome"
                value={outcomeId}
                onChange={(event) => setOutcomeId(event.target.value)}
                className="max-w-full rounded-md border bg-background px-2 py-1.5 text-sm"
              >
                {groups.map((group) => (
                  <optgroup key={group} label={group}>
                    {league.outcomes
                      .filter((outcome) => outcome.group === group)
                      .map((outcome) => (
                        <option key={outcome.id} value={outcome.id}>
                          {outcome.label}
                        </option>
                      ))}
                  </optgroup>
                ))}
              </select>
              <span className="text-xs text-muted-foreground">ranked by Wilson lower bound · minimum n = 5</span>
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              {SCOPES.map((scope) => (
                <TopTable
                  key={scope.key}
                  title={scope.label}
                  rows={teams.top10[outcomeId]?.[scope.key] ?? []}
                />
              ))}
            </div>
          </div>
        ) : null}
      </TabsContent>

      <TabsContent value="upcoming">
        {!teams ? (
          <p className="text-sm text-muted-foreground">{error ? `Could not load fixtures: ${error}` : 'Loading fixtures…'}</p>
        ) : (
          <UpcomingList fixtures={teams.upcoming ?? []} />
        )}
      </TabsContent>
    </Tabs>
  );
}
