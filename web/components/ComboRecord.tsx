'use client';

import { useEffect, useState } from 'react';

type Strategy = {
  strategy: string;
  target: number;
  max_legs: number;
  tickets: number;
  predicted: number | null;
  landed: number | null;
  ci: [number | null, number | null];
  return: number | null;
  return_ci: [number | null, number | null];
  longest_losing: number;
  worst_drawdown: number;
  mozzart: { n: number; return: number | null };
};
type Payload = { strategies?: Strategy[] };

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

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Combos</h2>
      <p className="text-sm text-muted-foreground">
        Walk-forward on 2019-20 to 2025-26, model fitted on matches before each round and calibrated with that
        season&apos;s earlier-season factors. For each target payout and max leg count the optimiser picks the
        highest-probability ticket whose combined fair odds reach the target, one leg per match, each leg at
        fair odds 1.50 or more. Returns are at fair odds with flat 1-unit stakes.
      </p>
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2 text-right font-semibold">Target</th>
              <th className="px-3 py-2 text-right font-semibold">Max legs</th>
              <th className="px-3 py-2 text-right font-semibold">Tickets</th>
              <th className="px-3 py-2 text-right font-semibold">Predicted</th>
              <th className="px-3 py-2 text-right font-semibold">Landed</th>
              <th className="px-3 py-2 text-right font-semibold">95% CI</th>
              <th className="px-3 py-2 text-right font-semibold">Return</th>
              <th className="px-3 py-2 text-right font-semibold">Return 95% CI</th>
              <th className="px-3 py-2 text-right font-semibold">Longest losing</th>
              <th className="px-3 py-2 text-right font-semibold">Worst drawdown</th>
              <th className="px-3 py-2 text-right font-semibold">Mozzart</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((row) => (
              <tr key={row.strategy} className="border-t">
                <td className="tabular px-3 py-1.5 text-right font-medium">{row.target.toFixed(2)}</td>
                <td className="tabular px-3 py-1.5 text-right">{row.max_legs}</td>
                <td className="tabular px-3 py-1.5 text-right">{row.tickets.toLocaleString('en-GB')}</td>
                <td className="tabular px-3 py-1.5 text-right">{pct(row.predicted)}</td>
                <td className="tabular px-3 py-1.5 text-right font-medium">{pct(row.landed)}</td>
                <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">
                  {row.ci[0] === null ? '–' : `${pct(row.ci[0])} to ${pct(row.ci[1])}`}
                </td>
                <td className="tabular px-3 py-1.5 text-right">{signed(row.return)}</td>
                <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">
                  {row.return_ci[0] === null ? '–' : `${signed(row.return_ci[0])} to ${signed(row.return_ci[1])}`}
                </td>
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
      <p className="text-xs text-muted-foreground">
        Mozzart returns appear once settled live rounds carry frozen prices; there are none yet.
      </p>
    </section>
  );
}
