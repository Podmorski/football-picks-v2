'use client';

import { useEffect, useState } from 'react';

type Row = {
  strategy: string;
  level: string;
  picks: number;
  mean_return: number | null;
  return_ci: [number | null, number | null];
};

type Payload = {
  priced_picks?: number;
  summary?: Row[];
};

function signedPct(value: number | null): string {
  if (value === null) return '–';
  const sign = value > 0 ? '+' : '';
  return sign + (value * 100).toFixed(1) + '%';
}

export default function MozzartRecord() {
  const [data, setData] = useState<Payload | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/mozzart-record.json')
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: Payload | null) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const rows = data?.summary ?? [];
  if (rows.length === 0) return null;

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Return at Mozzart price</h2>
      <p className="text-sm text-muted-foreground">
        Every published pick that carried a frozen Mozzart price, replayed at that price: price − 1 when it
        landed, −1 when it lost. The 95% interval is bootstrapped over round dates. Only picks settled so far
        count, so the sample grows each week.
      </p>
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2 text-left font-semibold">Ranking</th>
              <th className="px-3 py-2 text-right font-semibold">Min odds</th>
              <th className="px-3 py-2 text-right font-semibold">n priced</th>
              <th className="px-3 py-2 text-right font-semibold">Return</th>
              <th className="px-3 py-2 text-right font-semibold">95% CI</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.strategy + '-' + row.level} className="border-t">
                <td className="px-3 py-1.5">{row.strategy === 'lean' ? 'Strongest lean' : 'Most likely'}</td>
                <td className="tabular px-3 py-1.5 text-right text-muted-foreground">{row.level}</td>
                <td className="tabular px-3 py-1.5 text-right">{row.picks.toLocaleString('en-GB')}</td>
                <td className="tabular px-3 py-1.5 text-right font-medium">{signedPct(row.mean_return)}</td>
                <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">
                  {row.return_ci[0] === null
                    ? '–'
                    : signedPct(row.return_ci[0]) + ' to ' + signedPct(row.return_ci[1])}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        Mozzart pays what it pays; at the fair price the long-run return is about zero, so any edge here is
        the bookmaker price minus the fair one.
      </p>
    </section>
  );
}
