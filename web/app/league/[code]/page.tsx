import { Fragment } from 'react';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import OutcomeSelector from '@/components/OutcomeSelector';
import { readIndex, readLeague } from '@/lib/data';
import { ci, nOf, rate } from '@/lib/format';
import type { LeagueFile, Stat } from '@/lib/types';

// Every league page is known at build time; anything else is a genuine 404.
export const dynamicParams = false;

export function generateStaticParams() {
  return readIndex().divisions.map((division) => ({ code: division.code }));
}

const COLUMNS = [
  { key: 'pooled', label: 'All seasons' },
  { key: 'focus', label: 'This season' },
  { key: 'tue', label: 'Tue' },
  { key: 'sat', label: 'Sat' },
  { key: 'other', label: 'Other' },
] as const;

function statFor(league: LeagueFile, outcomeId: string, column: string): Stat | undefined {
  if (column === 'pooled') return league.league.pooled[outcomeId];
  if (column === 'focus') return league.league.by_season[league.focus_season]?.[outcomeId];
  return league.league.by_weekday[column]?.[outcomeId];
}

export default async function LeaguePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const league = readLeague(code);
  if (!league) notFound();

  const groups = Array.from(new Set(league.outcomes.map((outcome) => outcome.group)));
  const firstSeason = league.seasons[0];
  const lastSeason = league.seasons[league.seasons.length - 1];

  return (
    <main className="wrap">
      <p className="crumbs">
        <Link href="/">← All leagues</Link>
      </p>
      <h1>{league.name}</h1>
      <p className="meta">
        {league.country} · tier {league.tier} · {league.matches.toLocaleString('en-GB')} matches ·{' '}
        {firstSeason}–{lastSeason} · {league.team_count} teams
      </p>

      <h2>Outcome rates</h2>
      <p className="note" style={{ marginTop: 0 }}>
        Rate, sample size and 95% Wilson interval. “This season” is {league.focus_season}; the
        weekday columns split the same sample. ✻ marks outcomes that need half-time scores.
      </p>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Outcome</th>
              {COLUMNS.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <Fragment key={group}>
                <tr className="group-row">
                  <td colSpan={COLUMNS.length + 1}>{group}</td>
                </tr>
                {league.outcomes
                  .filter((outcome) => outcome.group === group)
                  .map((outcome) => (
                    <tr key={outcome.id}>
                      <td>
                        {outcome.label}
                        {outcome.needs_ht ? <span className="sub"> ✻</span> : null}
                      </td>
                      {COLUMNS.map((column) => {
                        const stat = statFor(league, outcome.id, column.key);
                        return (
                          <td key={column.key}>
                            <div className="rate">{rate(stat)}</div>
                            <div className="sub">
                              n={nOf(stat)} · {ci(stat)}
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Team Top 10s — {league.focus_season}</h2>
      <OutcomeSelector outcomes={league.outcomes} top10={league.top10} />
    </main>
  );
}
