import {
  readBestBetsRecord,
  readMozzartStatus,
  readMozzartVettedRecord,
  readTypeBacktest,
  readValueRecord,
} from '@/lib/data';
import type { BestBetsRound, BestBetsSplit, MozzartStatusFile, ValueSummaryRow } from '@/lib/types';

function pct(value: number | null): string {
  return value === null ? '–' : `${(value * 100).toFixed(1)}%`;
}

function signed(value: number | null): string {
  return value === null ? '–' : `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

function interval(low: number | null, high: number | null): string {
  return low === null || high === null ? '–' : `${signed(low)} to ${signed(high)}`;
}

function units(value: number | null): string {
  return value === null ? '–' : `${value > 0 ? '+' : ''}${value.toFixed(2)}`;
}

function ValueTable({ label, summary }: { label: string; summary: ValueSummaryRow }) {
  return (
    <tr className="border-t">
      <td className="px-3 py-1.5">{label}</td>
      <td className="tabular px-3 py-1.5 text-right">{summary.bets}</td>
      <td className="tabular px-3 py-1.5 text-right">{summary.landed}</td>
      <td className="tabular px-3 py-1.5 text-right">{summary.needed.toFixed(2)}</td>
      <td className="tabular px-3 py-1.5 text-right">{units(summary.profit)}</td>
      <td className="tabular px-3 py-1.5 text-right font-medium">{signed(summary.return)}</td>
      <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">{interval(summary.ci[0], summary.ci[1])}</td>
    </tr>
  );
}

function ValueSplitRow({ label, summary }: { label: string; summary: ValueSummaryRow }) {
  return (
    <tr className="border-t">
      <td className="px-3 py-1.5">{label}</td>
      <td className="tabular px-3 py-1.5 text-right">{summary.bets}</td>
      <td className="tabular px-3 py-1.5 text-right">{summary.landed}</td>
      <td className="tabular px-3 py-1.5 text-right">{summary.needed.toFixed(2)}</td>
      <td className="tabular px-3 py-1.5 text-right">{units(summary.profit)}</td>
      <td className="tabular px-3 py-1.5 text-right font-medium">{signed(summary.return)}</td>
    </tr>
  );
}

function ProfitChart({ points }: { points: { date: string; profit: number }[] }) {
  if (points.length === 0) return null;
  const values = points.map((point) => point.profit);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const span = max - min || 1;
  const width = 560;
  const height = 120;
  const left = 20;
  const top = 10;
  const x = (index: number) => left + (points.length === 1 ? width / 2 : (index / (points.length - 1)) * width);
  const y = (value: number) => top + height - ((value - min) / span) * height;
  const path = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(index).toFixed(1)} ${y(point.profit).toFixed(1)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${left * 2 + width} ${height + top * 2}`} className="h-40 w-full text-foreground" role="img" aria-label="Cumulative profit chart">
      <line x1={left} y1={y(0)} x2={left + width} y2={y(0)} stroke="currentColor" strokeOpacity="0.2" />
      <path d={path} fill="none" stroke="currentColor" strokeWidth="2" />
      {points.map((point, index) => (
        <circle key={point.date} cx={x(index)} cy={y(point.profit)} r="2.5" fill="currentColor" />
      ))}
    </svg>
  );
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
  const valueRecord = readValueRecord();

  const settled = bestBets?.rounds.filter((round) => round.settled > 0) ?? [];
  const pending = bestBets?.rounds.filter((round) => round.settled === 0 && round.passing > 0) ?? [];

  if (!report) {
    return (
      <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
        No report data yet. Regenerate it with the pipeline.
      </p>
    );
  }

  const bootstrap = report.bootstrap;

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">Report</h1>
        <p className="text-xs text-muted-foreground">Last updated: {updated}</p>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Walk-forward over 2019-20..2025-26. Every round uses matches before it only; each row is
          calibrated with the target season&apos;s picker factors. No threshold is tuned on results.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">STRICT_checks cohort · TYPE_RULE research backtest · per group</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          This is the existing TYPE_RULE research cohort, not the default Ranked group/market list. It
          applies TYPE_RULE before the UI minimum-fair filter. One pick per match by highest probability,
          sorted by probability; selection is by probability, not lift. Returns are at fair odds, not
          realised Mozzart profit. Ranked mode has no established profitability record; this table does
          not measure it. The interval is a 95% CI bootstrapped over round dates{bootstrap ? ` (${bootstrap.resamples.toLocaleString('en-GB')} resamples, seed ${bootstrap.seed})` : ''}.
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
                <th className="px-3 py-2 text-right font-semibold">Return (fair)</th>
                <th className="px-3 py-2 text-right font-semibold">95% CI</th>
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
        </p>
        <p className="text-xs text-muted-foreground">
          Footnote: one pick per match, highest probability. Weekly reporting is automatic: the pipeline
          rebuilds this page after every run, including the Monday settle.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Best bets results · Any bet</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          This is the Any-bet record only. It does not measure the Ranked group/market mode. Passing picks
          under {bestBets ? `fair ≥ ${bestBets.min_fair.toFixed(2)}` : 'the Any-bet rule'}, one per match.
          Expected is the sum of the shown probabilities. Strong is ≥{' '}
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

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Value bets at Mozzart prices</h2>
        {valueRecord ? (
          <>
            <p className="text-sm text-muted-foreground">
              Flat 1 unit at the Mozzart snapshot price. Needed is the sum of 1/price; profit is in units.
              Settled rounds only; the 95% CI is bootstrapped over round dates (2,000, seed 20261025).
            </p>
            {valueRecord.cumulative.bets === 0 ? (
              <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
                No settled Value bets yet. They appear after the Monday settle.
              </p>
            ) : (
              <>
                <div className="overflow-x-auto rounded-xl border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                        <th className="px-3 py-2 text-left font-semibold">Scope</th>
                        <th className="px-3 py-2 text-right font-semibold">Bets</th>
                        <th className="px-3 py-2 text-right font-semibold">Landed</th>
                        <th className="px-3 py-2 text-right font-semibold">Needed</th>
                        <th className="px-3 py-2 text-right font-semibold">Profit (units)</th>
                        <th className="px-3 py-2 text-right font-semibold">Return</th>
                        <th className="px-3 py-2 text-right font-semibold">95% CI</th>
                      </tr>
                    </thead>
                    <tbody><ValueTable label="Cumulative" summary={valueRecord.cumulative} /></tbody>
                  </table>
                </div>

                <h3 className="text-sm font-semibold">Value bets per round</h3>
                <div className="overflow-x-auto rounded-xl border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                        <th className="px-3 py-2 text-left font-semibold">Round</th>
                        <th className="px-3 py-2 text-right font-semibold">Bets</th>
                        <th className="px-3 py-2 text-right font-semibold">Landed</th>
                        <th className="px-3 py-2 text-right font-semibold">Needed</th>
                        <th className="px-3 py-2 text-right font-semibold">Profit</th>
                        <th className="px-3 py-2 text-right font-semibold">Return</th>
                        <th className="px-3 py-2 text-right font-semibold">95% CI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {valueRecord.rounds.map((round) => (
                        <ValueTable key={round.date} label={round.label} summary={round.summary} />
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold">By bet group</h3>
                    <div className="overflow-x-auto rounded-xl border">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                            <th className="px-3 py-2 text-left font-semibold">Group</th>
                            <th className="px-3 py-2 text-right font-semibold">Bets</th>
                            <th className="px-3 py-2 text-right font-semibold">Landed</th>
                            <th className="px-3 py-2 text-right font-semibold">Needed</th>
                            <th className="px-3 py-2 text-right font-semibold">Profit</th>
                            <th className="px-3 py-2 text-right font-semibold">Return</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(valueRecord.groups).map(([group, summary]) => (
                            <ValueSplitRow key={group} label={group} summary={summary} />
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold">By odds band</h3>
                    <div className="overflow-x-auto rounded-xl border">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                            <th className="px-3 py-2 text-left font-semibold">Band</th>
                            <th className="px-3 py-2 text-right font-semibold">Bets</th>
                            <th className="px-3 py-2 text-right font-semibold">Landed</th>
                            <th className="px-3 py-2 text-right font-semibold">Needed</th>
                            <th className="px-3 py-2 text-right font-semibold">Profit</th>
                            <th className="px-3 py-2 text-right font-semibold">Return</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(valueRecord.bands).map(([band, summary]) => (
                            <ValueSplitRow key={band} label={band} summary={summary} />
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                <h3 className="text-sm font-semibold">Cumulative profit</h3>
                <ProfitChart points={valueRecord.profit_series} />
              </>
            )}
          </>
        ) : (
          <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
            Value tracking is generated by the update workflow; it is not in this build.
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
