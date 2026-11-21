import { readTypeBacktest } from '@/lib/data';

function pct(value: number | null): string {
  return value === null ? '–' : `${(value * 100).toFixed(1)}%`;
}

function signed(value: number | null): string {
  return value === null ? '–' : `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

function interval(low: number | null, high: number | null): string {
  return low === null || high === null ? '–' : `${signed(low)} to ${signed(high)}`;
}

export default function ReportPage() {
  const report = readTypeBacktest();

  if (!report) {
    return (
      <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
        No TYPE_RULE report yet. Regenerate it with the pipeline.
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
        <p className="max-w-3xl text-sm text-muted-foreground">
          Held-out seasons {first}–{last}. For every round the goals model and the empirical rates use
          matches before that round only; each row is calibrated with the target season&apos;s picker
          factors. No threshold is tuned on results.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">TYPE_RULE backtest · per group</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Used when Bet is a group or a single market. One passing bet per match per group (highest
          lift), sorted by lift. Returns are at fair odds; the interval is a 95% CI bootstrapped over
          round dates{bootstrap ? ` (${bootstrap.resamples.toLocaleString('en-GB')} resamples, seed ${bootstrap.seed})` : ''}.
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
    </div>
  );
}
