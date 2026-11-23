import type { ProposedLeg, ProposedTicket } from './types';

export type LegStatuses = Record<string, string>;

export type PaperResult = {
  status: 'pending' | 'landed' | 'lost' | 'void';
  stake: number;
  returned: number | null;
  profit: number | null;
};

export function proposalKey(leg: Pick<ProposedLeg, 'd' | 'h' | 'a' | 'm'>): string {
  return `${leg.d}|${leg.h}|${leg.a}|${leg.m}`;
}

export function paperSettlement(ticket: ProposedTicket, statuses: LegStatuses, stakeOverride?: number): PaperResult {
  const stake = stakeOverride ?? ticket.adaptive.stake;
  const states = ticket.legs.map((leg) => statuses[proposalKey(leg)] ?? 'pending');
  if (states.some((state) => state === 'lost')) return { status: 'lost', stake, returned: 0, profit: -stake };
  if (states.length === 0 || states.some((state) => state !== 'landed' && state !== 'void')) {
    return { status: 'pending', stake, returned: null, profit: null };
  }
  if (states.every((state) => state === 'void')) return { status: 'void', stake, returned: stake, profit: 0 };
  const odds = ticket.legs.reduce((total, leg, index) => states[index] === 'landed' ? total * leg.odds : total, 1);
  const returned = stake * odds;
  return { status: 'landed', stake, returned, profit: returned - stake };
}

export function sharedCounts(tickets: ProposedTicket[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const ticket of tickets) {
    for (const leg of ticket.legs) counts[proposalKey(leg)] = (counts[proposalKey(leg)] ?? 0) + 1;
  }
  return counts;
}
