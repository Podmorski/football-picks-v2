'use client';

import { useEffect, useState } from 'react';

import type {
  DescriptiveFile,
  DescriptiveFixture,
  DescriptiveFrequency,
  DescriptiveH2H,
  DescriptiveResultFrequency,
  DescriptiveStreaks,
  DescriptiveTeam,
  DescriptiveWindow,
} from '@/lib/types';

const HTFT_CODES = ['1-1', '1-X', '1-2', 'X-1', 'X-X', 'X-2', '2-1', '2-X', '2-2'];
const STREAKS: { key: keyof DescriptiveStreaks; label: string }[] = [
  { key: 'win', label: 'Win' },
  { key: 'unbeaten', label: 'Unbeaten' },
  { key: 'winless', label: 'Winless' },
  { key: 'losing', label: 'Losing' },
  { key: 'drawing', label: 'Drawing' },
  { key: 'btts', label: 'BTTS' },
  { key: 'no_btts', label: 'No BTTS' },
  { key: 'over25', label: 'Over 2.5' },
  { key: 'under25', label: 'Under 2.5' },
];

const CACHE = new Map<string, Promise<DescriptiveFile | null>>();

function loadSidecar(date: string): Promise<DescriptiveFile | null> {
  const cached = CACHE.get(date);
  if (cached) return cached;
  const pending = fetch(`/data/descriptive/${date}.json`).then(async (response) => {
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`statistics request failed: ${response.status}`);
    const payload = await response.json() as DescriptiveFile;
    if (payload.schema_version !== 1 || !Array.isArray(payload.fixtures)) {
      throw new Error('unsupported statistics schema');
    }
    return payload;
  });
  CACHE.set(date, pending);
  pending.catch(() => CACHE.delete(date));
  return pending;
}

function pct(rate: number | null): string {
  return rate === null ? '—' : `${(rate * 100).toFixed(1)}%`;
}

function RateTable({ title, frequency }: { title: string; frequency: DescriptiveResultFrequency }) {
  return (
    <table className="w-full text-xs">
      <caption className="pb-1 text-left font-medium text-foreground">
        {title} <span className="font-normal text-muted-foreground">(n={frequency.n})</span>
      </caption>
      <thead>
        <tr className="text-muted-foreground">
          {['1', 'X', '2'].map((code) => <th key={code} className="py-1 text-left font-medium">{code}</th>)}
        </tr>
      </thead>
      <tbody>
        <tr className="tabular">
          {(['1', 'X', '2'] as const).map((code) => <td key={code} className="py-0.5">{pct(frequency[code])}</td>)}
        </tr>
      </tbody>
    </table>
  );
}

