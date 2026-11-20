// Target-payout ticket optimiser. Exact enumeration for pools <= 20 legs;
// exact DP over 0.001-quantised log(fair) above that, with the true fair checked.
import type { TicketLeg } from './ticket';

export type OptimisedTicket = { legs: TicketLeg[]; probability: number; fair: number };

const ENUMERATE_LIMIT = 20;
const STEP = 0.001;

function combinedFair(legs: TicketLeg[]): number {
  return legs.reduce((total, leg) => total * leg.fair, 1);
}

function dedupe(legs: TicketLeg[], minFair: number): TicketLeg[] {
  const byMatch = new Map<string, TicketLeg>();
  for (const leg of legs) {
    if (leg.fair < minFair) continue;
    const key = leg.h + '|' + leg.a;
    const current = byMatch.get(key);
    if (!current || leg.pc > current.pc) byMatch.set(key, leg);
  }
  return [...byMatch.values()];
}

function* combinations(items: TicketLeg[], k: number): Generator<TicketLeg[]> {
  if (k === 0) {
    yield [];
    return;
  }
  for (let i = 0; i <= items.length - k; i += 1) {
    for (const rest of combinations(items.slice(i + 1), k - 1)) {
      yield [items[i], ...rest];
    }
  }
}

function enumerate(pool: TicketLeg[], target: number, maxLegs: number, alternatives: number): OptimisedTicket[] {
  const found: { fair: number; legs: TicketLeg[] }[] = [];
  for (let size = 1; size <= maxLegs; size += 1) {
    for (const combo of combinations(pool, size)) {
      const fair = combinedFair(combo);
      if (fair >= target) found.push({ fair, legs: combo });
    }
  }
  found.sort((a, b) => a.fair - b.fair);
  const out: OptimisedTicket[] = [];
  const seen = new Set<string>();
  for (const entry of found) {
    const key = entry.legs.map((leg) => leg.h + '|' + leg.a + '|' + leg.m).sort().join(';');
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ legs: entry.legs, probability: 1 / entry.fair, fair: entry.fair });
    if (out.length >= alternatives) break;
  }
  return out;
}

type Parent = [number, number] | null;

function reconstruct(reachable: Map<number, Parent>[], size: number, weight: number, pool: TicketLeg[]): TicketLeg[] | null {
  const combo: TicketLeg[] = [];
  let k = size;
  let w = weight;
  while (k > 0) {
    const previous = reachable[k].get(w);
    if (!previous) return null;
    const [index, prevWeight] = previous;
    combo.push(pool[index]);
    w = prevWeight;
    k -= 1;
  }
  return combo;
}

function dynamic(pool: TicketLeg[], target: number, maxLegs: number, alternatives: number): OptimisedTicket[] {
  const weights = pool.map((leg) => Math.max(1, Math.ceil(Math.log(Math.max(leg.fair, 1)) / STEP)));
  const maxWeight = maxLegs * Math.max(...weights, 1);
  const reachable: Map<number, Parent>[] = Array.from({ length: maxLegs + 1 }, () => new Map<number, Parent>());
  reachable[0].set(0, null);
  for (let index = 0; index < weights.length; index += 1) {
    const weight = weights[index];
    for (let size = maxLegs; size >= 1; size -= 1) {
      const previous = reachable[size - 1];
      const current = reachable[size];
      for (const prevWeight of Array.from(previous.keys())) {
        const next = prevWeight + weight;
        if (next > maxWeight) continue;
        if (!current.has(next)) current.set(next, [index, prevWeight]);
      }
    }
  }
  const targetWeight = Math.ceil(Math.log(target) / STEP);
  const candidates: { fair: number; legs: TicketLeg[] }[] = [];
  for (let size = 1; size <= maxLegs; size += 1) {
    const weightsForSize = [...reachable[size].keys()].filter((value) => value >= targetWeight).sort((a, b) => a - b);
    for (const weight of weightsForSize) {
      const combo = reconstruct(reachable, size, weight, pool);
      if (!combo) continue;
      const fair = combinedFair(combo);
      if (fair >= target) candidates.push({ fair, legs: combo });
    }
  }
  candidates.sort((a, b) => a.fair - b.fair);
  const out: OptimisedTicket[] = [];
  const seen = new Set<string>();
  for (const entry of candidates) {
    const key = entry.legs.map((leg) => leg.h + '|' + leg.a + '|' + leg.m).sort().join(';');
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ legs: entry.legs, probability: 1 / entry.fair, fair: entry.fair });
    if (out.length >= alternatives) break;
  }
  return out;
}

export function optimiseTickets(
  legs: TicketLeg[],
  target: number,
  maxLegs: number,
  alternatives = 3,
  minFair = 1.5,
): OptimisedTicket[] {
  const pool = dedupe(legs, minFair);
  if (pool.length === 0) return [];
  if (pool.length <= ENUMERATE_LIMIT) return enumerate(pool, target, maxLegs, alternatives);
  return dynamic(pool, target, maxLegs, alternatives);
}
