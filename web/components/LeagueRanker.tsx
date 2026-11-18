'use client';

import { useEffect, useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import type { PlayLeagueRow } from '@/lib/types';

function pct(value: number | null) {
  return value === null ? '–' : `${(value * 100).toFixed(1)}%`;
}

export default function LeagueRanker({ outcomes }: { outcomes: { id: string; label: string; group: string }[] }) {
  const [data, setData] = useState<Record<string, PlayLeagueRow[]> | null>(null);
  const [play, setPlay] = useState('tg_3plus');

  useEffect(() => {
    let cancelled = false;
    fetch('/data/play-leagues.json')
      .then((response) => (response.ok ? response.json() : { outcomes: {} }))
      .then((payload: { outcomes: Record<string, PlayLeagueRow[]> }) => {
        if (!cancelled) setData(payload.outcomes ?? {});
      })
      .catch(() => {
        if (!cancelled) setData({});
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const groups = useMemo(() => Array.from(new Set(outcomes.map((outcome) => outcome.group))), [outcomes]);
  const rows = data?.[play] ?? [];

  return (
    <section className="space-y-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold">Rank leagues by play</h2>
        <select
          value={play}
          onChange={(event) => setPlay(event.target.value)}
          className="rounded-md border bg-background px-2 py-1.5 text-sm"
        >
          {groups.map((group) => (
            <optgroup key={group} label={group}>
              {outcomes
                .filter((outcome) => outcome.group === group)
                .map((outcome) => (
                  <option key={outcome.id} value={outcome.id}>
                    {outcome.label}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </div>

      {!data ? <p className="text-sm text-muted-foreground">Loading…</p> : null}

      {data && rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Not enough history for this play.</p>
      ) : null}

      {rows.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-2 py-1.5 text-left font-semibold">League</th>
                <th className="px-2 py-1.5 text-right font-semibold">Rate</th>
                <th className="px-2 py-1.5 text-right font-semibold">n</th>
                <th className="px-2 py-1.5 text-right font-semibold">95% CI</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.code} className="border-t">
                  <td className="px-2 py-1.5">
                    {row.name}
                    <span className="ml-1 text-xs text-muted-foreground">{row.country}</span>
                    {row.ft_only ? (
                      <Badge variant="outline" className="ml-1 text-[10px]">
                        FT only
                      </Badge>
                    ) : null}
                  </td>
                  <td className="tabular px-2 py-1.5 text-right font-medium">{pct(row.rate)}</td>
                  <td className="tabular px-2 py-1.5 text-right">{row.n.toLocaleString('en-GB')}</td>
                  <td className="tabular px-2 py-1.5 text-right text-xs text-muted-foreground">
                    {pct(row.ci[0])}–{pct(row.ci[1])}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