function FrequencyBlock({ window }: { window: DescriptiveWindow }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <RateTable title="FT result" frequency={window.ft} />
      <RateTable title="HT result" frequency={window.ht} />
      <table className="w-full text-xs">
        <caption className="pb-1 text-left font-medium text-foreground">
          BTTS and goals <span className="font-normal text-muted-foreground">(n={window.n})</span>
        </caption>
        <tbody>
          <tr><th className="py-0.5 text-left font-medium text-muted-foreground">BTTS yes</th><td className="tabular py-0.5">{window.btts.count} · {pct(window.btts.rate)}</td></tr>
          <tr><th className="py-0.5 text-left font-medium text-muted-foreground">Over 2.5</th><td className="tabular py-0.5">{window.over25.count} · {pct(window.over25.rate)}</td></tr>
        </tbody>
      </table>
      <table className="w-full text-xs">
        <caption className="pb-1 text-left font-medium text-foreground">
          HT/FT <span className="font-normal text-muted-foreground">(n={window.htft.n})</span>
        </caption>
        <tbody>
          <tr>
            {HTFT_CODES.slice(0, 5).map((code) => (
              <th key={code} className="py-0.5 text-left font-medium text-muted-foreground">{code}</th>
            ))}
          </tr>
          <tr className="tabular">
            {HTFT_CODES.slice(0, 5).map((code) => <td key={code}>{pct(window.htft[code])}</td>)}
          </tr>
          <tr>
            {HTFT_CODES.slice(5).map((code) => (
              <th key={code} className="py-0.5 text-left font-medium text-muted-foreground">{code}</th>
            ))}
          </tr>
          <tr className="tabular">
            {HTFT_CODES.slice(5).map((code) => <td key={code}>{pct(window.htft[code])}</td>)}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function WindowSummary({ windows, venue }: { windows: DescriptiveTeam['windows']; venue: string }) {
  const rows = [
    ['Overall — last 6', windows.overall6],
    ['Overall — last 12', windows.overall12],
    [`${venue} — last 6`, windows.venue6],
    [`${venue} — last 12`, windows.venue12],
  ] as const;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-muted-foreground">
            <th className="py-1 text-left font-medium">Window</th>
            <th className="py-1 text-right font-medium">n</th>
            <th className="py-1 text-right font-medium">W-D-L</th>
            <th className="py-1 text-right font-medium">GF–GA</th>
            <th className="py-1 text-right font-medium">GF/GA per match</th>
            <th className="py-1 text-right font-medium">Pts/match</th>
            <th className="py-1 text-right font-medium">BTTS</th>
            <th className="py-1 text-right font-medium">Over 2.5</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, window]) => (
            <tr key={label} className="border-t">
              <th className="py-1.5 text-left font-medium">{label}</th>
              <td className="tabular py-1.5 text-right">{window.n}</td>
              <td className="tabular py-1.5 text-right">{window.w}-{window.d}-{window.l}</td>
              <td className="tabular py-1.5 text-right">{window.gf}–{window.ga}</td>
              <td className="tabular py-1.5 text-right">{window.gf_pm ?? '—'} / {window.ga_pm ?? '—'}</td>
              <td className="tabular py-1.5 text-right">{window.points_pm ?? '—'}</td>
              <td className="tabular py-1.5 text-right">{pct(window.btts.rate)}</td>
              <td className="tabular py-1.5 text-right">{pct(window.over25.rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StreakRows({ label, streaks }: { label: string; streaks: DescriptiveStreaks }) {
  return (
    <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
      <span className="font-medium text-foreground">{label}:</span>
      {STREAKS.map(({ key, label: name }) => <span key={key}>{name} {streaks[key]}</span>)}
    </p>
  );
}

function TeamSection({ title, team, venue }: { title: string; team: DescriptiveTeam; venue: string }) {
  const frequencies = [
    ['Overall — last 6', team.windows.overall6],
    ['Overall — last 12', team.windows.overall12],
    [`${venue} — last 6`, team.windows.venue6],
    [`${venue} — last 12`, team.windows.venue12],
  ] as const;
  return (
    <section className="min-w-0 space-y-2 rounded-lg border p-3">
      <h4 className="font-semibold text-foreground">{title}</h4>
      <WindowSummary windows={team.windows} venue={venue} />
      <div className="space-y-1">
        <StreakRows label="Overall streaks" streaks={team.streaks.overall} />
        <StreakRows label={`${venue} streaks`} streaks={team.streaks.venue} />
      </div>
      <div className="space-y-1">
        {frequencies.map(([label, window]) => (
          <details key={label} className="rounded-md border px-2 py-1 text-xs">
            <summary className="cursor-pointer font-medium text-foreground">
              Historical frequencies — {label} (n={window.n})
            </summary>
            <div className="mt-2">
              {window.n === 0 ? <p className="text-muted-foreground">No completed matches in this window.</p> : <FrequencyBlock window={window} />}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

function H2HSection({ h2h }: { h2h: DescriptiveH2H }) {
  return (
    <section className="space-y-2 rounded-lg border p-3">
      <h4 className="font-semibold text-foreground">Head-to-head — prior main-division league meetings</h4>
      {h2h.n === 0 ? (
        <p className="text-xs text-muted-foreground">No prior main-division league meetings in the loaded history.</p>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            Sample n={h2h.n} · current home team W-D-L {h2h.w}-{h2h.d}-{h2h.l} · goals {h2h.gf}–{h2h.ga} · BTTS {pct(h2h.btts.rate)} · Over 2.5 {pct(h2h.over25.rate)}
          </p>
          <ul className="space-y-1 text-xs">
            {h2h.meetings.map((meeting) => (
              <li key={`${meeting.date}|${meeting.home}|${meeting.away}`} className="tabular">
                <span className="text-muted-foreground">{meeting.date}</span> · {meeting.home} {meeting.fthg}–{meeting.ftag} {meeting.away}
                <span className="text-muted-foreground"> (HT {meeting.hthg ?? '—'}–{meeting.htag ?? '—'})</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function hasAnyHistory(fixture: DescriptiveFixture): boolean {
  const windows = [
    ...Object.values(fixture.home.windows),
    ...Object.values(fixture.away.windows),
  ];
  return windows.some((window) => window.n > 0) || fixture.h2h.n > 0;
}

export default function MatchStats({ date, div, home, away }: { date: string; div: string; home: string; away: string }) {
  const [state, setState] = useState<
    { status: 'loading' } | { status: 'error' } | { status: 'unavailable' } | { status: 'ready'; fixture: DescriptiveFixture }
  >({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      setState({ status: 'unavailable' });
      return () => { cancelled = true; };
    }
    loadSidecar(date).then((payload) => {
      if (cancelled) return;
      const fixture = payload?.fixtures.find((item) => item.d === div && item.h === home && item.a === away);
      if (!fixture || !hasAnyHistory(fixture)) {
        setState({ status: 'unavailable' });
        return;
      }
      setState({ status: 'ready', fixture });
    }).catch(() => {
      if (!cancelled) setState({ status: 'error' });
    });
    return () => { cancelled = true; };
  }, [date, div, home, away]);

  return (
    <section className="mt-3 space-y-3 border-t pt-3" aria-label="Match statistics">
      <div>
        <h3 className="text-sm font-semibold text-foreground">Match statistics — history before this fixture</h3>
        <p className="text-xs text-muted-foreground">Historical frequencies describe past matches; they are not calibrated chances.</p>
      </div>
      {state.status === 'loading' ? <p className="text-xs text-muted-foreground" role="status">Loading statistics.</p> : null}
      {state.status === 'error' ? <p className="text-xs text-muted-foreground" role="alert">Statistics could not be loaded.</p> : null}
      {state.status === 'unavailable' ? <p className="text-xs text-muted-foreground">No statistics available for this round/fixture.</p> : null}
      {state.status === 'ready' ? (
        <div className="space-y-3">
          <div className="grid gap-3 lg:grid-cols-2">
            <TeamSection title={`Home team — ${home}`} team={state.fixture.home} venue="Home" />
            <TeamSection title={`Away team — ${away}`} team={state.fixture.away} venue="Away" />
          </div>
          <H2HSection h2h={state.fixture.h2h} />
          <p className="text-xs text-muted-foreground">Historical frequencies describe past matches; they are not calibrated chances.</p>
        </div>
      ) : null}
    </section>
  );
}
