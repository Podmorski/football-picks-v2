import {
  readBestBetsRecord,
  readDataHealth,
  readForwardProposals,
  readForwardValidation,
  readMozzartStatus,
  readMozzartVettedRecord,
  readPreregistration,
  readTypeBacktest,
  readValueRecord,
} from '@/lib/data';
import type { BestBetsRound, DataHealthFile, ForwardProposalsFile, ForwardValidationFile, ForwardValidationSeries, MozzartStatusFile, PreregistrationFile, ValueSummaryRow } from '@/lib/types';

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

function DataHealthSection({ health }: { health: DataHealthFile | null }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Data health</h2>
      <p className="max-w-3xl text-sm text-muted-foreground">
        Each unsettled indexed round, its pending fixtures, the result source, the cached fallback attempt
        and the next scheduled retry. Aggregates only.
      </p>
      {!health ? (
        <p className="rounded-xl border border-dashed px-4 py-4 text-sm text-muted-foreground">No data health file yet; the next pipeline run writes it.</p>
      ) : (
        <>
          <p className="text-sm">
            Latest football-data result date: <span className="font-medium">{health.latest_football_data_result_date ?? 'unknown'}</span>
          </p>
          {health.unsettled_rounds.length === 0 ? (
            <p className="rounded-xl border border-dashed px-4 py-4 text-sm text-muted-foreground">No unsettled indexed round.</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-3 py-2 text-left font-semibold">Round</th>
                    <th className="px-3 py-2 text-right font-semibold">Fixtures</th>
                    <th className="px-3 py-2 text-right font-semibold">Pending</th>
                    <th className="px-3 py-2 text-right font-semibold">Settled by source</th>
                    <th className="px-3 py-2 text-left font-semibold">Fallback attempt</th>
                    <th className="px-3 py-2 text-left font-semibold">Pending reasons</th>
                    <th className="px-3 py-2 text-left font-semibold">Next retry</th>
                  </tr>
                </thead>
                <tbody>
                  {health.unsettled_rounds.map((round) => (
                    <tr key={round.date} className="border-t align-top">
                      <td className="px-3 py-1.5">{round.label}</td>
                      <td className="tabular px-3 py-1.5 text-right">{round.fixtures}</td>
                      <td className="tabular px-3 py-1.5 text-right">{round.pending_fixtures}</td>
                      <td className="tabular px-3 py-1.5 text-right text-xs">
                        football-data {round.sources.football_data_fixtures} · API-Football {round.sources.api_football_fixtures} · unknown {round.sources.unknown_fixtures}
                      </td>
                      <td className="px-3 py-1.5 text-xs">
                        {round.fallback.attempted
                          ? `${round.fallback.requests ?? 0} req · ${round.fallback.matched ?? 0} matched · ${round.fallback.ambiguous ?? 0} ambiguous · ${round.fallback.unmatched ?? 0} unmatched`
                          : round.fallback.reason ?? 'not attempted'}
                      </td>
                      <td className="px-3 py-1.5 text-xs">
                        source-pending {round.pending_reasons.source_pending_fixtures} · ambiguous {round.pending_reasons.ambiguous_fixtures} · unmatched {round.pending_reasons.unmatched_fixtures}
                        {round.pending_reasons.source_pending_sample.length > 0
                          ? ` (e.g. ${round.pending_reasons.source_pending_sample.join('; ')})`
                          : ''}
                      </td>
                      <td className="px-3 py-1.5 text-xs">{round.next_retry}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function ForwardProposalsSection({ forward }: { forward: ForwardProposalsFile | null }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Forward proposals</h2>
      <p className="max-w-3xl text-sm text-muted-foreground">
        Frozen automatic tickets are separate from Best bets. Counts are aggregate; actual leg and ticket
        prices stay in the private store.
      </p>
      {!forward ? (
        <p className="rounded-xl border border-dashed px-4 py-4 text-sm text-muted-foreground">No forward proposal record yet.</p>
      ) : (
        <>
          <p className="text-sm">
            Activation <span className="font-medium">{forward.activation_date}</span> · policy{' '}
            <span className="font-medium">{forward.policy_version}</span> · construction{' '}
            <span className="font-medium">{forward.construction_version}</span> · eligible round{' '}
            <span className="font-medium">{forward.eligible_round ?? 'none yet'}</span>
          </p>
          <p className="text-sm"><span className="font-medium">State:</span> {forward.state}</p>
          {forward.errors.length > 0 ? (
            <ul className="rounded-xl border border-dashed px-4 py-3 text-sm text-muted-foreground">
              {forward.errors.map((error) => <li key={error}>{error}</li>)}
            </ul>
          ) : null}
          <div className="grid gap-2 text-sm sm:grid-cols-2">
            <p>Tickets: <span className="font-medium">{forward.counts.available} available / {forward.counts.unavailable} unavailable</span></p>
            <p>Preferred band: <span className="font-medium">{forward.counts.bands.preferred ?? 0}</span> · outside {forward.counts.bands.outside ?? 0} · below floor {forward.counts.bands.below_floor ?? 0}</p>
            <p>Individual floor relaxed: <span className="font-medium">{forward.counts.individual_floor_relaxed}</span> · overlap relaxed {forward.counts.overlap_relaxed}</p>
            <p>Negative model EV: <span className="font-medium">{forward.counts.negative_model_ev}</span> ({forward.counts.negative_model_ev_share === null ? '–' : pct(forward.counts.negative_model_ev_share)})</p>
            <p>Price coverage: <span className="font-medium">{forward.price_coverage.priced_fixtures} / {forward.price_coverage.fixtures}</span> fixtures · {forward.price_coverage.priced_markets} priced markets</p>
            <p>Started not priced: {forward.price_coverage.started_not_priced} · unmatched fixtures {forward.price_coverage.unmatched_fixtures}</p>
          </div>
          <p className="text-sm">
            Paper results: flat ROI {signed(typeof forward.results.flat.roi === 'number' ? forward.results.flat.roi : null)} · MEL ROI{' '}
            {signed(typeof forward.results.mel.roi === 'number' ? forward.results.mel.roi : null)} · settled tickets {forward.results.counts.settled ?? 0} · pending {forward.results.counts.pending ?? 0}.
            {' '}{forward.results.note}
          </p>
        </>
      )}
    </section>
  );
}

function PreregistrationSection({ prereg }: { prereg: PreregistrationFile | null }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Pre-registration · construction and staking</h2>
      {!prereg ? (
        <p className="rounded-xl border border-dashed px-4 py-4 text-sm text-muted-foreground">No pre-registration file yet.</p>
      ) : (
        <>
          <p className="max-w-3xl text-sm text-muted-foreground">
            {prereg.construction_version} · {prereg.policy_version} · proposal schema {prereg.proposal_schema_version} · activation {prereg.activation_date}.
            Primary comparison: {prereg.primary_comparison.join(' and ')}. Exploratory: {prereg.exploratory.join(', ')}.
          </p>
          <ul className="space-y-1 text-sm">
            <li>One-sided alpha {String(prereg.protocol.alpha_one_sided)}, power {String(prereg.protocol.power)}, meaningful alternative {pct(Number(prereg.protocol.meaningful_roi_equivalent))} ROI-equivalent.</li>
            <li>N* rule: {String(prereg.protocol.n_star_rule)}; {String(prereg.protocol.n_star_unavailable)}.</li>
            <li>Evidence: {String(prereg.protocol.evidence_rule)}. {String(prereg.protocol.inconclusive_rule)}.</li>
            <li>No early efficacy stopping; safety review at {pct(Number(prereg.protocol.safety_review_drawdown))} realised drawdown or any identity/accounting failure.</li>
            <li>Stop adaptive staking if {String(prereg.protocol.stop_adaptive_rule)}.</li>
          </ul>
          <p className="max-w-3xl text-sm text-muted-foreground">{prereg.research_note}</p>
          <p className="max-w-3xl text-xs text-muted-foreground">{prereg.version_rule}</p>
        </>
      )}
    </section>
  );
}

function validationRow(label: string, series: ForwardValidationSeries) {
  return (
    <tr key={label} className="border-t">
      <td className="px-3 py-1.5 font-medium">{label}</td>
      <td className="tabular px-3 py-1.5 text-right">{series.terminal_rounds}</td>
      <td className="tabular px-3 py-1.5 text-right">{signed(series.roi)}</td>
      <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">{interval(series.bootstrap.roi_ci[0], series.bootstrap.roi_ci[1])}</td>
      <td className="tabular px-3 py-1.5 text-right">{series.bootstrap.mean_log_growth === null ? '–' : `${(series.bootstrap.mean_log_growth * 100).toFixed(2)}%`}</td>
      <td className="tabular px-3 py-1.5 text-right text-xs text-muted-foreground">{interval(series.bootstrap.log_growth_ci[0], series.bootstrap.log_growth_ci[1])}</td>
      <td className="tabular px-3 py-1.5 text-right">{pct(series.maximum_drawdown)}</td>
      <td className="tabular px-3 py-1.5 text-right">{pct(series.losing_round_frequency)}</td>
    </tr>
  );
}

function ForwardValidationSection({ validation }: { validation: ForwardValidationFile | null }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Forward validation · actual prices only</h2>
      <p className="max-w-3xl text-sm text-muted-foreground">
        Whole round dates are resampled with every ticket and leg retained; bankroll, unresolved exposure and
        drawdown are replayed through each sequence. No retrospective fair-odds substitution.
      </p>
      {!validation ? (
        <p className="rounded-xl border border-dashed px-4 py-4 text-sm text-muted-foreground">No forward validation file yet.</p>
      ) : (
        <>
          <p className="text-sm"><span className="font-medium">State:</span> {validation.state} · rounds {validation.counts.rounds} · settled playable {validation.counts.terminal_rounds} · void {validation.counts.void} · pending {validation.counts.pending}</p>
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-3 py-2 text-left font-semibold">Policy</th>
                  <th className="px-3 py-2 text-right font-semibold">Rounds</th>
                  <th className="px-3 py-2 text-right font-semibold">ROI</th>
                  <th className="px-3 py-2 text-right font-semibold">95% CI</th>
                  <th className="px-3 py-2 text-right font-semibold">Mean log growth</th>
                  <th className="px-3 py-2 text-right font-semibold">95% CI</th>
                  <th className="px-3 py-2 text-right font-semibold">Max DD</th>
                  <th className="px-3 py-2 text-right font-semibold">Losing rounds</th>
                </tr>
              </thead>
              <tbody>
                {validationRow('Flat (primary)', validation.primary.flat)}
                {validationRow('MEL-v1 (primary)', validation.primary.mel)}
                {Object.entries(validation.exploratory).map(([key, series]) => (
                  <tr key={key} className="border-t text-muted-foreground">
                    <td className="px-3 py-1.5">{key} (exploratory)</td>
                    <td className="tabular px-3 py-1.5 text-right">{series.terminal_rounds}</td>
                    <td className="tabular px-3 py-1.5 text-right">{signed(series.roi)}</td>
                    <td className="tabular px-3 py-1.5 text-right text-xs">–</td>
                    <td className="tabular px-3 py-1.5 text-right">–</td>
                    <td className="tabular px-3 py-1.5 text-right text-xs">–</td>
                    <td className="tabular px-3 py-1.5 text-right">{pct(series.maximum_drawdown)}</td>
                    <td className="tabular px-3 py-1.5 text-right">–</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid gap-1 text-sm sm:grid-cols-2">
            <p>N*: <span className="font-medium">{validation.power.n_star ?? 'not estimable'}</span>{validation.power.reason ? ` — ${validation.power.reason}` : ''}</p>
            <p>Settled playable rounds: <span className="font-medium">{validation.evidence.settled_playable_rounds}</span> · positive evidence {validation.evidence.positive ? 'yes' : 'no'} · inconclusive {validation.evidence.inconclusive ? 'yes' : 'no'}</p>
            <p>Maximum drawdown: <span className="font-medium">{pct(validation.safety.maximum_drawdown)}</span> · review {validation.safety.drawdown_review ? 'required' : 'not triggered'}</p>
            <p>Void frequency: {pct(validation.counts.void_frequency ?? null)} · pending frequency {pct(validation.counts.pending_frequency ?? null)} · unresolved exposure (MEL) {validation.primary.mel.unresolved_exposure?.toFixed(2) ?? '–'}</p>
            <p>Ruin upper 95% ({validation.protocol.stop_adaptive_rule ? '52 rounds' : '52 rounds'}): <span className="font-medium">{validation.safety.ruin_upper_95 === null ? 'not estimable' : pct(validation.safety.ruin_upper_95)}</span> · stop adaptive {validation.safety.stop_adaptive ? 'yes' : 'no'}</p>
            <p>Exposure by type (MEL): {Object.entries(validation.exposure.by_type_mel_stake).map(([key, value]) => `${key} ${value.toFixed(2)}`).join(' · ')}</p>
            <p>Shared leg instances: {validation.exposure.shared_leg_instances} · tickets {validation.exposure.shared_leg_tickets} · fallbacks outside band {validation.fallbacks.outside_preferred_band ?? 0} · bounded DP {validation.fallbacks.bounded_dp ?? 0} · fallback frequency {validation.fallbacks.fallback_frequency === null || validation.fallbacks.fallback_frequency === undefined ? '–' : pct(validation.fallbacks.fallback_frequency as number)}</p>
            <p>Negative model EV share: {validation.fallbacks.negative_model_ev_share === null ? '–' : pct(validation.fallbacks.negative_model_ev_share as number)}</p>
            {validation.small_sample ? <p>Small sample: fewer than 30 settled playable rounds. {validation.multiple_comparisons}</p> : null}
          </div>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {validation.notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </>
      )}
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
  const dataHealth = readDataHealth();
  const forwardProposals = readForwardProposals();
  const preregistration = readPreregistration();
  const forwardValidation = readForwardValidation();

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

      <DataHealthSection health={dataHealth} />
      <ForwardProposalsSection forward={forwardProposals} />
      <PreregistrationSection prereg={preregistration} />
      <ForwardValidationSection validation={forwardValidation} />

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Legacy research · STRICT_checks TYPE_RULE cohort · per group</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Legacy research only. This is not the current Best bets list, which is the unified inclusive
          58% calibrated-probability list. It applies TYPE_RULE before the UI minimum-fair filter and
          returns at fair odds, not realised Mozzart profit. The interval is a 95% CI bootstrapped over
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
        <h2 className="text-lg font-semibold">Best bets results · unified 58% selection</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Current Best bets record: calibrated probability ≥{' '}
          {bestBets ? pct(bestBets.min_pc) : '58.0%'}, fair odds ≥ {bestBets?.min_fair?.toFixed(2) ?? '1.20'} (the Any-bet
          default), one pick per match by highest pc.
          Expected is the sum of shown probabilities over settled rows only, where settled means
          Landed or Lost; Void and Pending are separate buckets.
        </p>
        <p className="max-w-3xl rounded-xl border border-dashed px-4 py-3 text-sm text-muted-foreground">
          The 14 Nov row is a retrospective example generated after the fixture; not forward
          performance. Under the 1.20 minimum-fair default its 48 selections are 36 landed, 10 lost
          and 2 void; none is GOAL_RANGE_FT:1+, and median selected fair odds are approximately 1.218.
          This is not evidence of positive expected value or realised bookmaker profit.
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
                  <th className="px-3 py-2 text-right font-semibold">Lost</th>
                  <th className="px-3 py-2 text-right font-semibold">Void</th>
                  <th className="px-3 py-2 text-right font-semibold">Pending</th>
                  <th className="px-3 py-2 text-right font-semibold">Expected (settled)</th>
                </tr>
              </thead>
              <tbody>
                {settled.map((round: BestBetsRound) => (
                  <tr key={round.date} className="border-t">
                    <td className="px-3 py-1.5">
                      {round.label}
                      {round.kind === 'example' ? <span className="ml-1 text-xs text-muted-foreground">Retrospective example generated after the fixture; not forward performance</span> : null}
                    </td>
                    <td className="tabular px-3 py-1.5 text-right">{round.passing}</td>
                    <td className="tabular px-3 py-1.5 text-right">{round.settled}</td>
                    <td className="tabular px-3 py-1.5 text-right">{round.landed}</td>
                    <td className="tabular px-3 py-1.5 text-right">{round.lost}</td>
                    <td className="tabular px-3 py-1.5 text-right">{round.void}</td>
                    <td className="tabular px-3 py-1.5 text-right">{round.pending}</td>
                    <td className="tabular px-3 py-1.5 text-right">{round.expected.toFixed(1)}</td>
                  </tr>
                ))}
                {bestBets ? (
                  <tr className="border-t bg-muted/40 font-medium">
                    <td className="px-3 py-1.5">Cumulative</td>
                    <td className="tabular px-3 py-1.5 text-right">{bestBets.cumulative.passing}</td>
                    <td className="tabular px-3 py-1.5 text-right">{bestBets.cumulative.settled}</td>
                    <td className="tabular px-3 py-1.5 text-right">{bestBets.cumulative.landed}</td>
                    <td className="tabular px-3 py-1.5 text-right">{bestBets.cumulative.lost}</td>
                    <td className="tabular px-3 py-1.5 text-right">{bestBets.cumulative.void}</td>
                    <td className="tabular px-3 py-1.5 text-right">{bestBets.cumulative.pending}</td>
                    <td className="tabular px-3 py-1.5 text-right">{bestBets.cumulative.expected.toFixed(1)}</td>
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
