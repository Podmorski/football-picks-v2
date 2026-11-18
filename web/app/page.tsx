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

export default function HomePage() {
  const index = readIndex();
  const lastSeason = index.seasons[index.seasons.length - 1];

  return (
    <main className="wrap">
      <h1>League outcome rates</h1>
      <p className="lede">
        Every figure here is a historical hit rate: how often an outcome has actually happened in
        the division since {index.seasons[0]}, counted across {index.divisions.length} leagues.
        Nothing on this site is a prediction or a tip.
      </p>
      <p className="meta">
        {index.seasons[0]} – {lastSeason} · current season {index.current_season} · all-season
        pooled rates
      </p>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>League</th>
              {HEADLINE.map((item) => (
                <th key={item.id}>{item.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {index.divisions.map((division) => (
              <tr key={division.code}>
                <td>
                  <Link href={`/league/${division.code}`}>{division.name}</Link>
                  <div className="sub">
                    {division.country} · tier {division.tier} ·{' '}
                    {division.matches.toLocaleString('en-GB')} matches
                  </div>
                </td>
                {HEADLINE.map((item) => {
                  const stat = division.headline[item.id];
                  return (
                    <td key={item.id}>
                      <div className="rate">{rate(stat)}</div>
                      <div className="sub">n={nOf(stat)}</div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="note">
        Rates pool every season in the archive. Open a league for season-by-season rates, Tuesday
        and Saturday splits, and team Top 10s.
      </p>
    </main>
  );
}
