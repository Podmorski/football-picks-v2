import {
  readBestBetsRecord,
  readMozzartStatus,
  readMozzartVettedRecord,
  readTypeBacktest,
} from '@/lib/data';
import type { BestBetsRound, BestBetsSplit, MozzartStatusFile } from '@/lib/types';

function pct(value: number | null): string {
  return value === null ? '–' : `${(value * 100).toFixed(1)}%`;
}

function signed(value: number | null): string {
  return value === null ? '–' : `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

function interval(low: number | null, high: number | null): string {
  return low === null || high === null ? '–' : `${signed(low)} to ${signed(high)}`;
}

function split(split: BestBetsSplit): string {
  return `${split.landed} / ${split.settled}`;
}

function utcStamp(value: string | null): string {
  if (!value) return '–';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '–';
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC`;
}

const MOZZART_SCOPES: [string, string][] = [
  ['all', 'All passing picks'],
  ['passing_value', 'Passing + Mozzart >= fair'],
  ['any_value', 'Any priced bet + Mozzart >= fair'],
];

function PriceStatus({ status }: { status: MozzartStatusFile }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Price status</h2>
      <p className="text-sm text-muted-foreground">Aggregates only: no prices are stored in this repository.</p>
      {status.usage ? (
        <p className="text-sm">
          Requests this month: <span className="font-medium">{status.usage.used} / {status.usage.cap}</span>
          {status.last_run ? (
            <>
              {' · '}Last price run: <span className="font-medium">{status.last_run.ok ? 'ok' : 'failed'}</span>{' '}
              ({status.last_run.note}) {utcStamp(status.last_run.at)}
            </>
          ) : null}
        </p>
      ) : null}
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2 text-left font-semibold">Round</th>
              <th className="px-3 py-2 text-left font-semibold">Last fetch</th>
              <th className="px-3 py-2 text-right font-semibold">Priced</th>
              <th className="px-3 py-2 text-right font-semibold">Matched</th>
              <th className="px-3 py-2 text-right font-semibold">Unmatched</th>
            </tr>
          </thead>
          <tbody>
            {status.rounds.map((round) => (
              <tr key={round.round_date} className="border-t">
                <td className="px-3 py-1.5">{round.round_date}</td>
                <td className="px-3 py-1.5 text-muted-foreground">{utcStamp(round.last_fetch)}</td>
                <td className="tabular px-3 py-1.5 text-right">{round.priced}</td>
                <td className="tabular px-3 py-1.5 text-right">{round.matched}</td>
                <td className="tabular px-3 py-1.5 text-right">{round.unmatched}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function ReportPage() {
  const report = readTypeBacktest();
  const bestBets = readBestBetsRecord();
  const mozzart = readMozzartVettedRecord();
  const status = readMozzartStatus();
  const updated = utcStamp(new Date().toISOString());

  const settled = bestBets?.rounds.filter((round) => round.settled > 0) ?? [];
  const pending = bestBets?.rounds.filter((round) => round.settled === 0 && round.passing > 0) ?? [];

  if (!report) {
    return (
      <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
        No report data yet. Regenerate it with the pipeline.
      </p>
    );
  }

  const first = report.seasons[0] ?? '–';
  const last = report.seasons.at(-1) ?? '–';
  const bootstrap = report.bootstrap;

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">Report</h1>
        <p className="text-xs text-muted-foreground">Last updated: {updated}</p>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Weekly reporting is automatic: the pipeline rebuilds this page after every run, including the
          Monday settle. Held-out seasons {first}–{last}; every round uses matches before it only.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">TYPE_RULE backtest · per group</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Used when Bet is a group or a single market. One passing bet per match per group (highest
          probability), sorted by probability. Returns are at fair odds; the interval is a 95% CI
          bootstrapped over round dates{bootstrap ? ` (${bootstrap.resamples.toLocaleString('en-GB')} resamples, seed ${bootstrap.seed})` : ''}.
        </p>
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 text-left font-semibold">Group</th>
                <th className="px-3 py-2 text-right font-semibold">Rounds</th>
                <th className="px-3 py-2 text-right font-semibold">Picks</th>
                <th className="px-3 py-2 text-right font-semibold">Picks/round</th>
                <th className="px-3 py-2 text-right font-semibold">Landed</th>
                <th className="px-3 py-2 text-right font-semibold">Predicted</th>
                <th className="px-3 py-2 text-right font-semibold">Return</th>
                <th className="px-3 py-2 text-right font-semibold">Return 95% CI</th>
              </tr>
            </thead>
            <tbody>
              {report.groups.map((row) => (
                <tr key={row.group} className="border-t">
                  <td className="px-3 py-1.5 font-medium">{row.group}</td>
                  <td className="tabular px-3 py-1.5 text-right">{row.rounds.toLocaleString('en-GB')}</td>
                  <td className="tabular px-3 py-1.5 text-right">{row.picks.toLocaleString('en-GB')}</td>
                  <td className="tabular px-3 py-1.5 text-right">{row.picks_per_round === null ? '–' : row.picks_per_round.toFixed(2)}</td>
                  <td className="tabular px-3 py-1.5 text-right">{pct(row.landed)}</td>
                  <td className="tabular px-3 py-1.5 text-right">{pct(row.predicted)}</td>
                  <td className="tabular px-3 py-1.5 text-right font-medium">{signed(row.return)}</td>
                  <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">{interval(row.return_ci[0], row.return_ci[1])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted-foreground">
          Rule: lift ≥ usual × {report.rule.lift_multiplier} and ≥ usual + {(report.rule.lift_points * 100).toFixed(0)} pts · home/away
          records ≥ usual with n ≥ {report.rule.record_min_n} · |model − empirical| ≤ max({(report.rule.agreement_min * 100).toFixed(0)} pts,
          {' '}{(report.rule.agreement_fraction * 100).toFixed(0)}% of p) · fair ≤ {report.rule.max_fair_odds}.
          {report.note ? ` ${report.note}` : ''}
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Best bets results · Any bet</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Passing picks under {bestBets ? `fair ≥ ${bestBets.min_fair.toFixed(2)}` : 'the Any-bet rule'}, one per
          match. Expected is the sum of the shown probabilities. Strong is ≥{' '}
          {bestBets ? pct(bestBets.strong_probability) : '55.0%'}.
        </p>
        {settled.length === 0 ? (
          <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
            No settled rounds yet.{pending.length > 0 ? ` ${pending.map((round) => `${round.label}: ${round.passing}`).join(', ')} passing picks are awaiting results.` : ''}
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-3 py-2 text-left font-semibold">Round</th>
                  <th className="px-3 py-2 text-right font-semibold">Passing</th>
                  <th className="px-3 py-2 text-right font-semibold">Settled</th>
                  <th className="px-3 py-2 text-right font-semibold">Landed</th>
                  <th className="px-3 py-2 text-right font-semibold">Expected</th>
                  <th className="px-3 py-2 text-right font-semibold">Strong</th>
                  <th className="px-3 py-2 text-right font-semibold">Possible</th>
                </tr>
              </thead>
              <tbody>
                {settled.map((round: BestBetsRound) => (
                  <tr key={round.date} className="border-t">
                    <td className="px-3 py-1.5">
                      {round.label}
                      {round.kind === 'example' ? <span className="ml-1 text-xs text-muted-foreground">example</span> : null}
                    </td>
                    <td className="tabular px-3 py-1.5 text-right">{round.passing}</td>
                    <td className="tabular px-3 py-1.5 text-right">{round.settled}</td>
                    <td className="tabular px-3 py-1.5 text-right">{round.landed} of {round.settled}</td>
                    <td className="tabular px-3 py-1.5 text-right">{round.expected.toFixed(1)}</td>
                    <td className="tabular px-3 py-1.5 text-right">{split(round.strong)}</td>
                    <td className="tabular px-3 py-1.5 text-right">{split(round.possible)}</td>
                  </tr>
                ))}
                {bestBets ? (
                  <tr className="border-t bg-muted/40 font-medium">
                    <td className="px-3 py-1.5">Cumulative</td>
                    <td className="tabular px-3 py-1.5 text-right">{bestBets.cumulative.passing}</td>
                    <td className="tabular px-3 py-1.5 text-right">{bestBets.cumulative.settled}</td>
                    <td className="tabular px-3 py-1.5 text-right">{bestBets.cumulative.landed} of {bestBets.cumulative.settled}</td>
                    <td className="tabular px-3 py-1.5 text-right">{bestBets.cumulative.expected.toFixed(1)}</td>
                    <td className="tabular px-3 py-1.5 text-right">{split(bestBets.cumulative.strong)}</td>
                    <td className="tabular px-3 py-1.5 text-right">{split(bestBets.cumulative.possible)}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
        {pending.length > 0 ? (
          <p className="text-xs text-muted-foreground">
            Awaiting results: {pending.map((round) => `${round.label} (${round.passing})`).join(' · ')}.
          </p>
        ) : null}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Record at Mozzart prices</h2>
        {mozzart && mozzart.cumulative?.all?.n > 0 ? (
          <>
            <p className="text-sm text-muted-foreground">
              Settled rounds only. Return is at the Mozzart price; the 95% interval is bootstrapped over
              round dates. Aggregates only; no prices are stored here.
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
                  {MOZZART_SCOPES.map(([key, label]) => {
                    const summary = mozzart.cumulative[key];
                    if (!summary || summary.n === 0) return null;
                    return (
                      <tr key={key} className="border-t">
                        <td className="px-3 py-1.5">{label}</td>
                        <td className="tabular px-3 py-1.5 text-right">{summary.n.toLocaleString('en-GB')}</td>
                        <td className="tabular px-3 py-1.5 text-right">{pct(summary.landed)}</td>
                        <td className="tabular px-3 py-1.5 text-right font-medium">{signed(summary.return)}</td>
                        <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">{interval(summary.ci[0], summary.ci[1])}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
            No priced record in this build. Mozzart aggregates are embedded only in the priced production build.
          </p>
        )}
      </section>

      {status ? (
        <PriceStatus status={status} />
      ) : (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Price status</h2>
          <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
            Price status is embedded only in the priced production build.
          </p>
        </section>
      )}
    </div>
  );
}
