'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';

import {
  combinedFair,
  combinedMozzart,
  combinedProbability,
  legKey,
  loadTickets,
  overallStatus,
  removeTicket,
  type SavedTicket,
} from '@/lib/ticket';
import { paperSettlement, proposalKey, sharedCounts, type LegStatuses } from '@/lib/proposals';
import type { PrivateProposalsFile, ProposalRecordFile, ProposedTicket, RetrospectiveFile, RetrospectiveProposal } from '@/lib/types';

function pct(value: number | null): string {
  return value === null ? '–' : `${(value * 100).toFixed(1)}%`;
}

function units(value: number | null): string {
  return value === null ? '–' : `${value > 0 ? '+' : ''}${value.toFixed(2)}`;
}

function rate(value: number | null): string {
  return value === null ? '–' : `${(value * 100).toFixed(1)}%`;
}

function decodeRows(payload: Record<string, unknown>): { d: string; h: string; a: string; m: string; st?: string }[] {
  const raw = (payload.rows ?? []) as unknown[];
  if (!raw.length || !Array.isArray(raw[0])) return raw as { d: string; h: string; a: string; m: string; st?: string }[];
  const fixtures = (payload.fixture_list ?? []) as { d: string; h: string; a: string }[];
  const fields = (payload.fields ?? []) as string[];
  return (raw as unknown[][]).map((values) => {
    const fixture = fixtures[values[0] as number];
    const row: Record<string, unknown> = { d: fixture.d, h: fixture.h, a: fixture.a };
    fields.forEach((name, index) => {
      if (index < values.length) row[name] = values[index];
    });
    return row as { d: string; h: string; a: string; m: string; st?: string };
  });
}

function statusClass(status: string): string {
  if (status === 'landed') return 'border-emerald-500 text-emerald-600'; if (status === 'lost') return 'border-rose-500 text-rose-600';
  return 'text-muted-foreground';
}

function ProposalCard({ ticket, statuses, shared }: { ticket: ProposedTicket; statuses: LegStatuses; shared: Record<string, number> }) {
  if (ticket.status !== 'available') {
    return (
      <li className="rounded-xl border border-dashed p-3 text-sm text-muted-foreground">
        <div className="font-semibold text-foreground">{ticket.label}</div>
        <p>Unavailable: {ticket.reason || 'no eligible priced legs'}.</p>
        <p className="text-xs">Its allocation remains unbet.</p>
      </li>
    );
  }
  const adaptive = paperSettlement(ticket, statuses);
  const flat = paperSettlement(ticket, statuses, ticket.flat_stake);
  return (
    <li className="space-y-2 rounded-xl border p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold">{ticket.label}</span>
        <span className={`rounded-full border px-2 py-0.5 text-xs ${statusClass(adaptive.status)}`}>{adaptive.status}</span>
      </div>
      <div className="tabular grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-4">
        <span>Model {pct(ticket.combined_probability)}</span>
        <span>Actual odds {ticket.combined_odds?.toFixed(2)}</span>
        <span>Flat {ticket.flat_stake.toFixed(0)}u</span>
        <span>Adaptive {ticket.adaptive.stake.toFixed(2)}u</span>
      </div>
      <ul className="space-y-1 text-xs">
        {ticket.legs.map((leg) => {
          const count = shared[proposalKey(leg)] ?? 1;
          return (
            <li key={proposalKey(leg)} className="flex flex-wrap items-baseline justify-between gap-2">
              <span>{leg.h} v {leg.a} · {leg.m}</span>
              <span className="tabular text-muted-foreground">{pct(leg.pc)} · {leg.odds.toFixed(2)} · {statuses[proposalKey(leg)] ?? 'pending'}{count > 1 ? ` · shared by ${count} proposals` : ''}</span>
            </li>
          );
        })}
      </ul>
      {ticket.adaptive.reason ? <p className="text-xs text-muted-foreground">Adaptive: {ticket.adaptive.reason}.</p> : null}
      {adaptive.status !== 'pending' ? (
        <p className="tabular text-xs">
          Flat stake {flat.stake.toFixed(2)} · return {flat.returned?.toFixed(2)} · profit {units(flat.profit)} · Adaptive return {adaptive.returned?.toFixed(2)} · profit {units(adaptive.profit)}
        </p>
      ) : <p className="text-xs text-muted-foreground">Pending until every leg is terminal.</p>}
    </li>
  );
}

