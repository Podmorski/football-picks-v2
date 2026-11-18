import Link from 'next/link';

import LeagueRanker from '@/components/LeagueRanker';
import { Badge } from '@/components/ui/badge';
import { readIndex, readLeague } from '@/lib/data';
import { rate } from '@/lib/format';

const HEADLINE = [
  { id: 'tg_3plus', label: '3+ goals' },
  { id: 'btts_yes', label: 'BTTS' },
  { id: 'ht_x', label: 'HT draw' },
  { id: 'c1', label: 'C1' },
  { id: 'c2', label: 'C2' },
  { id: 'c3', label: 'C3' },
];

export default function LeaguesPage() {
  const index = readIndex();
  const lastSeason = index.seasons[index.seasons.length - 1];
  const sample = readLeague('E1') ?? readLeague(index.divisions[0]?.code ?? 'E1');
  const outcomes = sample?.outcomes ?? [];

  const byCountry = new Map<string, typeof index.divisions>();
  for (const division of index.divisions) {
    const list = byCountry.get(division.country) ?? [];
    list.push(division);
    byCountry.set(division.country, list);
  }
  const countries = Array.from(byCountry.keys()).sort();

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">Leagues</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          {index.divisions.length} competitions, {index.seasons[0]}–{lastSeason}. “FT only” leagues have no half-time
          scores in the source, so half-time plays are never offered for them.
        </p>
      </header>

      {outcomes.length ? <LeagueRanker outcomes={outcomes} /> : null}

      <div className="space-y-6">
        {countries.map((country) => (
          <section key={country} className="space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{country}</h2>
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
                    <th className="px-3 py-2 text-right font-semibold">Matches</th>
                  </tr>
                </thead>
                <tbody>
                  {(byCountry.get(country) ?? [])
                    .sort((a, b) => a.tier - b.tier || a.code.localeCompare(b.code))
                    .map((division) => (
                      <tr key={division.code} className="border-t hover:bg-muted/30">
                        <td className="px-3 py-2">
                          <Link className="font-medium underline-offset-2 hover:underline" href={`/leagues/${division.code}`}>
                            {division.name}
                          </Link>
                          {division.ft_only ? (
                            <Badge variant="outline" className="ml-1.5 text-[10px]">
                              FT only
                            </Badge>
                          ) : null}
                          <div className="text-xs text-muted-foreground">tier {division.tier}</div>
                        </td>
                        {HEADLINE.map((item) => {
                          const stat = division.headline[item.id];
                          return (
                            <td key={item.id} className="tabular px-3 py-2 text-right whitespace-nowrap font-medium">
                              {rate(stat)}
                            </td>
                          );
                        })}
                        <td className="tabular px-3 py-2 text-right text-muted-foreground">
                          {division.matches.toLocaleString('en-GB')}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
