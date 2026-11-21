import Link from 'next/link';

import ComboRecord from '@/components/ComboRecord';
import MozzartRecord from '@/components/MozzartRecord';
import MozzartVettedRecord from '@/components/MozzartVettedRecord';
import PickerRecord from '@/components/PickerRecord';
import { readModel, readRecord } from '@/lib/data';

function pct(value: number | null) {
  return value === null ? '–' : `${(value * 100).toFixed(1)}%`;
}

export default function RecordPage() {
  const record = readRecord();
  const model = readModel();

  if (!record) {
    return (
      <p className="text-sm text-muted-foreground">
        No record yet. Run the pipeline to build the backtest and publish a round.
      </p>
    );
  }

  const bins = record.calibration.overall.bins.filter((bin) => bin.n > 0);
  const settledRounds = record.rounds.filter((round) => round.settled_count > 0);

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">Record</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Everything here is measured, not claimed: the walk-forward backtest calibration and every published pick.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Backtest calibration</h2>
        <p className="text-sm text-muted-foreground">
          Held-out seasons {model?.backtest.seasons[0] ?? '–'}–{model?.backtest.seasons.at(-1) ?? '–'} ·{' '}
          {(model?.backtest.fixtures ?? 0).toLocaleString('en-GB')} fixtures. “Shown” is the predicted
          probability bin, “landed” is how often it actually happened.
        </p>
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 text-left font-semibold">Bin</th>
                <th className="px-3 py-2 text-right font-semibold">Shown</th>
                <th className="px-3 py-2 text-right font-semibold">Landed</th>
                <th className="px-3 py-2 text-right font-semibold">Diff</th>
                <th className="px-3 py-2 text-right font-semibold">n</th>
              </tr>
            </thead>
            <tbody>
              {bins.map((bin) => {
                const diff = bin.landed === null ? null : bin.landed - bin.shown;
                const inRange = Number(bin.bin.split('-')[0]) >= 40 && Number(bin.bin.split('-')[1]) <= 65;
                return (
                  <tr key={bin.bin} className={inRange ? 'border-t bg-accent/30' : 'border-t'}>
                    <td className="tabular px-3 py-1.5">{bin.bin}%</td>
                    <td className="tabular px-3 py-1.5 text-right">{pct(bin.shown)}</td>
                    <td className="tabular px-3 py-1.5 text-right font-medium">{pct(bin.landed)}</td>
                    <td className="tabular px-3 py-1.5 text-right text-muted-foreground">
                      {diff === null ? '–' : `${diff > 0 ? '+' : ''}${(diff * 100).toFixed(1)}`}
                    </td>
                    <td className="tabular px-3 py-1.5 text-right">{bin.n.toLocaleString('en-GB')}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted-foreground">
          Highlighted rows are the 40–65% band the picker actually publishes.
        </p>
      </section>

      {model ? (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">What earned its place in the model</h2>
          <p className="text-sm text-muted-foreground">
            Brier score by component (lower is better), pooled over all outcomes. A component is only used live if
            it improved the held-out score.
          </p>
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-3 py-2 text-left font-semibold">Component</th>
                  <th className="px-3 py-2 text-right font-semibold">Brier</th>
                  <th className="px-3 py-2 text-right font-semibold">Log loss</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(model.ablation.overall).map(([component, entry]) => (
                  <tr key={component} className="border-t">
                    <td className="px-3 py-1.5 capitalize">{component === 'odds' ? 'goals + odds' : component}</td>
                    <td className="tabular px-3 py-1.5 text-right">{entry.brier?.toFixed(4) ?? '–'}</td>
                    <td className="tabular px-3 py-1.5 text-right">{entry.logloss?.toFixed(4) ?? '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <PickerRecord />

      <ComboRecord />

      <MozzartRecord />

      <MozzartVettedRecord />

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Published picks</h2>
        {settledRounds.length === 0 ? (
          <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
            No settled rounds yet. See the{' '}
            <Link className="underline underline-offset-2" href="/#example">
              example round
            </Link>{' '}
            for how a published round looks once results are in.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-3 py-2 text-left font-semibold">Round</th>
                  <th className="px-3 py-2 text-right font-semibold">Picks</th>
                  <th className="px-3 py-2 text-right font-semibold">Settled</th>
                  <th className="px-3 py-2 text-right font-semibold">Landed</th>
                  <th className="px-3 py-2 text-right font-semibold">Hit rate</th>
                </tr>
              </thead>
              <tbody>
                {record.rounds.map((round) => (
                  <tr key={`${round.date}-${round.kind}`} className="border-t">
                    <td className="px-3 py-1.5">
                      {round.label}
                      {round.kind === 'example' ? (
                        <span className="ml-1 text-xs text-muted-foreground">example</span>
                      ) : null}
                    </td>
                    <td className="tabular px-3 py-1.5 text-right">{round.picks}</td>
                    <td className="tabular px-3 py-1.5 text-right">{round.settled_count}</td>
                    <td className="tabular px-3 py-1.5 text-right">{round.hits}</td>
                    <td className="tabular px-3 py-1.5 text-right font-medium">
                      {round.settled_count ? `${((round.hits / round.settled_count) * 100).toFixed(1)}%` : '–'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
