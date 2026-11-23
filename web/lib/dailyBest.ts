// Daily-best selection for the Best bets page.
//
// Pure and dependency-free (type-only imports) so the contract can be run
// directly with Node's TypeScript type-stripping runner in tests. Every odds
// value here is an ACTUAL offered decimal price, never a model fair price.

import type { RankRow } from './types';

export const DAILY_LIMIT = 12;
export const DAILY_MIN_ODDS = 1.20;
export const DEFAULT_BAND = '1.70-2.30';

export type BandSpec = {
  token: string;
  min: number;
  max: number | null;
  // All 1.20+: highest pc per fixture, ranked by pc with no band sections.
  all: boolean;
};

export const BAND_OPTIONS: { token: string; label: string }[] = [
  { token: '1.70-2.30', label: '1.70–2.30 — default' },
  { token: '1.20-1.69', label: '1.20–1.69' },
  { token: '2.31-4.00', label: '2.31–4.00' },
  { token: '4.01+', label: '4.01+' },
  { token: 'all', label: 'All 1.20+' },
];

export type Refinement = 'all' | 'pc50' | 'pc58' | 'fair150' | 'fair200';

export const REFINEMENTS: { token: Refinement; label: string }[] = [
  { token: 'all', label: 'No refinement (all)' },
  { token: 'pc50', label: 'Model probability ≥ 50%' },
  { token: 'pc58', label: 'Model probability ≥ 58%' },
  { token: 'fair150', label: 'Fair odds ≥ 1.50' },
  { token: 'fair200', label: 'Fair odds ≥ 2.00' },
];

export type OddsCandidate = {
  d: string;
  h: string;
  a: string;
  m: string;
  pc: number;
  odds: number | null;
  st?: string;
};

export type DailyCandidate = OddsCandidate & { odds: number };

const NUMBER = /^\d+(?:\.\d+)?$/;

function formatNumber(value: number): string {
  return value.toFixed(2);
}

export function expectedReturnOf(probability: number, odds: number): number {
  return probability * odds - 1;
}

export function fairOddsOf(probability: number): number {
  return 1 / Math.max(probability, 0.0001);
}

function identity(candidate: OddsCandidate): string {
  return `${candidate.d}|${candidate.h}|${candidate.a}|${candidate.m}`;
}

function probabilityOrder(a: OddsCandidate, b: OddsCandidate): number {
  if (b.pc !== a.pc) return b.pc - a.pc;
  const oddsA = a.odds ?? fairOddsOf(a.pc);
  const oddsB = b.odds ?? fairOddsOf(b.pc);
  const evA = expectedReturnOf(a.pc, oddsA);
  const evB = expectedReturnOf(b.pc, oddsB);
  if (evB !== evA) return evB - evA;
  return identity(a).localeCompare(identity(b));
}

// Parse a band token: `1.70-2.30`, `4.01+`, `all` (alias `any`), or any other
// numeric range/floor. Invalid or absent values fall back to the default band.
// The contract never looks below the 1.20 daily floor.
export function parseBand(raw: string | null | undefined): BandSpec {
  const token = (raw ?? '').trim().toLowerCase();
  if (token === 'all' || token === 'any') {
    return { token: 'all', min: DAILY_MIN_ODDS, max: null, all: true };
  }
  const plus = token.match(/^(\d+(?:\.\d+)?)\+$/);
  if (plus) {
    const min = Math.max(DAILY_MIN_ODDS, Number(plus[1]));
    return { token: `${formatNumber(min)}+`, min, max: null, all: false };
  }
  const range = token.match(/^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$/);
  if (range) {
    const min = Math.max(DAILY_MIN_ODDS, Number(range[1]));
    const max = Number(range[2]);
    if (Number.isFinite(max) && max >= min) {
      return { token: `${formatNumber(min)}-${formatNumber(max)}`, min, max, all: false };
    }
  }
  if (token !== DEFAULT_BAND) return parseBand(DEFAULT_BAND);
  return { token: DEFAULT_BAND, min: 1.7, max: 2.3, all: false };
}

