import Link from 'next/link';

import { readDailyBestPrivate, readRankRoundComplete, readRoundIndex } from '@/lib/data';
import { roundTally } from '@/lib/vetted';

export default function RoundsPage() {
  const index = readRoundIndex();
  const dailyBest = readDailyBestPrivate();
  const frozenByDate = new Map((dailyBest?.rounds ?? []).map((round) => [round.round_date, round]));
  const seen = new Set<string>();
  const rounds = [...index.rounds]
    .sort((a, b) => (a.date < b.date ? 1 : -1))
    .filter((round) => {
      if (seen.has(round.date)) return false;
      seen.add(round.date);
      return true;
    });

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">Rounds</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Every published round, newest first. Activated rounds show the frozen Daily-best tally; other rounds
          keep the legacy 58% Any-bet cohort tally (calibrated probability ≥ 58%, fair odds ≥ 1.20), which is
          research only. Open a round to see the full dashboard for it.
        </p>
      </header>

      {rounds.length === 0 ? (
        <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          No rounds published yet.
        </p>
      ) : (
        <ul className="divide-y rounded-xl border">
          {rounds.map((round) => {
            const document = readRankRoundComplete(round.date);
            const frozen = frozenByDate.get(round.date);
            const statusMap = new Map(
              (document?.rows ?? []).map((row) => [`${row.d}|${row.h}|${row.a}|${row.m}`, row.st ?? 'pending']),
            );
            const frozenTally = frozen
              ? frozen.rows.reduce(
                  (tally, row) => {
                    const status = statusMap.get(`${row.d}|${row.h}|${row.a}|${row.m}`) ?? 'pending';
                    tally.selected += 1;
                    if (status === 'landed') tally.landed += 1;
                    else if (status === 'lost') tally.lost += 1;
                    else if (status === 'void') tally.void += 1;
                    else tally.pending += 1;
                    return tally;
                  },
                  { selected: 0, landed: 0, lost: 0, void: 0, pending: 0 },
                )
              : null;
            const tally = document ? roundTally(document.rows) : null;
            const settled = tally?.settled.length ?? 0;
            const landed = tally?.landed ?? 0;
            const expected = tally?.expected ?? 0;
            const frozenSettled = frozenTally ? frozenTally.landed + frozenTally.lost + frozenTally.void : 0;
            return (
              <li key={round.date}>
                <Link href={`/?round=${round.date}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-3 hover:bg-muted/40">
                  <span className="w-36 shrink-0 text-sm font-medium">
                    {round.label}
                    {round.kind === 'example' ? <span className="ml-1 text-xs text-muted-foreground">example</span> : null}
                  </span>
                  <span className="text-sm text-muted-foreground">{round.fixtures} matches</span>
                  <span className="tabular text-sm">
                    {frozenTally ? (
                      <>
                        Frozen Daily best · {frozenTally.selected} selected · {frozenSettled} settled ·{' '}
                        {frozenTally.landed} landed / {frozenTally.lost} lost / {frozenTally.void} void /{' '}
                        {frozenTally.pending} pending
                      </>
                    ) : settled > 0 ? (
                      <>
                        <span className="text-muted-foreground">Legacy 58% cohort · </span>
                        {landed} of {settled} landed · expected about {expected.toFixed(1)}
                      </>
                    ) : (
                      <span className="text-muted-foreground">Results pending</span>
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
