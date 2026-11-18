import Link from 'next/link';

import { readIndex } from '@/lib/data';
import { nOf, rate } from '@/lib/format';

const HEADLINE = [
  { id: 'tg_3plus', label: '3+ goals' },
  { id: 'btts_yes', label: 'BTTS' },
  { id: 'ht_x', label: 'HT draw' },
  { id: 'c1', label: 'C1 1X & 3+' },
  { id: 'c2', label: 'C2 1H 1+ & 2H 2+' },
  { id: 'c3', label: 'C3 Home 2+ & BTTS' },
];

export default function LeaguesPage() {
  const index = readIndex();
  const lastSeason = index.seasons[index.seasons.length - 1];

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">Leagues</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Pooled hit rates over {index.seasons[0]}–{lastSeason}, across {index.divisions.length} divisions. Open a
          league for season splits, Tuesday/Saturday splits, team Top 10s and upcoming fixtures.
        </p>
      </header>

      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2 text-left font-semibold">League</th>
              {HEADLINE.map((item) => (
                <th key={item.id} className="px-3 py-2 text-right font-semibold whitespace-nowrap">
                  {item.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {index.divisions.map((division) => (
              <tr key={division.code} className="border-t hover:bg-muted/30">
                <td className="px-3 py-2">
                  <Link className="font-medium underline-offset-2 hover:underline" href={`/leagues/${division.code}`}>
                    {division.name}
                  </Link>
                  <div className="text-xs text-muted-foreground">
                    {division.country} · tier {division.tier} · {division.matches.toLocaleString('en-GB')} matches
                  </div>
                </td>
                {HEADLINE.map((item) => {
                  const stat = division.headline[item.id];
                  return (
                    <td key={item.id} className="px-3 py-2 text-right whitespace-nowrap">
                      <div className="tabular font-medium">{rate(stat)}</div>
                      <div className="tabular text-xs text-muted-foreground">n={nOf(stat)}</div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