// Legacy Best-bets links carried `?min=` as a minimum FAIR odds. The Daily-best
// contract reads the same number as a minimum ACTUAL odds floor: `?min=1.70`
// becomes `band=1.70+`, and `?min=any` (or 1.20 and below) becomes `band=all`.
export function legacyMinToBand(min: string | null | undefined): string | null {
  if (!min) return null;
  const value = min.trim().toLowerCase();
  if (value === 'any') return 'all';
  if (!NUMBER.test(value)) return null;
  const odds = Number(value);
  if (!Number.isFinite(odds) || odds <= 0) return null;
  if (odds <= DAILY_MIN_ODDS) return 'all';
  return `${formatNumber(odds)}+`;
}

export function inBand(odds: number, band: BandSpec): boolean {
  if (!(odds >= DAILY_MIN_ODDS)) return false;
  if (band.all) return true;
  if (odds < band.min) return false;
  if (band.max !== null && odds > band.max) return false;
  return true;
}

// Absolute log-odds distance to the nearest preferred-band boundary.
export function bandDistance(odds: number, band: BandSpec): number {
  if (inBand(odds, band)) return 0;
  const value = Math.log(Math.max(odds, 1e-9));
  let distance = Math.abs(value - Math.log(band.min));
  if (band.max !== null) distance = Math.min(distance, Math.abs(value - Math.log(band.max)));
  return distance;
}

function fixturesOf<T extends OddsCandidate>(candidates: T[]): Map<string, T[]> {
  const map = new Map<string, T[]>();
  for (const candidate of candidates) {
    const key = `${candidate.d}|${candidate.h}|${candidate.a}`;
    const list = map.get(key);
    if (list) list.push(candidate);
    else map.set(key, [candidate]);
  }
  return map;
}

export type DailySelection<T extends OddsCandidate = DailyCandidate> = {
  // One row per unique fixture, ranked; not capped here.
  rows: (T & { odds: number })[];
  inside: (T & { odds: number })[];
  outside: (T & { odds: number })[];
  // Fixtures with at least one in-band candidate in the eligible pool.
  inBandFixtures: number;
  // Unique fixtures with at least one price at or above the 1.20 floor.
  eligibleFixtures: number;
  // Priced candidates below the floor or with pc outside (0, 1), for display.
  rejected: number;
};

export function dailyPool<T extends OddsCandidate>(candidates: T[]): (T & { odds: number })[] {
  const pool: (T & { odds: number })[] = [];
  for (const candidate of candidates) {
    if (candidate.odds === null || candidate.odds === undefined) continue;
    if (!(candidate.odds >= DAILY_MIN_ODDS)) continue;
    if (!(candidate.pc > 0 && candidate.pc < 1)) continue;
    pool.push({ ...candidate, odds: candidate.odds });
  }
  return pool;
}

// Per fixture: highest pc inside the band; otherwise the candidate nearest the
// band. Ties prefer higher model expected return, then deterministic identity.
export function chooseOnePerFixture<T extends OddsCandidate>(
  candidates: (T & { odds: number })[],
  band: BandSpec,
): (T & { odds: number })[] {
  const chosen: (T & { odds: number })[] = [];
  for (const list of fixturesOf(candidates).values()) {
    if (band.all) {
      chosen.push([...list].sort(probabilityOrder)[0]);
      continue;
    }
    const inside = list.filter((candidate) => inBand(candidate.odds, band)).sort(probabilityOrder);
    if (inside.length > 0) {
      chosen.push(inside[0]);
      continue;
    }
    const outside = [...list].sort((a, b) => {
      const distance = bandDistance(a.odds, band) - bandDistance(b.odds, band);
      return distance !== 0 ? distance : probabilityOrder(a, b);
    });
    chosen.push(outside[0]);
  }
  return chosen;
}

