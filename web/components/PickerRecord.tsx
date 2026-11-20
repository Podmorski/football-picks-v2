'use client';

import { useEffect, useState } from 'react';

type Row = {
  group: string;
  band: string;
  n: number;
  shown: number;
  landed: number;
  return: number | null;
  ci: [number | null, number | null];
};

type Payload = { record?: Row[] };

function pct(value: number | null): string {
  return value === null ? '–' : `${(value * 100).toFixed(1)}%`;
}

function signed(value: number | null): string {
  if (value === null) return '–';
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

export default function PickerRecord() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/picker.json')
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: Payload | null) => {
        if (!cancelled) setRows(payload?.record ?? []);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (rows.length === 0) return null;

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Picker calibration</h2>
      <p className="text-sm text-muted-foreground">
        Walk-forward: for every round the model used only matches before it, took each match&apos;s
        highest-probability bet in the group, and the factor for a group and probability band was fitted on
        earlier seasons only. Shown is the calibrated probability, landed is how often it actually happened.
      </p>
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2 text-left font-semibold">Group</th>
              <th className="px-3 py-2 text-left font-semibold">Band</th>
              <th className="px-3 py-2 text-right font-semibold">n</th>
              <th className="px-3 py-2 text-right font-semibold">Shown</th>
              <th className="px-3 py-2 text-right font-semibold">Landed</th>
              <th className="px-3 py-2 text-right font-semibold">Return</th>
              <th className="px-3 py-2 text-right font-semibold">95% CI</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.group}-${row.band}`} className="border-t">
                <td className="px-3 py-1.5">{row.group}</td>
                <td className="tabular px-3 py-1.5 text-muted-foreground">{row.band}%</td>
                <td className="tabular px-3 py-1.5 text-right">{row.n.toLocaleString('en-GB')}</td>
                <td className="tabular px-3 py-1.5 text-right font-medium">{pct(row.shown)}</td>
                <td className="tabular px-3 py-1.5 text-right">{pct(row.landed)}</td>
                <td className="tabular px-3 py-1.5 text-right">{signed(row.return)}</td>
                <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">
                  {row.ci[0] === null ? '–' : `${signed(row.ci[0])} to ${signed(row.ci[1])}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        At fair odds the long-run return is about zero; profit needs a bookmaker price above the fair odds.
      </p>
    </section>
  );
}
