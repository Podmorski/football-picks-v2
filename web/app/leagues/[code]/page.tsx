import Link from 'next/link';
import { notFound } from 'next/navigation';

import LeagueTabs from '@/components/LeagueTabs';
import { readIndex, readLeague } from '@/lib/data';

export const dynamicParams = false;

export function generateStaticParams() {
  return readIndex().divisions.map((division) => ({ code: division.code }));
}

export default async function LeaguePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const league = readLeague(code);
  if (!league) notFound();

  const firstSeason = league.seasons[0];
  const lastSeason = league.seasons[league.seasons.length - 1];

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <p className="text-sm text-muted-foreground">
          <Link className="underline-offset-2 hover:underline" href="/leagues">
            ← Leagues
          </Link>
        </p>
        <h1 className="text-2xl font-bold tracking-tight">{league.name}</h1>
        <p className="text-sm text-muted-foreground">
          {league.country} · tier {league.tier} · {league.matches.toLocaleString('en-GB')} matches · {firstSeason}–
          {lastSeason} · {league.team_count} teams
        </p>
      </header>

      <LeagueTabs league={league} />
    </div>
  );
}