function RetrospectiveCard({ ticket }: { ticket: RetrospectiveProposal }) {
  if (ticket.status !== 'available') {
    return (
      <li className="rounded-xl border border-dashed p-3 text-sm text-muted-foreground">
        <div className="font-semibold text-foreground">{ticket.label}</div>
        <p>Unavailable: {ticket.reason || 'no eligible legs'}.</p>
        <p className="text-xs">Its flat allocation remains unbet.</p>
      </li>
    );
  }
  const settlement = ticket.settlement;
  const source = settlement.source_pending ? ' · SOURCE PENDING' : '';
  return (
    <li className="space-y-2 rounded-xl border p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold">{ticket.label}</span>
        <span className={`rounded-full border px-2 py-0.5 text-xs ${statusClass(settlement.status)}`}>{settlement.status}{source}</span>
      </div>
      <div className="tabular grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-3">
        <span>Model {pct(ticket.combined_probability)}</span>
        <span>Fair odds {ticket.combined_fair_odds?.toFixed(2)}</span>
        <span>Flat {ticket.flat_stake.toFixed(0)}u</span>
      </div>
      <ul className="space-y-1 text-xs">
        {ticket.legs.map((leg, index) => (
          <li key={proposalKey(leg)} className="flex flex-wrap items-baseline justify-between gap-2">
            <span>{leg.h} v {leg.a} · {leg.m}</span>
            <span className="tabular text-muted-foreground">{pct(leg.pc)} · fair {leg.fair.toFixed(2)} · {settlement.leg_statuses[index] ?? 'pending'}</span>
          </li>
        ))}
      </ul>
      {settlement.status !== 'pending' && settlement.status !== 'unavailable' ? (
        <p className="tabular text-xs">Stake {ticket.flat_stake.toFixed(2)} · return {settlement.return?.toFixed(2)} · profit {units(settlement.profit)}</p>
      ) : null}
    </li>
  );
}

function RetrospectiveSection({ state, data }: { state: 'loading' | 'ready' | 'error'; data: RetrospectiveFile | null }) {
  return (
    <section className="space-y-3 border-t pt-4">
      <div>
        <h2 className="text-lg font-semibold">Retrospective simulations — model-fair odds</h2>
        <p className="text-sm text-muted-foreground">Retrospective simulation — generated after the round; not a frozen pre-match recommendation.</p>
        <p className="text-sm text-muted-foreground">Model-fair odds — not realised bookmaker returns.</p>
      </div>
      {state === 'loading' ? <p className="text-sm text-muted-foreground">Loading retrospective tickets…</p> : null}
      {state === 'error' ? <p className="text-sm text-muted-foreground">Retrospective tickets could not be loaded.</p> : null}
      {data ? (
        <>
          {data.rounds.map((round) => (
            <div key={round.round_date} className="space-y-2">
              <h3 className="text-base font-semibold">{round.round_date}</h3>
              <p className="text-xs text-muted-foreground">{round.disclaimer}</p>
              <p className="text-xs text-muted-foreground">{round.fair_odds_note}</p>
              <ul className="grid gap-3 lg:grid-cols-3">
                {round.proposals.map((ticket) => <RetrospectiveCard key={ticket.type} ticket={ticket} />)}
              </ul>
            </div>
          ))}
          <div className="rounded-xl border p-3 text-sm">
            <h3 className="font-semibold">Retrospective cumulative — model-fair odds</h3>
            <p className="text-muted-foreground">Retrospective simulation — generated after the round; not a frozen pre-match recommendation. Model-fair odds — not realised bookmaker returns.</p>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
              <dt>Tickets</dt><dd className="tabular text-right">{data.cumulative.tickets}</dd>
              <dt>Settled</dt><dd className="tabular text-right">{data.cumulative.settled}</dd>
              <dt>Pending</dt><dd className="tabular text-right">{data.cumulative.pending}</dd>
              <dt>Source pending</dt><dd className="tabular text-right">{data.cumulative.source_pending}</dd>
              <dt>Staked</dt><dd className="tabular text-right">{data.cumulative.staked.toFixed(2)}</dd>
              <dt>Returned</dt><dd className="tabular text-right">{data.cumulative.returned.toFixed(2)}</dd>
              <dt>Profit</dt><dd className="tabular text-right">{units(data.cumulative.profit)}</dd>
              <dt>ROI</dt><dd className="tabular text-right">{rate(data.cumulative.roi)}</dd>
            </dl>
          </div>
        </>
      ) : null}
    </section>
  );
}

