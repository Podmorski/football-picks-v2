'use client';

import { useEffect, useState } from 'react';

type Summary = { n: number; landed: number | null; return: number | null; ci: [number | null, number | null] };
type Payload = { cumulative?: Record<string, Summary>; rounds?: ({ date: string } & Record<string, Summary>)[] };

const SCOPES: [string, string][] = [
  ['all', 'All passing picks'],
  ['passing_value', 'Passing + Mozzart >= fair'],
  ['any_value', 'Any priced bet + Mozzart >= fair'],
];

function pct(value: number | null): string {
  return value === null ? '–' : `${(value * 100).toFixed(1)}%`;
}
function signed(value: number | null): string {
  return value === null ? '–' : `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}
function ciText(summary: Summary): string {
  return summary.ci[0] === null ? '–' : `${signed(summary.ci[0])} to ${signed(summary.ci[1])}`;
}

export default function MozzartVettedRecord() {
  const [data, setData] = useState<Payload | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/mozzart-vetted-record.json')
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: Payload | null) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const cumulative = data?.cumulative;
  if (!cumulative || !cumulative.all || cumulative.all.n === 0) return null;

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Record at Mozzart prices</h2>
      <p className="text-sm text-muted-foreground">
        Settled rounds only. Return is at the Mozzart price: price − 1 when landed, −1 when lost; the
        95% interval is bootstrapped over round dates.
      </p>
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2 text-left font-semibold">Scope</th>
              <th className="px-3 py-2 text-right font-semibold">n</th>
              <th className="px-3 py-2 text-right font-semibold">Landed</th>
              <th className="px-3 py-2 text-right font-semibold">Return</th>
              <th className="px-3 py-2 text-right font-semibold">95% CI</th>
            </tr>
          </thead>
          <tbody>
            {SCOPES.map(([key, label]) => {
              const summary = cumulative[key];
              if (!summary || summary.n === 0) return null;
              return (
                <tr key={key} className="border-t">
                  <td className="px-3 py-1.5">{label}</td>
                  <td className="tabular px-3 py-1.5 text-right">{summary.n.toLocaleString('en-GB')}</td>
                  <td className="tabular px-3 py-1.5 text-right">{pct(summary.landed)}</td>
                  <td className="tabular px-3 py-1.5 text-right font-medium">{signed(summary.return)}</td>
                  <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">{ciText(summary)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {data?.rounds && data.rounds.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Per round</h3>
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-3 py-2 text-left font-semibold">Round</th>
                  {SCOPES.map(([, label]) => (
                    <th key={label} className="px-3 py-2 text-right font-semibold">{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rounds.map((round) => (
                  <tr key={round.date} className="border-t">
                    <td className="px-3 py-1.5">{round.date}</td>
                    {SCOPES.map(([key]) => {
                      const summary = round[key];
                      return (
                        <td key={key} className="tabular px-3 py-1.5 text-right text-xs">
                          {summary && summary.n > 0 ? `${summary.n} · ${pct(summary.landed)} · ${signed(summary.return)}` : '–'}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
