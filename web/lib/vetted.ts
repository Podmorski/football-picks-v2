// Shared vetted-list selection. The Best bets page and the rounds tally both
// use this, so a tally always describes the same rows, rule and default
// filters as the page it links to.

import type { PricedRow } from './prices';
import type { RankRow } from './types';
import {
  ANY_RULE,
  evaluateCandidate,
  evaluateTypeCandidate,
  liftOf,
  minPlay,
  teamEmpirical,
  type VettingCandidate,
  type VettingCheck,
} from './vetting';

// Default minimum fair odds on Best bets (`?min=`).
export const DEFAULT_MIN_FAIR = 1.70;

// Groups kept in the data files but no longer shown in the picker UI.
export const HIDDEN_GROUP = 'Correct score';

export function isHiddenMarketId(id: string): boolean {
  return id.startsWith('CORRECT_SCORE:');
}

export type RuleKind = 'any' | 'type';

export type Evaluated = {
  row: RankRow;
  price?: PricedRow;
  candidate: VettingCandidate;
  lift: number;
  minPlay: number;
  edge: number;
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
  rule: RuleKind = 'any',
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
      countsProbability: teamEmpirical({ probability, modelProbability: row.p, leagueRate: row.lr, leagueN: row.ln, homeRate: row.hr, homeN: row.hn, awayRate: row.ar, awayN: row.an, fairOdds }),
      mozzartOdds: price?.odds ?? null,
    };
    const result = rule === 'type'
      ? evaluateTypeCandidate(candidate)
      : evaluateCandidate(candidate, ANY_RULE);
    return {
      row,
      price,
      candidate,
      lift: liftOf(candidate),
      minPlay: minPlay(probability),
      edge: price ? price.odds * probability - 1 : -Infinity,
      ...result,
    };
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
    if (isHiddenMarketId(item.row.m)) continue;
    if (!item.passed) continue;
    if (item.candidate.fairOdds < minFair) continue;
    if (mozzartOnly && !(item.price && item.price.odds >= item.candidate.fairOdds)) continue;
    const key = `${item.row.h}|${item.row.a}`;
    const current = best.get(key);
    if (!current || item.candidate.probability > current.candidate.probability) best.set(key, item);
  }
  return [...best.values()].sort((a, b) => b.candidate.probability - a.candidate.probability);
}

// TYPE_RULE selection. For a group keep one passing bet per match (highest
// probability); for a single market every passing fixture. Highest probability
// first; lift is shown only.
export function selectType(
  evaluated: Evaluated[],
  options: { perMatch?: boolean; market?: string; minFair?: number } = {},
): Evaluated[] {
  const perMatch = options.perMatch ?? false;
  const minFair = options.minFair ?? DEFAULT_MIN_FAIR;
  const best = new Map<string, Evaluated>();
  for (const item of evaluated) {
    if (isHiddenMarketId(item.row.m)) continue;
    if (!item.passed) continue;
    if (item.candidate.fairOdds < minFair) continue;
    if (options.market !== undefined && item.row.m !== options.market) continue;
    const key = perMatch
      ? `${item.row.d}|${item.row.h}|${item.row.a}`
      : `${item.row.d}|${item.row.h}|${item.row.a}|${item.row.m}`;
    const current = best.get(key);
    if (!current || item.candidate.probability > current.candidate.probability) best.set(key, item);
  }
  return [...best.values()].sort((a, b) => b.candidate.probability - a.candidate.probability);
}

export function isValue(item: Evaluated): boolean {
  return item.price != null && item.price.odds >= item.minPlay;
}

// Value rows: Mozzart >= min play, team records + agreement + fair <= 6, one per
// match by highest edge, strongest edge first. Lift is not required.
const VALUE_CHECKS = ['t3', 't4', 't6'] as const;

export function selectValue(evaluated: Evaluated[]): Evaluated[] {
  const best = new Map<string, Evaluated>();
  for (const item of evaluated) {
    if (isHiddenMarketId(item.row.m)) continue;
    if (!isValue(item)) continue;
    if (!VALUE_CHECKS.every((id) => item.checks.find((check) => check.id === id)?.passed)) continue;
    const key = `${item.row.d}|${item.row.h}|${item.row.a}`;
    const current = best.get(key);
    if (!current || item.edge > current.edge) best.set(key, item);
  }
  return [...best.values()].sort((a, b) => b.edge - a.edge);
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
