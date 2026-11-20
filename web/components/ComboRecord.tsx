'use client';

import { useEffect, useState } from 'react';

type Strategy = {
  strategy: string;
  tickets: number;
  predicted: number | null;
  landed: number | null;
  ci: [number | null, number | null];
  return: number | null;
  longest_losing: number;
  worst_drawdown: number;
  mozzart: { n: number; return: number | null };
};
type Independence = { size: number; predicted: number; landed: number; ratio: number };
type Payload = { strategies?: Strategy[]; independence?: Independence[] };

function pct(value: number | null): string {
  return value === null ? '–' : `${(value * 100).toFixed(1)}%`;
}

function signed(value: number | null): string {
  if (value === null) return '–';
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

export default function ComboRecord() {
  const [data, setData] = useState<Payload | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/combo.json')
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: Payload | null) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const strategies = data?.strategies ?? [];
  if (strategies.length === 0) return null;
  const short = (data?.independence ?? []).filter((row) => row.ratio < 1);

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Combos</h2>
      <p className="text-sm text-muted-foreground">
        Walk-forward on 2019-20 to 2025-26, model fitted on matches before each round. Singles are the top 15 by
        calibrated probability; each k-leg ticket is the best k of those, one leg per match. Returns are at fair
        odds with flat 1-unit stakes.
      </p>
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2 text-left font-semibold">Strategy</th>
              <th className="px-3 py-2 text-right font-semibold">Tickets</th>
              <th className="px-3 py-2 text-right font-semibold">Predicted</th>
              <th className="px-3 py-2 text-right font-semibold">Landed</th>
              <th className="px-3 py-2 text-right font-semibold">95% CI</th>
              <th className="px-3 py-2 text-right font-semibold">Return</th>
              <th className="px-3 py-2 text-right font-semibold">Longest losing</th>
              <th className="px-3 py-2 text-right font-semibold">Worst drawdown</th>
              <th className="px-3 py-2 text-right font-semibold">Mozzart</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((row) => (
              <tr key={row.strategy} className="border-t">
                <td className="px-3 py-1.5">{row.strategy}</td>
                <td className="tabular px-3 py-1.5 text-right">{row.tickets.toLocaleString('en-GB')}</td>
                <td className="tabular px-3 py-1.5 text-right">{pct(row.predicted)}</td>
                <td className="tabular px-3 py-1.5 text-right font-medium">{pct(row.landed)}</td>
                <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">
                  {row.ci[0] === null ? '–' : `${pct(row.ci[0])} to ${pct(row.ci[1])}`}
                </td>
                <td className="tabular px-3 py-1.5 text-right">{signed(row.return)}</td>
                <td className="tabular px-3 py-1.5 text-right">{row.longest_losing}</td>
                <td className="tabular px-3 py-1.5 text-right">{row.worst_drawdown.toFixed(2)}</td>
                <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">
                  {row.mozzart.n > 0 ? `${row.mozzart.n} · ${signed(row.mozzart.return)}` : 'n=0'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(data?.independence ?? []).length > 0 ? (
        <p className="text-sm text-muted-foreground">
          Independence check (landed / predicted):{' '}
          {(data?.independence ?? []).map((row) => `${row.size}-leg ${row.ratio.toFixed(3)}`).join(' · ')}.
          {short.length > 0
            ? ' Multis land LESS often than predicted, so the combined % is optimistic.'
            : ' Multis land slightly more often than predicted, so the combined % is not optimistic.'}
        </p>
      ) : null}
      <p className="text-xs text-muted-foreground">
        Mozzart returns appear once settled live rounds carry frozen prices; there are none yet.
      </p>
    </section>
  );
}
