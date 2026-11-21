// Shared vetted-list selection. The Best bets page and the rounds tally both
// use this, so a tally always describes the same rows, rule and default
// filters as the page it links to.

import type { PricedRow } from './prices';
import type { RankRow } from './types';
import { DEFAULT_RULE, evaluateCandidate, type VettingCandidate, type VettingCheck } from './vetting';

// Default minimum fair odds on Best bets (`?min=`).
export const DEFAULT_MIN_FAIR = 1.70;

export type Evaluated = {
  row: RankRow;
  price?: PricedRow;
  candidate: VettingCandidate;
  passed: boolean;
  checks: VettingCheck[];
};

export function pcOf(row: RankRow): number {
  return row.pc ?? row.p;
}

export function fairOf(row: RankRow): number {
  return 1 / Math.max(pcOf(row), 0.0001);
}

export function evaluateRows(
  rows: RankRow[],
  priceFor?: (row: RankRow) => PricedRow | undefined,
): Evaluated[] {
  return rows.map((row) => {
    const probability = pcOf(row);
    const fairOdds = fairOf(row);
    const price = priceFor?.(row);
    const candidate: VettingCandidate = {
      probability,
      modelProbability: row.p,
      leagueRate: row.lr,
      leagueN: row.ln,
      homeRate: row.hr,
      homeN: row.hn,
      awayRate: row.ar,
      awayN: row.an,
      fairOdds,
      countsProbability: row.lr,
      mozzartOdds: price?.odds ?? null,
    };
    const result = evaluateCandidate(candidate, DEFAULT_RULE);
    return { row, price, candidate, ...result };
  });
}

// Default rule + default filters: one passing pick per match, highest
// probability first. `minFair` defaults to the Best bets page default.
export function selectPassing(
  evaluated: Evaluated[],
  options: { minFair?: number; mozzartOnly?: boolean } = {},
): Evaluated[] {
  const minFair = options.minFair ?? DEFAULT_MIN_FAIR;
  const mozzartOnly = options.mozzartOnly ?? false;
  const best = new Map<string, Evaluated>();
  for (const item of evaluated) {
    if (!item.passed) continue;
    if (item.candidate.fairOdds < minFair) continue;
    if (mozzartOnly && !(item.price && item.price.odds >= item.candidate.fairOdds)) continue;
    const key = `${item.row.h}|${item.row.a}`;
    const current = best.get(key);
    if (!current || item.candidate.probability > current.candidate.probability) best.set(key, item);
  }
  return [...best.values()].sort((a, b) => b.candidate.probability - a.candidate.probability);
}

export type RoundTally = {
  picks: Evaluated[];
  settled: Evaluated[];
  landed: number;
  expected: number;
};

// Tally under the default filters. Only landed/lost rows count as settled;
// pending and void never land or lose.
export function roundTally(rows: RankRow[]): RoundTally {
  const picks = selectPassing(evaluateRows(rows), { minFair: DEFAULT_MIN_FAIR });
  const settled = picks.filter((item) => item.row.st === 'landed' || item.row.st === 'lost');
  const landed = settled.filter((item) => item.row.st === 'landed').length;
  const expected = settled.reduce((total, item) => total + item.candidate.probability, 0);
  return { picks, settled, landed, expected };
}
