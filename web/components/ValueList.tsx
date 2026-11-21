'use client';

import { useEffect, useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { buildPriceIndex, snapshotFor, utcTime, type MozzartPricesFile } from '@/lib/prices';
import { valueRowsForRound } from '@/lib/value';
import type { MarketMeta, RankRow } from '@/lib/types';

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function decodeRows(payload: Record<string, unknown>): RankRow[] {
  const raw = (payload.rows ?? []) as unknown[];
  if (!raw.length || !Array.isArray(raw[0])) return raw as RankRow[];
  const fixtures = (payload.fixture_list ?? []) as { d: string; k: string | null; h: string; a: string }[];
  const fields = (payload.fields ?? []) as string[];
  const rows = (raw as unknown[][]).map((values) => {
    const fixture = fixtures[values[0] as number];
    const row: Record<string, unknown> = { d: fixture.d, k: fixture.k, h: fixture.h, a: fixture.a };
    fields.forEach((name, index) => { if (index < values.length) row[name] = values[index]; });
    if (row.pc === undefined) row.pc = row.p;
    return row as unknown as RankRow;
  });
  return rows;
}

function useParam(key: string, initial: string): [string, (next: string) => void] {
  const [value, setValue] = useState(initial);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const found = params.get(key);
    if (found) setValue(found);
  }, [key]);
  function update(next: string) {
    setValue(next);
    const params = new URLSearchParams(window.location.search);
    params.set(key, next);
    window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`);
  }
  return [value, update];
}

export default function ValueList({
  date, kind, leagueOptions, roundOptions = [],
}: {
  date: string; kind: string; leagueOptions: [string, string, string][]; roundOptions?: [string, string][];
}) {
  const [data, setData] = useState<{ rows: RankRow[] } | null>(null);
  const [markets, setMarkets] = useState<Record<string, MarketMeta>>({});
  const [prices, setPrices] = useState<MozzartPricesFile | null>(null);
  const [roundParam, setRound] = useParam('round', date);

  const activeDate = /^\d{4}-\d{2}-\d{2}$/.test(roundParam) ? roundParam : date;

  useEffect(() => {
    let cancelled = false;
    setData(null);
    (async () => {
      for (const url of [`/data/rounds/${activeDate}.full.json`, `/data/rounds/${activeDate}.json`]) {
        const response = await fetch(url);
        if (!response.ok) continue;
        const payload = (await response.json()) as Record<string, unknown>;
        if (!cancelled) setData({ rows: decodeRows(payload) });
        return;
      }
      if (!cancelled) setData({ rows: [] });
    })().catch(() => { if (!cancelled) setData({ rows: [] }); });
    return () => { cancelled = true; };
  }, [activeDate]);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/markets.json')
      .then((response) => (response.ok ? response.json() : { markets: [] }))
      .then((payload: { markets: MarketMeta[] }) => {
        if (cancelled) return;
        const map: Record<string, MarketMeta> = {};
        for (const market of payload.markets ?? []) map[market.id] = market;
        setMarkets(map);
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/mozzart-prices.json')
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: MozzartPricesFile | null) => { if (!cancelled) setPrices(payload); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  const leagueNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const [code, name] of leagueOptions) map[code] = name;
    return map;
  }, [leagueOptions]);

  const priceIndex = useMemo(() => buildPriceIndex(prices, activeDate), [prices, activeDate]);
  const snapshot = useMemo(() => snapshotFor(prices, activeDate), [prices, activeDate]);
  const rows = data?.rows ?? [];
  const valueRows = useMemo(() => valueRowsForRound(rows, markets, priceIndex), [rows, markets, priceIndex]);

  return (
    <div className="space-y-4 pb-24">
      {roundOptions.length > 1 ? (
        <div className="flex flex-wrap gap-1.5">
          {roundOptions.map(([value, label]) => (
            <button key={value} type="button" onClick={() => setRound(value)} className={cn('rounded-full border px-3 py-1 text-xs font-medium', activeDate === value ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground')}>{label}</button>
          ))}
        </div>
      ) : null}

      <p className="text-sm text-muted-foreground">
        {valueRows.length} value {valueRows.length === 1 ? 'bet' : 'bets'} this round · sorted by edge
        {kind === 'example' ? ' · Example round' : ''}
      </p>

      {valueRows.length === 0 ? (
        <p className="rounded-xl border border-dashed px-4 py-8 text-sm text-muted-foreground">
          {prices === null
            ? 'No Mozzart prices in this build, so Value bets cannot be shown here.'
            : 'No Value bets in this round. Value needs Mozzart at or above the minimum play odds plus the team-record and agreement checks.'}
        </p>
      ) : (
        <ul className="space-y-2">
          {valueRows.map((item) => {
            const { row, price, candidate } = item;
            const meta = markets[row.m];
            const edge = item.edge;
            return (
              <li key={`${row.h}|${row.a}|${row.m}`} className="rounded-xl border p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="text-muted-foreground">{row.k ?? ''}</span>
                      <span className="font-semibold">{row.h} <span className="text-muted-foreground">v</span> {row.a}</span>
                      <span className="text-xs text-muted-foreground">{leagueNames[row.d] ?? row.d}</span>
                      <Badge variant="value">Value</Badge>
                    </div>
                    <div className="mt-1 text-sm">
                      {meta?.plain ?? row.m} <span className="text-xs text-muted-foreground">({meta?.mozzart ?? ''})</span>
                    </div>
                  </div>
                  <div className="tabular text-right text-sm">
                    <div className="text-base font-semibold">{pct(candidate.probability)}</div>
                    <div className="text-xs text-muted-foreground">edge {edge > 0 ? '+' : ''}{(edge * 100).toFixed(1)}%</div>
                  </div>
                </div>
                <div className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-3">
                  <span>Mozzart <span className="font-medium text-foreground">{price ? price.odds.toFixed(2) : '–'}</span>{price ? ` · ${utcTime(price.fetchedAt)}` : ''}</span>
                  <span>Min play <span className="font-medium text-foreground">{item.minPlay.toFixed(2)}</span></span>
                  <span>Play only at odds ≥ {item.minPlay.toFixed(2)}</span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>{snapshot ? 'Priced snapshot' : 'No snapshot'}</span>
                  <span>·</span>
                  <span>{row.ht || row.ft ? `HT ${row.ht ?? '–'} · FT ${row.ft ?? '–'}` : 'Pending'}</span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