// Global rank: in-band rows first by pc then model expected return; outside-band
// rows by nearest band distance, then pc and expected return; identity last.
export function selectDaily<T extends OddsCandidate>(candidates: T[], band: BandSpec): DailySelection<T> {
  const pool = dailyPool(candidates);
  const fixtures = fixturesOf(pool);
  const inBandFixtures = [...fixtures.values()]
    .filter((list) => list.some((candidate) => inBand(candidate.odds, band)))
    .length;
  const chosen = chooseOnePerFixture(pool, band);
  const inside = chosen.filter((candidate) => inBand(candidate.odds, band)).sort(probabilityOrder);
  const outside = chosen
    .filter((candidate) => !inBand(candidate.odds, band))
    .sort((a, b) => {
      const distance = bandDistance(a.odds, band) - bandDistance(b.odds, band);
      return distance !== 0 ? distance : probabilityOrder(a, b);
    });
  return {
    rows: band.all ? [...chosen].sort(probabilityOrder) : [...inside, ...outside],
    inside,
    outside,
    inBandFixtures,
    eligibleFixtures: fixtures.size,
    rejected: candidates.filter((candidate) => candidate.odds !== null).length - pool.length,
  };
}

// Display cap: 12 unique fixtures by default. Show all is only meaningful for
// a single selected league; the caller decides when to pass showAll.
export function visibleDailyRows<T extends OddsCandidate>(
  selection: DailySelection<T>,
  showAll: boolean,
  limit: number = DAILY_LIMIT,
): (T & { odds: number })[] {
  return showAll ? selection.rows : selection.rows.slice(0, limit);
}

// Group view: every fixture with a candidate, summarised by its highest pc.
// No odds floor, preferred band, probability gate or price requirement.
export function selectGroupRows<T extends OddsCandidate>(candidates: T[]): T[] {
  return [...fixturesOf(candidates).values()]
    .map((list) => [...list].sort(probabilityOrder)[0])
    .sort(probabilityOrder);
}

// Exact-market view: every fixture in the round/league for that market, sorted
// by pc. Missing actual prices stay in the list with no actual-EV claim.
export function selectMarketRows<T extends OddsCandidate>(candidates: T[]): T[] {
  return [...candidates].sort(probabilityOrder);
}

// Optional refinements are never applied by default and never turn an empty
// refinement into an empty-market state; the caller shows `hidden` with Show all.
export function applyRefinement<T extends { pc: number }>(
  rows: T[],
  refinement: Refinement,
): { rows: T[]; hidden: number } {
  if (refinement === 'all') return { rows, hidden: 0 };
  const kept = rows.filter((row) => {
    if (refinement === 'pc50') return row.pc >= 0.5;
    if (refinement === 'pc58') return row.pc >= 0.58;
    if (refinement === 'fair150') return fairOddsOf(row.pc) >= 1.5;
    return fairOddsOf(row.pc) >= 2.0;
  });
  return { rows: kept, hidden: rows.length - kept.length };
}

export function parseRefinement(raw: string | null | undefined): Refinement {
  const value = (raw ?? '').trim().toLowerCase();
  return REFINEMENTS.some((option) => option.token === value) ? (value as Refinement) : 'all';
}

// Decoder helper shared by the page and the contract runner. The compact round
// format stores rows as arrays against `fixture_list` + `fields`.
export function decodeRankRows(payload: Record<string, unknown>): RankRow[] {
  const raw = (payload.rows ?? []) as unknown[];
  if (!raw.length || !Array.isArray(raw[0])) return raw as RankRow[];
  const fixtures = (payload.fixture_list ?? []) as { d: string; k: string | null; h: string; a: string }[];
  const fields = (payload.fields ?? []) as string[];
  return (raw as unknown[][]).map((values) => {
    const fixture = fixtures[values[0] as number];
    const row: Record<string, unknown> = { d: fixture.d, k: fixture.k, h: fixture.h, a: fixture.a };
    fields.forEach((name, index) => { if (index < values.length) row[name] = values[index]; });
    if (row.pc === undefined) row.pc = row.p;
    return row as unknown as RankRow;
  });
}
