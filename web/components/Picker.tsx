'use client';

import { Fragment, useEffect, useMemo, useState } from 'react';
import { Check, ChevronDown, Minus, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
  buildPriceIndex,
  isOld,
  priceKey,
  signedPct,
  snapshotFor,
  utcTime,
  vsFairPct,
  type MozzartPricesFile,
} from '@/lib/prices';
import {
  addTicket,
  combinedFair,
  combinedMozzart,
  combinedProbability,
  legKey,
  overallStatus,
  payout,
  sameMatchWarning,
  ticketVsFair,
  type TicketLeg,
} from '@/lib/ticket';
import { optimiseTickets } from '@/lib/ticketOpt';
import type { MarketMeta, RankRow } from '@/lib/types';

const GROUP_ORDER = [
  'Combos',
  'HT/FT',
  'Goals',
  'BTTS',
  'Half-time',
  'Team goals',
  'Result & double chance',
  'Correct score',
];
const GROUP_LABEL: Record<string, string> = {
  Combos: 'All combos',
  'HT/FT': 'All HT/FT',
  Goals: 'All goals',
  BTTS: 'All BTTS',
  'Half-time': 'All half-time',
  'Team goals': 'All team goals',
  'Result & double chance': 'All result & double chance',
  'Correct score': 'All correct score',
};
const FLOORS: [string, string, number][] = [
  ['any', 'Any', 0],
  ['1.30', '1.30+', 1.3],
  ['1.50', '1.50+', 1.5],
  ['2.00', '2.00+', 2.0],
  ['3.00', '3.00+', 3.0],
];
const TARGETS = [2, 3, 5, 10, 20];
const MAX_LEG_OPTIONS = [2, 3, 4, 5];
const LADDER_LABELS: Record<string, string> = {
  'GOAL_RANGE_FT:1+': 'FT 1+ goals',
  'GOAL_RANGE_FT:2+': 'FT 2+ goals',
  'GOAL_RANGE_FT:3+': 'FT 3+ goals',
  'GOAL_RANGE_FT:4+': 'FT 4+ goals',
  'GOAL_RANGE_FT:5+': 'FT 5+ goals',
  'GOAL_RANGE_FT:0-1': 'Under 1.5',
  'GOAL_RANGE_FT:0-2': 'Under 2.5',
  'GOAL_RANGE_FT:0-3': 'Under 3.5',
  'GOAL_RANGE_1H:I1+': '1st half 1+',
  'GOAL_RANGE_1H:I2+': '1st half 2+',
  'BTTS:GG': 'Both teams score',
};

type SortKey = 'pc' | 'fair' | 'mozzart' | 'vsfair' | 'vsusual' | 'kickoff';

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function pcOf(row: RankRow): number {
  return row.pc ?? row.p;
}

function fairOf(row: RankRow): number {
  return 1 / Math.max(pcOf(row), 0.0001);
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

function decodeRows(payload: Record<string, unknown>): RankRow[] {
  const raw = (payload.rows ?? []) as unknown[];
  if (!raw.length || !Array.isArray(raw[0])) return raw as RankRow[];
  const fixtures = (payload.fixture_list ?? []) as { d: string; k: string | null; h: string; a: string }[];
  const fields = (payload.fields ?? []) as string[];
  return (raw as unknown[][]).map((values) => {
    const fixture = fixtures[values[0] as number];
    const row: Record<string, unknown> = { d: fixture.d, k: fixture.k, h: fixture.h, a: fixture.a };
    fields.forEach((name, index) => {
      if (index < values.length) row[name] = values[index];
    });
    if (row.pc === undefined) row.pc = row.p;
    return row as unknown as RankRow;
  });
}

function pickPool(rows: RankRow[], bet: string, league: string, markets: Record<string, MarketMeta>, minFair: number): RankRow[] {
  const filtered = rows.filter((row) => (league === 'all' || row.d === league) && fairOf(row) >= minFair);
  if (bet === 'any') {
    const best = new Map<string, RankRow>();
    for (const row of filtered) {
      if (row.m === 'RESULT:1' || row.m === 'RESULT:2') continue;
      const key = `${row.h}|${row.a}`;
      const current = best.get(key);
      if (!current || pcOf(row) > pcOf(current)) best.set(key, row);
    }
    return [...best.values()];
  }
  if (bet.startsWith('group:')) {
    const group = bet.slice(6);
    const best = new Map<string, RankRow>();
    for (const row of filtered) {
      if ((markets[row.m]?.group ?? '') !== group) continue;
      const key = `${row.h}|${row.a}`;
      const current = best.get(key);
      if (!current || pcOf(row) > pcOf(current)) best.set(key, row);
    }
    return [...best.values()];
  }
  const id = bet.slice(7);
  return filtered.filter((row) => row.m === id);
}

function metric(row: RankRow, key: SortKey, priceIndex: Record<string, { odds: number }>): number | string {
  const fair = fairOf(row);
  const price = priceIndex[priceKey(row.d, row.h, row.a, row.m)];
  if (key === 'fair') return fair;
  if (key === 'mozzart') return price ? price.odds : -1;
  if (key === 'vsfair') return price ? price.odds / fair - 1 : -Infinity;
  if (key === 'vsusual') return row.lr > 0 ? pcOf(row) / row.lr - 1 : -Infinity;
  if (key === 'kickoff') return row.k ?? '';
  return pcOf(row);
}

function sortRows(rows: RankRow[], key: SortKey, dir: string, priceIndex: Record<string, { odds: number }>): RankRow[] {
  const sign = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const left = metric(a, key, priceIndex);
    const right = metric(b, key, priceIndex);
    if (typeof left === 'string' || typeof right === 'string') {
      return sign * String(left).localeCompare(String(right));
    }
    return sign * ((left as number) - (right as number));
  });
}

