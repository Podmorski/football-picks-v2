import Link from 'next/link';

import RoundTabs from '@/components/RoundTabs';
import { Badge } from '@/components/ui/badge';
import { readRound, readRoundIndex } from '@/lib/data';
import type { RoundDocument } from '@/lib/types';

function latest(kind: string): RoundDocument | null {
  const index = readRoundIndex();
  const candidates = index.rounds
    .filter((row) => row.kind === kind && row.picks > 0)
    .sort((a, b) => (a.date < b.date ? 1 : -1));
  for (const row of candidates) {
    const round = readRound(row.date);
    if (round && round.picks.length > 0) return round;
  }
  return null;
}

export default function HomePage() {
  const round = latest('round');
  const example = latest('example');

  return (
    <div className="space-y-8">
      <section className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">
          {round ? `${round.label} — best plays` : 'This round — best plays'}
        </h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          One play per match, chosen where the counted history and the goal model agree. Probability is a
          calibrated hit rate, not a guarantee.
        </p>
      </section>

      {round ? (
        <RoundTabs round={round} />
      ) : (
        <section className="rounded-xl border border-dashed px-4 py-8 text-center">
          <p className="font-medium">This round is not published yet.</p>
          <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
            Saturday picks appear Friday around 18:00 UK; Tuesday picks Tuesday around 14:00 UK.
          </p>
          {example ? (
            <p className="mt-4 text-sm">
              <Link className="underline underline-offset-2" href="#example">
                See the example round for last Saturday ({example.label}) →
              </Link>
            </p>
          ) : null}
        </section>
      )}

      {example ? (
        <section id="example" className="scroll-mt-16 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">Example — last Saturday</h2>
            <Badge variant="secondary">
              {example.settled_count}/{example.picks.length} settled · {example.hits} landed
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {example.label}, using only data available before that day, settled against the real results.
          </p>
          <RoundTabs round={example} />
        </section>
      ) : null}
    </div>
  );
}
