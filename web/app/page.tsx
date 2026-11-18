import Link from 'next/link';

import RoundExplorer from '@/components/RoundExplorer';
import { readModel, readRound, readRoundIndex } from '@/lib/data';
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

function viewCount(round: RoundDocument, key: string): number {
  return round.views?.[key]?.picks.length ?? (key === 'most_likely' ? round.picks?.length ?? 0 : 0);
}

export default function HomePage() {
  const round = latest('round');
  const example = latest('example');
  const model = readModel();
  const bandStats = model?.picker_backtest?.play_bands ?? [];

  const focus = round ?? example;
  const leagues = focus
    ? new Set(
        (focus.views?.most_likely?.picks ?? focus.picks ?? []).map((pick) => pick.div),
      ).size
    : 0;
  const fixtures = focus?.fixtures ?? focus?.views?.most_likely?.picks.length ?? 0;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">
          {focus ? `${focus.label} — best plays` : 'This round — best plays'}
        </h1>
        <p className="text-sm text-muted-foreground">
          {focus
            ? `${fixtures} fixtures · ${leagues} leagues · ${viewCount(focus, 'most_likely')} most likely · ${viewCount(
                focus,
                'stand_out',
              )} stand-out · ${viewCount(focus, 'best_combos')} combos`
            : 'No fixtures published for this round yet.'}
        </p>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Every play is a calibrated hit rate. Nothing here is a guarantee — the filters only keep plays with a
          real sample behind them.
        </p>
      </header>

      {round ? (
        <RoundExplorer round={round} bandStats={bandStats} />
      ) : example ? (
        <>
          <section className="rounded-xl border border-dashed px-4 py-6 text-center">
            <p className="font-medium">This round is not published yet.</p>
            <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
              Saturday picks appear Friday around 18:00 UK; Tuesday picks Tuesday around 14:00 UK.
            </p>
            <p className="mt-3 text-sm">
              <Link className="underline underline-offset-2" href="#example">
                See the example round for last Saturday ({example.label}) →
              </Link>
            </p>
          </section>

          <section id="example" className="scroll-mt-16 space-y-4">
            <h2 className="text-lg font-semibold">Example — last Saturday</h2>
            <p className="text-sm text-muted-foreground">
              {example.label}, using only data available before that day and settled against the real results.
            </p>
            <RoundExplorer round={example} bandStats={bandStats} />
          </section>
        </>
      ) : (
        <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          No rounds published yet.
        </p>
      )}
    </div>
  );
}
