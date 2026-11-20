'use client';

import { useEffect, useState } from 'react';
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

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
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

export default function TicketsPage() {
  const [tickets, setTickets] = useState<SavedTicket[]>([]);
  const [statuses, setStatuses] = useState<Record<string, Record<string, string>>>({});

  useEffect(() => {
    setTickets(loadTickets());
  }, []);

  useEffect(() => {
    const dates = [...new Set(tickets.map((ticket) => ticket.date))];
    let cancelled = false;
    Promise.all(
      dates.map(async (date) => {
        for (const url of [`/data/rounds/${date}.full.json`, `/data/rounds/${date}.json`]) {
          const response = await fetch(url);
          if (!response.ok) continue;
          const payload = (await response.json()) as Record<string, unknown>;
          const map: Record<string, string> = {};
          for (const row of decodeRows(payload)) {
            map[`${row.d}|${row.h}|${row.a}|${row.m}`] = row.st ?? 'pending';
          }
          return [date, map] as const;
        }
        return [date, {}] as const;
      }),
    )
      .then((entries) => {
        if (!cancelled) setStatuses(Object.fromEntries(entries));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [tickets]);

  function remove(id: string) {
    setTickets(removeTicket(id));
  }

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">My tickets</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Saved in this browser only. Nothing here is sent to a server or committed to the repo.
        </p>
      </header>

      {tickets.length === 0 ? (
        <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          No saved tickets yet. Open a round and add legs from the picker.
        </p>
      ) : (
        <ul className="space-y-3">
          {tickets.map((ticket) => {
            const legs = ticket.legs.map((leg) => ({
              ...leg,
              st: statuses[ticket.date]?.[legKey(leg)] ?? leg.st ?? 'pending',
            }));
            const overall = overallStatus(legs);
            const mozzart = combinedMozzart(legs);
            return (
              <li key={ticket.id} className="rounded-xl border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-sm font-medium">
                    <Link href={`/?round=${ticket.date}`} className="underline underline-offset-2">{ticket.date}</Link>{' '}
                    · {ticket.legs.length} legs · {pct(combinedProbability(ticket.legs))} · fair {combinedFair(ticket.legs).toFixed(2)}
                    {mozzart !== null ? ` · Mozzart ${mozzart.toFixed(2)}` : ' · Mozzart incomplete'}
                    {ticket.bonus ? ` · bonus ${ticket.bonus}%` : ''} · stake {ticket.stake}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full border px-2 py-0.5 text-xs ${overall === 'landed' ? 'border-emerald-500 text-emerald-600' : overall === 'lost' ? 'border-rose-500 text-rose-600' : 'text-muted-foreground'}`}>
                      {overall}
                    </span>
                    <button type="button" onClick={() => remove(ticket.id)} className="text-xs text-muted-foreground">Delete</button>
                  </div>
                </div>
                <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
                  {legs.map((leg) => (
                    <li key={legKey(leg)} className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="truncate">{leg.h} v {leg.a} · {leg.label} · {pct(leg.pc)} · {leg.fair.toFixed(2)}{leg.odds !== null ? ` · Mozzart ${leg.odds.toFixed(2)}` : ''}</span>
                      <span>{leg.st}</span>
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