function LedgerSummary({ record }: { record: ProposalRecordFile | null }) {
  if (!record) return null;
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Automatic proposal record</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border p-3 text-sm">
          <h3 className="font-semibold">Flat benchmark</h3>
          <p className="text-muted-foreground">100 units allocated per round: 50 / 30 / 20.</p>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <dt>Staked</dt><dd className="tabular text-right">{record.flat.staked.toFixed(2)}</dd>
            <dt>Returned</dt><dd className="tabular text-right">{record.flat.returned.toFixed(2)}</dd>
            <dt>Net</dt><dd className="tabular text-right">{units(record.flat.net)}</dd>
            <dt>ROI</dt><dd className="tabular text-right">{rate(record.flat.roi)}</dd>
            <dt>95% return CI</dt><dd className="tabular text-right text-xs">{record.flat.return_ci[0] === null ? 'needs 30 rounds' : `${rate(record.flat.return_ci[0])} to ${rate(record.flat.return_ci[1])}`}</dd>
          </dl>
        </div>
        <div className="rounded-xl border p-3 text-sm">
          <h3 className="font-semibold">Adaptive risk-managed simulation</h3>
          <p className="text-muted-foreground">Quarter Kelly, 1% ticket cap, 2% round cap, drawdown controls.</p>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <dt>Bankroll</dt><dd className="tabular text-right">{record.adaptive.bankroll.toFixed(2)}</dd>
            <dt>Net</dt><dd className="tabular text-right">{units(record.adaptive.net)}</dd>
            <dt>ROI</dt><dd className="tabular text-right">{rate(record.adaptive.roi)}</dd>
            <dt>Current drawdown</dt><dd className="tabular text-right">{rate(record.adaptive.current_drawdown)}</dd>
            <dt>Maximum drawdown</dt><dd className="tabular text-right">{rate(record.adaptive.maximum_drawdown)}</dd>
          </dl>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Rounds {record.counts.rounds} · tickets {record.counts.tickets} · pending {record.counts.pending} · void {record.counts.void} · unavailable {record.counts.unavailable} · unpriced {record.counts.unpriced}.
        Paper convention: a lost leg loses the stake; void legs settle at 1.00. This is not a profit guarantee.
      </p>
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead><tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground"><th className="px-3 py-2 text-left">Type</th><th className="px-3 py-2 text-right">Tickets</th><th className="px-3 py-2 text-right">Settled</th><th className="px-3 py-2 text-right">Flat net</th><th className="px-3 py-2 text-right">Adaptive net</th></tr></thead>
          <tbody>
            {Object.entries(record.types).map(([type, row]) => (
              <tr key={type} className="border-t">
                <td className="px-3 py-1.5">{type}</td>
                <td className="tabular px-3 py-1.5 text-right">{row.tickets ?? 0}</td>
                <td className="tabular px-3 py-1.5 text-right">{row.settled ?? 0}</td>
                <td className="tabular px-3 py-1.5 text-right">{units((row.flat_returned ?? 0) - (row.flat_staked ?? 0))}</td>
                <td className="tabular px-3 py-1.5 text-right">{units((row.adaptive_returned ?? 0) - (row.adaptive_staked ?? 0))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function TicketsPage() {
  const [tickets, setTickets] = useState<SavedTicket[]>([]);
  const [statuses, setStatuses] = useState<Record<string, LegStatuses>>({});
  const [proposalsState, setProposalsState] = useState<'loading' | 'ready' | 'unpriced' | 'error'>('loading');
  const [rounds, setRounds] = useState<PrivateProposalsFile['rounds']>([]);
  const [record, setRecord] = useState<ProposalRecordFile | null>(null);
  const [recordState, setRecordState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [retrospective, setRetrospective] = useState<RetrospectiveFile | null>(null);
  const [retrospectiveState, setRetrospectiveState] = useState<'loading' | 'ready' | 'error'>('loading');

  useEffect(() => { setTickets(loadTickets()); }, []);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/proposed-tickets-private.json')
      .then(async (response) => {
        if (response.status === 404) { if (!cancelled) setProposalsState('unpriced'); return; }
        if (!response.ok) throw new Error('proposals');
        const payload = (await response.json()) as PrivateProposalsFile;
        if (!cancelled) { setRounds(payload.rounds ?? []); setProposalsState('ready'); }
      })
      .catch(() => { if (!cancelled) setProposalsState('error'); });
    fetch('/data/proposed-tickets-record.json')
      .then((response) => {
        if (!response.ok) throw new Error('record');
        return response.json() as Promise<ProposalRecordFile>;
      })
      .then((payload) => { if (!cancelled) { setRecord(payload); setRecordState('ready'); } })
      .catch(() => { if (!cancelled) setRecordState('error'); });
    fetch('/data/retrospective-tickets.json')
      .then((response) => {
        if (!response.ok) throw new Error('retrospective');
        return response.json() as Promise<RetrospectiveFile>;
      })
      .then((payload) => { if (!cancelled) { setRetrospective(payload); setRetrospectiveState('ready'); } })
      .catch(() => { if (!cancelled) setRetrospectiveState('error'); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const dates = [...new Set([
      ...tickets.map((ticket) => ticket.date),
      ...rounds.map((round) => round.round_date),
    ])];
    let cancelled = false;
    Promise.all(dates.map(async (date) => {
      for (const url of [`/data/rounds/${date}.full.json`, `/data/rounds/${date}.json`]) {
        const response = await fetch(url);
        if (!response.ok) continue;
        const map: LegStatuses = {};
        for (const row of decodeRows(await response.json() as Record<string, unknown>)) {
          map[`${row.d}|${row.h}|${row.a}|${row.m}`] = row.st ?? 'pending';
        }
        return [date, map] as const;
      }
      return [date, {}] as const;
    })).then((entries) => { if (!cancelled) setStatuses(Object.fromEntries(entries)); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [tickets, rounds]);

  const automatic = useMemo(() => [...rounds].sort((a, b) => b.round_date.localeCompare(a.round_date)), [rounds]);
  const forwardAvailable = proposalsState === 'ready' && automatic.length > 0;

  function remove(id: string) { setTickets(removeTicket(id)); }

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">My tickets</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Automatic proposals are frozen from the first usable private Mozzart snapshot. Flat and adaptive allocations are paper simulations, not guarantees.
        </p>
      </header>

      {!forwardAvailable ? <RetrospectiveSection state={retrospectiveState} data={retrospective} /> : null}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Forward proposals — actual frozen prices</h2>
      {proposalsState === 'loading' ? <p className="text-sm text-muted-foreground">Loading automatic proposals…</p> : null}
      {proposalsState === 'error' ? <p className="text-sm text-muted-foreground">Automatic proposals could not be loaded.</p> : null}
      {proposalsState === 'unpriced' ? (
        <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
          Automatic proposals require private Mozzart prices. This build is unpriced; no actual prices are shown.
        </p>
      ) : null}
      {proposalsState === 'ready' && automatic.length === 0 ? (
        <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">No automatic proposals have been frozen yet.</p>
      ) : null}
      {automatic.map((round) => {
        const shared = sharedCounts(round.proposals);
        return (
          <section key={round.round_date} className="space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-lg font-semibold">{round.round_date}</h2>
              <span className="text-xs text-muted-foreground">Frozen snapshot {round.snapshot_identity.fetched_at ?? '–'}</span>
            </div>
            <ul className="grid gap-3 lg:grid-cols-3">
              {round.proposals.map((ticket) => (
                <ProposalCard key={ticket.type} ticket={ticket} statuses={statuses[round.round_date] ?? {}} shared={shared} />
              ))}
            </ul>
          </section>
        );
      })}
      {recordState === 'error' ? <p className="text-sm text-muted-foreground">Automatic proposal record could not be loaded.</p> : null}
      </section>

      <LedgerSummary record={record} />

      {forwardAvailable ? <RetrospectiveSection state={retrospectiveState} data={retrospective} /> : null}

      <section className="space-y-3 border-t pt-4">
        <h2 className="text-lg font-semibold">My saved tickets</h2>
        <p className="text-sm text-muted-foreground">Browser-only tickets saved from the picker. Separate from the automatic proposals above.</p>
        {tickets.length === 0 ? (
          <p className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
            No saved tickets yet. Open a round and add legs from the picker.
          </p>
        ) : (
          <ul className="space-y-3">
            {tickets.map((ticket) => {
              const legs = ticket.legs.map((leg) => ({ ...leg, st: statuses[ticket.date]?.[legKey(leg)] ?? leg.st ?? 'pending' }));
              const overall = overallStatus(legs);
              const mozzart = combinedMozzart(legs);
              return (
                <li key={ticket.id} className="rounded-xl border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-medium">
                      <Link href={`/?round=${ticket.date}`} className="underline underline-offset-2">{ticket.date}</Link>{' '}· {ticket.legs.length} legs · {pct(combinedProbability(ticket.legs))} · fair {combinedFair(ticket.legs).toFixed(2)}{mozzart !== null ? ` · Mozzart ${mozzart.toFixed(2)}` : ''} · stake {ticket.stake}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full border px-2 py-0.5 text-xs ${statusClass(overall)}`}>{overall}</span>
                      <button type="button" onClick={() => remove(ticket.id)} className="text-xs text-muted-foreground">Delete</button>
                    </div>
                  </div>
                  <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
                    {legs.map((leg) => <li key={legKey(leg)}>{leg.h} v {leg.a} · {leg.label} · {pct(leg.pc)} · {leg.fair.toFixed(2)}{leg.odds !== null ? ` · Mozzart ${leg.odds.toFixed(2)}` : ''} · {leg.st}</li>)}
                  </ul>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
