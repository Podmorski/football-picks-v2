import Link from 'next/link';

import { readRankRound, readRoundIndex } from '@/lib/data';
import type { RankRow } from '@/lib/types';

function pcOf(row: RankRow): number {
  return row.pc ?? row.pl ?? row.p;
}

function defaultPicks(rows: RankRow[]): RankRow[] {
  const best = new Map<string, RankRow>();
  for (const row of rows) {
    if (row.m === 'RESULT:1' || row.m === 'RESULT:2') continue;
    if (pcOf(row) > 0.8) continue;
    const key = `${row.h}|${row.a}`;
    const current = best.get(key);
    if (!current || pcOf(row) > pcOf(current)) best.set(key, row);
  }
  return [...best.values()].sort((a, b) => pcOf(b) - pcOf(a)).slice(0, 15);
}

export default function RoundsPage() {
  const index = readRoundIndex();
  const rounds = [...index.rounds].sort((a, b) => (a.date < b.date ? 1 : -1));

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">Rounds</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Every published round, newest first, with the tally for the default filters (Any bet, min odds Any,
          Strongest lean). Open a round to see the full dashboard for it.
        </p>
      </header>

      {rounds.length === 0 ? (
        <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          No rounds published yet.
        </p>
      ) : (
        <ul className="divide-y rounded-xl border">
          {rounds.map((round) => {
            const document = readRankRound(round.date);
            const picks = document ? defaultPicks(document.rows) : [];
            const settled = picks.filter((row) => row.st === 'landed' || row.st === 'lost');
            const landed = picks.filter((row) => row.st === 'landed').length;
            const expected = settled.reduce((total, row) => total + pcOf(row), 0);
            return (
              <li key={`${round.date}-${round.kind}`}>
                <Link href={`/?round=${round.date}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-3 hover:bg-muted/40">
                  <span className="w-36 shrink-0 text-sm font-medium">
                    {round.label}
                    {round.kind === 'example' ? <span className="ml-1 text-xs text-muted-foreground">example</span> : null}
                  </span>
                  <span className="text-sm text-muted-foreground">{round.fixtures} matches</span>
                  <span className="tabular text-sm">
                    {settled.length > 0 ? (
                      <>
                        {landed} of {settled.length} landed · expected about {expected.toFixed(1)}
                      </>
                    ) : (
                      <span className="text-muted-foreground">pending</span>
                    )}
                  </span>
                  <span className="ml-auto text-sm text-primary">Open →</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
