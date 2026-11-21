// Ticket maths. Everything here is pure; persistence is browser-only.

export type TicketLeg = {
  d: string;
  h: string;
  a: string;
  m: string;
  label: string;
  mozzart: string;
  pc: number;
  fair: number;
  minPlay: number;
  odds: number | null;
  fetchedAt?: string;
  kickoff?: string | null;
  st?: string;
  ht?: string | null;
  ft?: string | null;
};

export type SavedTicket = {
  id: string;
  date: string;
  legs: TicketLeg[];
  bonus: number;
  stake: number;
  savedAt: string;
};

export const TICKET_KEY = 'fpv2-tickets';

export function legKey(leg: { d: string; h: string; a: string; m: string }): string {
  return `${leg.d}|${leg.h}|${leg.a}|${leg.m}`;
}

export function combinedProbability(legs: TicketLeg[]): number {
  return legs.reduce((total, leg) => total * leg.pc, 1);
}

export function combinedFair(legs: TicketLeg[]): number {
  return legs.reduce((total, leg) => total * leg.fair, 1);
}

export function combinedMinPlay(legs: TicketLeg[]): number | null {
  if (legs.length === 0) return null;
  return legs.reduce((total, leg) => total * (leg.minPlay || 1), 1);
}

export function combinedMozzart(legs: TicketLeg[]): number | null {
  if (legs.length === 0 || legs.some((leg) => leg.odds === null || leg.odds === undefined)) return null;
  return legs.reduce((total, leg) => total * (leg.odds as number), 1);
}

export function ticketVsFair(legs: TicketLeg[], bonus = 0): number | null {
  const mozzart = combinedMozzart(legs);
  const fair = combinedFair(legs);
  if (mozzart === null || fair <= 0) return null;
  return (mozzart * (1 + bonus / 100)) / fair - 1;
}

export function payout(stake: number, legs: TicketLeg[], bonus = 0): number | null {
  const mozzart = combinedMozzart(legs);
  if (mozzart === null) return null;
  return stake * mozzart * (1 + bonus / 100);
}

export function sameMatchWarning(legs: TicketLeg[]): boolean {
  const seen = new Set<string>();
  for (const leg of legs) {
    const key = `${leg.h}|${leg.a}`;
    if (seen.has(key)) return true;
    seen.add(key);
  }
  return false;
}

export function loadTickets(): SavedTicket[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(TICKET_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as SavedTicket[]) : [];
  } catch {
    return [];
  }
}

export function saveTickets(tickets: SavedTicket[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(TICKET_KEY, JSON.stringify(tickets));
  } catch {
    // ignore quota/private-mode failures
  }
}

export function addTicket(ticket: SavedTicket): SavedTicket[] {
  const tickets = loadTickets();
  const next = [ticket, ...tickets].slice(0, 100);
  saveTickets(next);
  return next;
}

export function removeTicket(id: string): SavedTicket[] {
  const next = loadTickets().filter((ticket) => ticket.id !== id);
  saveTickets(next);
  return next;
}

export function overallStatus(legs: { st?: string }[]): 'landed' | 'lost' | 'pending' {
  if (legs.some((leg) => leg.st === 'lost')) return 'lost';
  if (legs.length > 0 && legs.every((leg) => leg.st === 'landed' || leg.st === 'void')) return 'landed';
  return 'pending';
}
