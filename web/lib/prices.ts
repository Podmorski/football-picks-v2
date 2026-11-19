// Shapes of web/public/data/mozzart-prices.json, generated at build time from
// the private prices repo only when PRICED=1. Never committed.

export type MozzartFixture = {
  div: string;
  home: string;
  away: string;
  kickoff: string | null;
  prices: Record<string, number>;
  match_similarity: number;
};

export type MozzartSnapshot = {
  round_date: string;
  fetched_at: string;
  fixtures: MozzartFixture[];
  unmatched_fixtures: { div: string; home: string; away: string; kickoff: string | null }[];
};

export type MozzartPricesFile = { rounds: MozzartSnapshot[] };

export type PricedRow = { odds: number; fetchedAt: string };

export function priceKey(div: string, home: string, away: string, market: string): string {
  return `${div}|${home}|${away}|${market}`;
}

export function snapshotFor(file: MozzartPricesFile | null, roundDate: string): MozzartSnapshot | null {
  return file?.rounds.find((round) => round.round_date === roundDate) ?? null;
}

export function buildPriceIndex(file: MozzartPricesFile | null, roundDate: string): Record<string, PricedRow> {
  const snapshot = snapshotFor(file, roundDate);
  const index: Record<string, PricedRow> = {};
  if (!snapshot) return index;
  for (const fixture of snapshot.fixtures) {
    for (const [market, odds] of Object.entries(fixture.prices)) {
      index[priceKey(fixture.div, fixture.home, fixture.away, market)] = {
        odds,
        fetchedAt: snapshot.fetched_at,
      };
    }
  }
  return index;
}

export function utcTime(iso: string): string {
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return '';
  const hours = String(value.getUTCHours()).padStart(2, '0');
  const minutes = String(value.getUTCMinutes()).padStart(2, '0');
  return `${hours}:${minutes} UTC`;
}

export function isOld(fetchedAt: string, kickoff: string | null, now: number = Date.now()): boolean {
  const age = now - new Date(fetchedAt).getTime();
  if (!Number.isFinite(age) || age <= 12 * 60 * 60 * 1000) return false;
  if (!kickoff) return false;
  const start = new Date(kickoff).getTime();
  return Number.isFinite(start) && now < start;
}

export function vsFairPct(odds: number, fair: number): number {
  return (odds / fair - 1) * 100;
}

export function signedPct(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
}
