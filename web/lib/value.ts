import { priceKey, type PricedRow } from './prices';
import type { MarketMeta, RankRow } from './types';
import { evaluateRows, selectValue, type Evaluated } from './vetted';

// All Value rows for a round (settled or not): one per match, highest edge.
export function valueRowsForRound(
  rows: RankRow[],
  _markets: Record<string, MarketMeta>,
  priceIndex: Record<string, PricedRow>,
): Evaluated[] {
  return selectValue(evaluateRows(rows, (row) => priceIndex[priceKey(row.d, row.h, row.a, row.m)], 'type'));
}