const STATUS_VARIANT = { landed: 'success', lost: 'destructive', pending: 'secondary', void: 'outline' } as const;

function StatusBadge({ status }: { status?: string }) {
  const value = status === 'landed' || status === 'lost' || status === 'void' ? status : 'pending';
  const label = value === 'landed' ? 'Landed' : value === 'lost' ? 'Lost' : value === 'void' ? 'Void' : 'Pending';
  return (
    <Badge variant={STATUS_VARIANT[value]} className="shrink-0">
      {value === 'landed' ? <Check className="h-3 w-3" /> : value === 'lost' ? <X className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
      {label}
    </Badge>
  );
}

export default function Picker({
  date,
  kind,
  leagueOptions,
  roundOptions = [],
}: {
  date: string;
  kind: string;
  leagueOptions: [string, string, string][];
  roundOptions?: [string, string][];
}) {
  const [data, setData] = useState<{ rows: RankRow[]; ladder: string[] } | null>(null);
  const [markets, setMarkets] = useState<Record<string, MarketMeta>>({});
  const [prices, setPrices] = useState<MozzartPricesFile | null>(null);
  const [priced, setPriced] = useState(false);
  const [league, setLeague] = useParam('league', 'all');
  const [bet, setBet] = useParam('bet', 'group:Combos');
  const [sort, setSort] = useParam('sort', 'pc');
  const [dir, setDir] = useParam('dir', 'desc');
  const [showAll, setShowAll] = useParam('all', '0');
  const [roundParam, setRound] = useParam('round', date);
  const [mozzartOnly, setMozzartOnly] = useParam('mozzart', '0');
  const [min, setMin] = useParam('min', '1.50');
  const [target, setTarget] = useParam('target', '5');
  const [maxLegs, setMaxLegs] = useParam('legs', '5');
  const [matchParam, setMatch] = useParam('match', '');
  const [pastRounds, setPastRounds] = useState<{ date: string; label: string; rows: RankRow[] }[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [leagueQuery, setLeagueQuery] = useState('');
  const [betQuery, setBetQuery] = useState('');
  const [ticket, setTicket] = useState<TicketLeg[]>([]);
  const [bonus, setBonus] = useState(0);
  const [stake, setStake] = useState(10);
  const [ticketOpen, setTicketOpen] = useState(false);

  const activeDate = /^\d{4}-\d{2}-\d{2}$/.test(roundParam) ? roundParam : date;

  useEffect(() => {
    let cancelled = false;
    setData(null);
    const urls = [`/data/rounds/${activeDate}.full.json`, `/data/rounds/${activeDate}.json`];
    (async () => {
      for (const url of urls) {
        const response = await fetch(url);
        if (!response.ok) continue;
        const payload = (await response.json()) as Record<string, unknown>;
        if (!cancelled) setData({ rows: decodeRows(payload), ladder: (payload.ladder as string[]) ?? [] });
        return;
      }
      if (!cancelled) setData({ rows: [], ladder: [] });
    })().catch(() => {
      if (!cancelled) setData({ rows: [], ladder: [] });
    });
    return () => {
      cancelled = true;
    };
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
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/mozzart-prices.json')
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: MozzartPricesFile | null) => {
        if (cancelled) return;
        setPrices(payload);
        setPriced(payload !== null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/rounds/index.json')
      .then((response) => (response.ok ? response.json() : { rounds: [] }))
      .then(async (payload: { rounds: { date: string; label: string; picks: number }[] }) => {
        const seen = new Set<string>();
        const dates = (payload.rounds ?? [])
          .filter((round) => {
            if (round.picks <= 0 || seen.has(round.date)) return false;
            seen.add(round.date);
            return true;
          })
          .sort((a, b) => (a.date < b.date ? 1 : -1))
          .slice(0, 12);
        const loaded = await Promise.all(
          dates.map(async (round) => {
            for (const url of [`/data/rounds/${round.date}.full.json`, `/data/rounds/${round.date}.json`]) {
              const response = await fetch(url);
              if (!response.ok) continue;
              const data = (await response.json()) as Record<string, unknown>;
              return { date: round.date, label: round.label, rows: decodeRows(data) };
            }
            return { date: round.date, label: round.label, rows: [] as RankRow[] };
          }),
        );
        if (!cancelled) setPastRounds(loaded);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const savedBonus = window.localStorage.getItem('fpv2-bonus');
    const savedStake = window.localStorage.getItem('fpv2-stake');
    if (savedBonus) setBonus(Number(savedBonus) || 0);
    if (savedStake) setStake(Number(savedStake) || 10);
  }, []);
  useEffect(() => {
    window.localStorage.setItem('fpv2-bonus', String(bonus));
  }, [bonus]);
  useEffect(() => {
    window.localStorage.setItem('fpv2-stake', String(stake));
  }, [stake]);

  const leagueNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const [code, name] of leagueOptions) map[code] = name;
    return map;
  }, [leagueOptions]);

  const countries = useMemo(() => {
    const groups = new Map<string, [string, string][]>();
    for (const [code, name, country] of leagueOptions) {
      if (!groups.has(country)) groups.set(country, []);
      groups.get(country)?.push([code, name]);
    }
    return [...groups.entries()];
  }, [leagueOptions]);

  const marketGroups = useMemo(() => {
    const groups = new Map<string, MarketMeta[]>();
    for (const market of Object.values(markets)) {
      if (!groups.has(market.group)) groups.set(market.group, []);
      groups.get(market.group)?.push(market);
    }
    for (const list of groups.values()) list.sort((a, b) => a.plain.localeCompare(b.plain));
    return groups;
  }, [markets]);

  const priceIndex = useMemo(() => buildPriceIndex(prices, activeDate), [prices, activeDate]);
  const snapshot = useMemo(() => snapshotFor(prices, activeDate), [prices, activeDate]);

  const floor = min === 'any' ? 0 : Number(min);
  const pool = useMemo(
    () => pickPool(data?.rows ?? [], bet, league, markets, floor),
    [data, bet, league, markets, floor],
  );
  const valuePool = useMemo(() => {
    if (mozzartOnly !== '1') return pool;
    return pool.filter((row) => {
      const price = priceIndex[priceKey(row.d, row.h, row.a, row.m)];
      return price !== undefined && price.odds >= fairOf(row);
    });
  }, [pool, mozzartOnly, priceIndex]);

  const sorted = useMemo(() => sortRows(valuePool, sort as SortKey, dir, priceIndex), [valuePool, sort, dir, priceIndex]);
  const visible = showAll === '1' ? sorted : sorted.slice(0, 10);

  const matchRow = useMemo(() => {
    const parts = matchParam.split('|');
    if (parts.length !== 3 || !parts[0] || !parts[1] || !parts[2]) return null;
    return { d: parts[0], h: parts[1], a: parts[2] };
  }, [matchParam]);
  const matchRows = useMemo(() => {
    if (!matchRow) return [];
    return (data?.rows ?? [])
      .filter((row) => row.d === matchRow.d && row.h === matchRow.h && row.a === matchRow.a && fairOf(row) >= floor)
      .sort((a, b) => pcOf(b) - pcOf(a))
      .slice(0, 10);
  }, [data, matchRow, floor]);

  const settled = sorted.filter((row) => row.st === 'landed' || row.st === 'lost');
  const landed = settled.filter((row) => row.st === 'landed').length;
  const expected = settled.reduce((total, row) => total + pcOf(row), 0);
  const belowFloor = useMemo(() => {
    if (!bet.startsWith('market:')) return 0;
    const id = bet.slice(7);
    const byMatch = new Map<string, number>();
    for (const row of data?.rows ?? []) {
      if (league !== 'all' && row.d !== league) continue;
      if (row.m !== id) continue;
      byMatch.set(`${row.h}|${row.a}`, fairOf(row));
    }
    let count = 0;
    for (const value of byMatch.values()) if (value < floor) count += 1;
    return count;
  }, [data, bet, league, floor]);

  function priceOf(row: RankRow) {
    return priceIndex[priceKey(row.d, row.h, row.a, row.m)];
  }

  function legFrom(row: RankRow, pIndex = priceIndex, snap = snapshot): TicketLeg {
    const meta = markets[row.m];
    const price = pIndex[priceKey(row.d, row.h, row.a, row.m)];
    const fixture = snap?.fixtures.find((item) => item.div === row.d && item.home === row.h && item.away === row.a);
    return {
      d: row.d,
      h: row.h,
      a: row.a,
      m: row.m,
      label: meta?.plain ?? row.m,
      mozzart: meta?.mozzart ?? '',
      pc: pcOf(row),
      fair: fairOf(row),
      odds: price?.odds ?? null,
      fetchedAt: price?.fetchedAt,
      kickoff: fixture?.kickoff ?? null,
      st: row.st,
      ht: row.ht,
      ft: row.ft,
    };
  }

  function toLeg(row: RankRow): TicketLeg {
    return legFrom(row);
  }

  function toggleLeg(row: RankRow) {
    const key = legKey(row);
    setTicket((current) =>
      current.some((leg) => legKey(leg) === key) ? current.filter((leg) => legKey(leg) !== key) : [...current, toLeg(row)],
    );
  }

  function saveCurrent() {
    if (ticket.length === 0) return;
    addTicket({ id: `${Date.now()}`, date: activeDate, legs: ticket, bonus, stake, savedAt: new Date().toISOString() });
    setTicket([]);
    setTicketOpen(false);
  }

  const targetValue = Number(target) || 5;
  const maxLegsValue = Number(maxLegs) || 5;
  const suggestions = useMemo(() => {
    const legs = valuePool.map(toLeg);
    return optimiseTickets(legs, targetValue, maxLegsValue, 3, floor);
  }, [valuePool, targetValue, maxLegsValue, floor, markets, priceIndex, snapshot]);

  const pastTickets = useMemo(() => {
    return pastRounds.map((round) => {
      const roundPriceIndex = buildPriceIndex(prices, round.date);
      const roundSnapshot = snapshotFor(prices, round.date);
      const roundPool = pickPool(round.rows, bet, league, markets, floor);
      const entries = [3, 5, 10].map((target) => {
        const legs = roundPool.map((row) => legFrom(row, roundPriceIndex, roundSnapshot));
        const tickets = optimiseTickets(legs, target, maxLegsValue, 1, floor);
        return { target, ticket: tickets[0] ?? null };
      });
      return { date: round.date, label: round.label, entries };
    });
  }, [pastRounds, bet, league, markets, floor, maxLegsValue, prices]);

  const pastTally = [3, 5, 10].map((target) => {
    const tickets = pastTickets.flatMap((round) => {
      const entry = round.entries.find((item) => item.target === target);
      return entry?.ticket ? [entry.ticket] : [];
    });
    const settled = tickets.filter((ticket) => {
      const status = overallStatus(ticket.legs);
      return status === 'landed' || status === 'lost';
    });
    const landed = settled.filter((ticket) => overallStatus(ticket.legs) === 'landed').length;
    const expected = settled.reduce((total, ticket) => total + ticket.probability, 0);
    return { target, landed, total: settled.length, expected };
  });

  const ticketProbability = combinedProbability(ticket);
  const ticketFair = combinedFair(ticket);
  const ticketMozzart = combinedMozzart(ticket);
  const ticketValue = ticketVsFair(ticket, bonus);
  const ticketPayout = payout(stake, ticket, bonus);
  const correlated = sameMatchWarning(ticket);

  const leagueMissing = (data?.rows.length ?? 0) === 0 || (league !== 'all' && !(data?.rows ?? []).some((row) => row.d === league));
  const leagueLabel = league === 'all' ? 'matches' : `${leagueNames[league] ?? league} matches`;

  function sortHeader(key: SortKey, label: string) {
    return (
      <button
        type="button"
        onClick={() => {
          if (sort === key) setDir(dir === 'desc' ? 'asc' : 'desc');
          else {
            setSort(key);
            setDir('desc');
          }
        }}
        className={cn('inline-flex items-center gap-1', sort === key && 'text-foreground')}
      >
        {label}
        {sort === key ? <span className="text-[10px]">{dir === 'desc' ? 'v' : '^'}</span> : null}
      </button>
    );
  }

  return (
    <div className="space-y-4 pb-40">
      {roundOptions.length > 1 ? (
        <div className="flex flex-wrap gap-1.5">
          {roundOptions.map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setRound(value)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium',
                activeDate === value ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}

      {matchRow ? (
        <section className="space-y-2 rounded-xl border p-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Best bets for {matchRow.h} v {matchRow.a}</h2>
            <button type="button" onClick={() => setMatch('')} className="rounded-md border px-2.5 py-1 text-xs">
              Back to list
            </button>
          </div>
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-2 py-2 text-left font-semibold">Bet</th>
                  <th className="px-2 py-2 text-right font-semibold">Prob</th>
                  <th className="px-2 py-2 text-right font-semibold">Fair</th>
                  <th className="px-2 py-2 text-right font-semibold">Mozzart</th>
                  <th className="px-2 py-2 text-left font-semibold">Result</th>
                </tr>
              </thead>
              <tbody>
                {matchRows.map((line) => {
                  const meta = markets[line.m];
                  const price = priceOf(line);
                  return (
                    <tr key={line.m} className="border-t">
                      <td className="px-2 py-1.5">
                        {meta?.plain ?? line.m} <span className="text-xs text-muted-foreground">({meta?.mozzart ?? ''})</span>
                      </td>
                      <td className="tabular px-2 py-1.5 text-right font-medium">{pct(pcOf(line))}</td>
                      <td className="tabular px-2 py-1.5 text-right">{fairOf(line).toFixed(2)}</td>
                      <td className="tabular px-2 py-1.5 text-right">{price ? price.odds.toFixed(2) : priced ? 'no price' : '—'}</td>
                      <td className="px-2 py-1.5">
                        <StatusBadge status={line.st} />
                        {line.ht || line.ft ? (
                          <span className="tabular block text-xs text-muted-foreground">HT {line.ht ?? '–'} · FT {line.ft ?? '–'}</span>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {matchRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No bets clear the floor for this match.</p>
          ) : null}
        </section>
      ) : null}

      <div className="space-y-2 rounded-xl border p-3">
        <div className="grid gap-2 sm:grid-cols-2">
          <div>
            <label className="text-xs font-medium text-muted-foreground" htmlFor="league-query">League</label>
            <input
              id="league-query"
              value={leagueQuery}
              onChange={(event) => setLeagueQuery(event.target.value)}
              placeholder="Search leagues"
              className="mb-1 w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            />
            <select
              value={league}
              onChange={(event) => setLeague(event.target.value)}
              aria-label="League"
              className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            >
              <option value="all">All leagues</option>
              {countries.map(([country, leagues]) => {
                const filtered = leagues.filter(([, name]) => name.toLowerCase().includes(leagueQuery.toLowerCase()));
                if (filtered.length === 0) return null;
                return (
                  <optgroup key={country} label={country}>
                    {filtered.map(([code, name]) => (
                      <option key={code} value={code}>{name}</option>
                    ))}
                  </optgroup>
                );
              })}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground" htmlFor="bet-query">Bet</label>
            <input
              id="bet-query"
              value={betQuery}
              onChange={(event) => setBetQuery(event.target.value)}
              placeholder="Search bets"
              className="mb-1 w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            />
            <select
              value={bet}
              onChange={(event) => setBet(event.target.value)}
              aria-label="Bet"
              className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            >
              <option value="any">Any bet</option>
              {GROUP_ORDER.map((group) => {
                const list = (marketGroups.get(group) ?? []).filter(
                  (market) =>
                    market.plain.toLowerCase().includes(betQuery.toLowerCase()) ||
                    market.mozzart.toLowerCase().includes(betQuery.toLowerCase()),
                );
                if (list.length === 0 && betQuery) return null;
                return (
                  <optgroup key={group} label={GROUP_LABEL[group] ?? group}>
                    <option value={`group:${group}`}>{GROUP_LABEL[group] ?? group}</option>
                    {list.map((market) => (
                      <option key={market.id} value={`market:${market.id}`}>
                        {market.plain} ({market.mozzart})
                      </option>
                    ))}
                  </optgroup>
                );
              })}
            </select>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Sort by</span>
          {([['pc', 'Probability'], ['fair', 'Fair odds'], ['mozzart', 'Mozzart'], ['vsfair', 'Mozzart vs fair'], ['vsusual', 'vs usual'], ['kickoff', 'Kickoff']] as [SortKey, string][]).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => { setSort(key); setDir('desc'); }}
              className={cn('rounded-full border px-2.5 py-1 text-xs', sort === key ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground')}
            >
              {label}
            </button>
          ))}
          {priced ? (
            <button
              type="button"
              onClick={() => setMozzartOnly(mozzartOnly === '1' ? '0' : '1')}
              className={cn('rounded-full border px-2.5 py-1 text-xs', mozzartOnly === '1' ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground')}
            >
              Only where Mozzart pays more than fair
            </button>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-xs text-muted-foreground">Odds floor</span>
          {FLOORS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setMin(key)}
              className={cn('rounded-full border px-2.5 py-1 text-xs', min === key ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground')}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <p className="text-sm text-muted-foreground">
        {visible.length}{visible.length < sorted.length ? ` of ${sorted.length}` : ''}{' '}
        {bet === 'any'
          ? 'best matches'
          : bet.startsWith('group:')
            ? `best matches for ${GROUP_LABEL[bet.slice(6)] ?? 'this group'}`
            : `best matches for ${markets[bet.slice(7)]?.plain ?? 'this bet'}`}
        {' · '}{league === 'all' ? 'all leagues' : (leagueNames[league] ?? league)} · {kind === 'example' ? 'Example round' : activeDate}
      </p>
      {settled.length > 0 ? (
        <p className="text-sm">Result: <span className="font-medium">{landed} of {settled.length} landed</span> · expected about {expected.toFixed(1)}</p>
      ) : (
        <p className="text-sm text-muted-foreground">Results appear after the matches (usually by Monday)</p>
      )}
      {bet.startsWith('market:') && belowFloor > 0 ? (
        <p className="text-xs text-muted-foreground">{belowFloor} matches below {floor > 0 ? floor.toFixed(2) : 'the floor'}</p>
      ) : null}

      {leagueMissing ? (
        <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          No {leagueLabel} in this round.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full min-w-[58rem] text-sm">
            <thead>
              <tr className="bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground">
                <th className="w-8 px-2 py-2" />
                <th className="px-2 py-2 text-left font-semibold">{sortHeader('kickoff', 'KO')}</th>
                <th className="px-2 py-2 text-left font-semibold">Match</th>
                <th className="px-2 py-2 text-left font-semibold">League</th>
                <th className="px-2 py-2 text-left font-semibold">Bet</th>
                <th className="px-2 py-2 text-right font-semibold">{sortHeader('pc', 'Prob')}</th>
                <th className="px-2 py-2 text-right font-semibold">{sortHeader('fair', 'Fair')}</th>
                <th className="px-2 py-2 text-right font-semibold">{sortHeader('mozzart', 'Mozzart')}</th>
                <th className="px-2 py-2 text-right font-semibold">{sortHeader('vsfair', 'vs fair')}</th>
                <th className="px-2 py-2 text-right font-semibold">{sortHeader('vsusual', 'vs usual')}</th>
                <th className="px-2 py-2 text-left font-semibold">Conf</th>
                <th className="px-2 py-2 text-left font-semibold">Result</th>
                <th className="w-8 px-2 py-2" />
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => {
                const meta = markets[row.m];
                const price = priceOf(row);
                const fair = fairOf(row);
                const fixture = snapshot?.fixtures.find((item) => item.div === row.d && item.home === row.h && item.away === row.a);
                const stale = price ? isOld(price.fetchedAt, fixture?.kickoff ?? null) : false;
                const key = legKey(row);
                const open = expanded === key;
                const checked = ticket.some((leg) => legKey(leg) === key);
                const siblings = (data?.rows ?? [])
                  .filter((candidate) => candidate.h === row.h && candidate.a === row.a && candidate.m !== row.m)
                  .sort((a, b) => pcOf(b) - pcOf(a))
                  .slice(0, 5);
                const ladderRows = (data?.ladder ?? []).map((id) => (data?.rows ?? []).find((candidate) => candidate.h === row.h && candidate.a === row.a && candidate.m === id)).filter(Boolean) as RankRow[];
                return (
                  <Fragment key={key}>
                    <tr className="border-t align-top">
                      <td className="px-2 py-2">
                        <input type="checkbox" checked={checked} onChange={() => toggleLeg(row)} aria-label="Add to ticket" />
                      </td>
                      <td className="tabular px-2 py-2 text-muted-foreground">{row.k ?? ''}</td>
                      <td className="px-2 py-2 font-medium">
                        <button
                          type="button"
                          onClick={() => setMatch(`${row.d}|${row.h}|${row.a}`)}
                          className="text-left underline-offset-2 hover:underline"
                        >
                          {row.h} <span className="text-muted-foreground">v</span> {row.a}
                        </button>
                      </td>
                      <td className="px-2 py-2 text-muted-foreground">{leagueNames[row.d] ?? row.d}</td>
                      <td className="px-2 py-2">
                        {meta?.plain ?? row.m} <span className="text-xs text-muted-foreground">({meta?.mozzart ?? ''})</span>
                      </td>
                      <td className="tabular px-2 py-2 text-right font-semibold">{pct(pcOf(row))}</td>
                      <td className="tabular px-2 py-2 text-right">{fair.toFixed(2)}</td>
                      <td className="tabular px-2 py-2 text-right">
                        {price ? (
                          <span>
                            {price.odds.toFixed(2)} <span className="text-xs text-muted-foreground">{utcTime(price.fetchedAt)}{stale ? ' · old' : ''}</span>
                          </span>
                        ) : priced ? (
                          <span className="text-xs text-muted-foreground">no price</span>
                        ) : '—'}
                      </td>
                      <td className="tabular px-2 py-2 text-right">{price ? signedPct(vsFairPct(price.odds, fair)) : '—'}</td>
                      <td className="tabular px-2 py-2 text-right">{row.lr > 0 ? signedPct((pcOf(row) / row.lr - 1) * 100) : '—'}</td>
                      <td className="px-2 py-2">{row.c}</td>
                      <td className="px-2 py-2">
                        <StatusBadge status={row.st} />
                        {row.ht || row.ft ? <span className="tabular block text-xs text-muted-foreground">HT {row.ht ?? '–'} · FT {row.ft ?? '–'}</span> : null}
                      </td>
                      <td className="px-2 py-2">
                        <button type="button" onClick={() => setExpanded(open ? null : key)} aria-label="Expand">
                          <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform', open && 'rotate-180')} />
                        </button>
                      </td>
                    </tr>
                    {open ? (
                      <tr className="border-t bg-muted/30">
                        <td colSpan={13} className="px-3 py-2 text-sm text-muted-foreground">
                          <div className="space-y-2">
                            <div>
                              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">Goal ladder</h4>
                              <ul className="grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
                                {ladderRows.map((line) => (
                                  <li key={line.m} className={cn('flex items-baseline justify-between gap-2', line.m === row.m && 'font-medium text-foreground')}>
                                    <span>{LADDER_LABELS[line.m] ?? line.m}</span>
                                    <span className="tabular">{pct(pcOf(line))} · {fairOf(line).toFixed(2)}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                            {siblings.length > 0 ? (
                              <div>
                                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">Other bets in this match</h4>
                                <ul className="space-y-0.5">
                                  {siblings.map((sibling) => (
                                    <li key={sibling.m} className="flex items-baseline justify-between gap-2">
                                      <span>{markets[sibling.m]?.plain ?? sibling.m}</span>
                                      <span className="tabular">{pct(pcOf(sibling))} · {fairOf(sibling).toFixed(2)}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {sorted.length > 10 && showAll !== '1' ? (
        <button type="button" onClick={() => setShowAll('1')} className="rounded-md border px-3 py-1.5 text-sm">
          Show all ({sorted.length})
        </button>
      ) : null}
      {showAll === '1' && sorted.length > 10 ? (
        <button type="button" onClick={() => setShowAll('0')} className="rounded-md border px-3 py-1.5 text-sm">
          Show top 10
        </button>
      ) : null}

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Target tickets</h2>
        <p className="text-sm text-muted-foreground">
          Highest combined probability whose combined fair odds reach the target, one leg per match, from the current filters.
          {priced ? (mozzartOnly === '1' ? ' Only legs where Mozzart pays at least fair.' : ' Mozzart odds shown when priced.') : ''}
        </p>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label className="flex items-center gap-1">Target
            <select value={target} onChange={(event) => setTarget(event.target.value)} className="rounded-md border bg-background px-2 py-1">
              {TARGETS.map((value) => <option key={value} value={String(value)}>{value.toFixed(2)}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">Max legs
            <select value={maxLegs} onChange={(event) => setMaxLegs(event.target.value)} className="rounded-md border bg-background px-2 py-1">
              {MAX_LEG_OPTIONS.map((value) => <option key={value} value={String(value)}>{value}</option>)}
            </select>
          </label>
          <span className="text-xs text-muted-foreground">{suggestions.length} ticket(s) found</span>
        </div>
        {suggestions.length === 0 ? (
          <p className="rounded-xl border border-dashed px-4 py-4 text-sm text-muted-foreground">
            No ticket of at most {maxLegs} legs reaches {Number(target).toFixed(2)} at this floor.
          </p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2">
            {suggestions.map((suggestion, index) => {
              const mozzart = combinedMozzart(suggestion.legs);
              const vs = ticketVsFair(suggestion.legs, 0);
              return (
                <li key={`${index}-${suggestion.fair}`} className="rounded-xl border p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{suggestion.legs.length}-leg · #{index + 1}</span>
                    <span className="tabular">{pct(suggestion.probability)}</span>
                  </div>
                  <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                    {suggestion.legs.map((leg) => (
                      <li key={legKey(leg)} className="flex flex-wrap justify-between gap-2">
                        <span className="truncate">{leg.h} v {leg.a} · {leg.label}</span>
                        <span className="tabular">
                          {pct(leg.pc)} · {leg.fair.toFixed(2)} ·{' '}
                          {leg.st === 'landed' ? 'Landed ✓' : leg.st === 'lost' ? 'Lost ✗' : 'Pending'}
                          {leg.ht || leg.ft ? ` (${leg.ht ?? '–'} / ${leg.ft ?? '–'})` : ''}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-1 tabular text-xs text-muted-foreground">
                    Fair {suggestion.fair.toFixed(2)}
                    {mozzart !== null ? ` · Mozzart ${mozzart.toFixed(2)} · vs fair ${vs === null ? '–' : signedPct(vs * 100)}` : ' · Mozzart incomplete'}
                    {' · '}
                    <span className="font-medium">Ticket: {overallStatus(suggestion.legs)}</span>
                  </div>
                  <button type="button" onClick={() => setTicket(suggestion.legs)} className="mt-2 rounded-md border px-2.5 py-1 text-xs">
                    Add to my ticket
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Suggested tickets — past rounds</h2>
        <p className="text-sm text-muted-foreground">
          The #1 ticket for targets 3.00 / 5.00 / 10.00 in every published round, using the current League/Bet/floor filters and only that round&apos;s file.
        </p>
        {pastTally.some((row) => row.total > 0) ? (
          <ul className="flex flex-wrap gap-2 text-sm">
            {pastTally.map((row) => (
              <li key={row.target} className="rounded-full border px-3 py-1">
                {row.target.toFixed(2)}: {row.landed} of {row.total} landed · expected about {row.expected.toFixed(1)}
              </li>
            ))}
          </ul>
        ) : null}
        {pastTickets.length === 0 ? (
          <p className="rounded-xl border border-dashed px-4 py-4 text-sm text-muted-foreground">No published rounds yet.</p>
        ) : (
          <ul className="space-y-2">
            {pastTickets.map((round) => (
              <li key={round.date} className="rounded-xl border p-3 text-sm">
                <div className="font-medium">
                  {round.label} <span className="text-xs text-muted-foreground">({round.date})</span>
                </div>
                <ul className="mt-1 space-y-1">
                  {round.entries.map((entry) => {
                    if (!entry.ticket) {
                      return (
                        <li key={entry.target} className="text-xs text-muted-foreground">
                          {entry.target.toFixed(2)}: no ticket
                        </li>
                      );
                    }
                    const ticket = entry.ticket;
                    const mozzart = combinedMozzart(ticket.legs);
                    const vs = ticketVsFair(ticket.legs, 0);
                    const status = overallStatus(ticket.legs);
                    return (
                      <li key={entry.target} className="rounded-md bg-muted/30 px-2 py-1">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-medium">
                            {entry.target.toFixed(2)} · {pct(ticket.probability)} · fair {ticket.fair.toFixed(2)}
                          </span>
                          <span className={status === 'landed' ? 'text-xs text-emerald-600' : status === 'lost' ? 'text-xs text-rose-600' : 'text-xs text-muted-foreground'}>
                            {status === 'landed' ? 'Landed' : status === 'lost' ? 'Lost' : 'Pending'}
                          </span>
                        </div>
                        <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                          {ticket.legs.map((leg) => (
                            <li key={legKey(leg)} className="flex flex-wrap justify-between gap-2">
                              <span className="truncate">{leg.h} v {leg.a} · {leg.label} · {pct(leg.pc)} · {leg.fair.toFixed(2)}</span>
                              <span>
                                {leg.st === 'landed' ? 'Landed ✓' : leg.st === 'lost' ? 'Lost ✗' : 'Pending'}
                                {leg.ht || leg.ft ? ` (${leg.ht ?? '–'} / ${leg.ft ?? '–'})` : ''}
                              </span>
                            </li>
                          ))}
                        </ul>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {mozzart !== null ? `Mozzart ${mozzart.toFixed(2)} · vs fair ${vs === null ? '–' : signedPct(vs * 100)}` : 'Mozzart incomplete'}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </section>

      {ticket.length > 0 ? (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/95 backdrop-blur">
          <div className="mx-auto max-w-5xl px-4 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button type="button" onClick={() => setTicketOpen(!ticketOpen)} className="text-sm font-medium">
                My ticket · {ticket.length} legs · {pct(ticketProbability)}
              </button>
              <div className="flex gap-2">
                <button type="button" onClick={() => setTicketOpen(!ticketOpen)} className="rounded-md border px-2.5 py-1 text-xs">
                  {ticketOpen ? 'Hide' : 'View'}
                </button>
                <button type="button" onClick={() => setTicket([])} className="rounded-md border px-2.5 py-1 text-xs">Clear</button>
              </div>
            </div>
            {ticketOpen ? (
              <div className="mt-2 max-h-[60vh] space-y-2 overflow-y-auto">
                <ul className="space-y-1 text-sm">
                  {ticket.map((leg) => (
                    <li key={legKey(leg)} className="flex items-center justify-between gap-2">
                      <span className="truncate">{leg.h} v {leg.a} · {leg.label} · {pct(leg.pc)} · {leg.fair.toFixed(2)}{leg.odds !== null ? ` · Mozzart ${leg.odds.toFixed(2)}` : ''}</span>
                      <button type="button" onClick={() => setTicket((current) => current.filter((item) => legKey(item) !== legKey(leg)))} className="text-xs text-muted-foreground">Remove</button>
                    </li>
                  ))}
                </ul>
                {correlated ? <p className="text-sm text-destructive">Same-match legs are correlated; combined % is not reliable.</p> : null}
                <div className="grid gap-2 text-sm sm:grid-cols-4">
                  <label className="flex flex-col gap-1">Bonus %
                    <input type="number" value={bonus} onChange={(event) => setBonus(Number(event.target.value) || 0)} className="w-full rounded-md border bg-background px-2 py-1" />
                  </label>
                  <label className="flex flex-col gap-1">Stake
                    <input type="number" value={stake} onChange={(event) => setStake(Number(event.target.value) || 0)} className="w-full rounded-md border bg-background px-2 py-1" />
                  </label>
                  <div>Combined %<div className="tabular font-medium">{pct(ticketProbability)}</div></div>
                  <div>Fair odds<div className="tabular font-medium">{ticketFair.toFixed(2)}</div></div>
                  <div>Mozzart<div className="tabular font-medium">{ticketMozzart === null ? 'incomplete' : ticketMozzart.toFixed(2)}</div></div>
                  <div>Ticket vs fair<div className="tabular font-medium">{ticketValue === null ? '–' : signedPct(ticketValue * 100)}</div></div>
                  <div>Payout<div className="tabular font-medium">{ticketPayout === null ? '–' : ticketPayout.toFixed(2)}</div></div>
                  <button type="button" onClick={saveCurrent} className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground">Save ticket</button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
