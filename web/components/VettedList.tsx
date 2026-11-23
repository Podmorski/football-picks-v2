'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Minus, X } from 'lucide-react';

import MatchStats from '@/components/MatchStats';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
  buildPriceIndex,
  priceKey,
  signedPct,
  snapshotFor,
  utcTime,
  type MozzartPricesFile,
} from '@/lib/prices';
import { addTicket, combinedFair, combinedMinPlay, combinedMozzart, combinedProbability, legKey, payout, sameMatchWarning, ticketVsFair, type TicketLeg } from '@/lib/ticket';
import { optimiseTickets } from '@/lib/ticketOpt';
import { evaluateRows, isHiddenMarketId, isValue, pcOf, selectByMatch, selectPassing, selectType, type Evaluated } from '@/lib/vetted';
import type { VettingCheck } from '@/lib/vetting';
import { minPlay } from '@/lib/vetting';
import type { MarketMeta, RankRow } from '@/lib/types';

const GROUP_ORDER = ['Combos', 'HT/FT', 'Goals', 'BTTS', 'Half-time', 'Team goals', 'Result & double chance'];
const GROUP_LABEL: Record<string, string> = {
  Combos: 'All combos', 'HT/FT': 'All HT/FT', Goals: 'All goals', BTTS: 'All BTTS',
  'Half-time': 'All half-time', 'Team goals': 'All team goals',
  'Result & double chance': 'All result & double chance',
};
const LADDER_LABELS: Record<string, string> = {
  'GOAL_RANGE_FT:1+': 'FT 1+ goals', 'GOAL_RANGE_FT:2+': 'FT 2+ goals', 'GOAL_RANGE_FT:3+': 'FT 3+ goals',
  'GOAL_RANGE_FT:4+': 'FT 4+ goals', 'GOAL_RANGE_FT:5+': 'FT 5+ goals',
  'GOAL_RANGE_FT:0-1': 'Under 1.5', 'GOAL_RANGE_FT:0-2': 'Under 2.5', 'GOAL_RANGE_FT:0-3': 'Under 3.5',
  'GOAL_RANGE_1H:I1+': '1st half 1+', 'GOAL_RANGE_1H:I2+': '1st half 2+', 'BTTS:GG': 'Both teams score',
};
const TARGETS = [3, 5, 10];

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}
function useParam(key: string, initial: string): [string, (next: string, write?: boolean) => void] {
  const [value, setValue] = useState(initial);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const found = params.get(key);
    if (found) setValue(found);
  }, [key]);
  function update(next: string, write = true) {
    setValue(next);
    if (!write) return;
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
    fields.forEach((name, index) => { if (index < values.length) row[name] = values[index]; });
    if (row.pc === undefined) row.pc = row.p;
    return row as unknown as RankRow;
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

type EvaluatedRow = Evaluated;

export default function VettedList({
  date, kind, leagueOptions, roundOptions = [], roundMeta = {},
}: {
  date: string; kind: string; leagueOptions: [string, string, string][]; roundOptions?: [string, string][];
  roundMeta?: Record<string, { label: string; kind: string }>;
}) {
  const [data, setData] = useState<{ rows: RankRow[]; ladder: string[] } | null>(null);
  const [markets, setMarkets] = useState<Record<string, MarketMeta>>({});
  const [prices, setPrices] = useState<MozzartPricesFile | null>(null);
  const [roundState, setRoundState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [marketsState, setMarketsState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [pricesState, setPricesState] = useState<'loading' | 'ready' | 'unpriced' | 'error'>('loading');
  const [league, setLeague] = useParam('league', 'all');
  const [bet, setBet] = useParam('bet', 'any');
  const [minOdds, setMinOdds] = useParam('min', '1.70');
  const [mode, setMode] = useParam('mode', 'ranked');
  const [roundParam, setRound] = useParam('round', date);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [ticket, setTicket] = useState<TicketLeg[]>([]);
  const [bonus, setBonus] = useState(0);
  const [stake, setStake] = useState(10);
  const [ticketOpen, setTicketOpen] = useState(false);
  const [valueOnly, setValueOnly] = useState(true);
  const minParamRef = useRef(false);

  const activeDate = /^\d{4}-\d{2}-\d{2}$/.test(roundParam) ? roundParam : date;
  const activeMeta = roundMeta[activeDate] ?? { label: activeDate, kind };
  const activeKind = activeMeta.kind;

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has('min')) minParamRef.current = true;
  }, []);

  useEffect(() => {
    if (minParamRef.current) return;
    setMinOdds(bet === 'any' ? '1.70' : 'any', false);
  }, [bet]);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setRoundState('loading');
    (async () => {
      for (const url of [`/data/rounds/${activeDate}.full.json`, `/data/rounds/${activeDate}.json`]) {
        const response = await fetch(url);
        if (!response.ok) continue;
        const payload = (await response.json()) as Record<string, unknown>;
        if (!cancelled) {
          setData({ rows: decodeRows(payload), ladder: (payload.ladder as string[]) ?? [] });
          setRoundState('ready');
        }
        return;
      }
      if (!cancelled) setRoundState('error');
    })().catch(() => { if (!cancelled) setRoundState('error'); });
    return () => { cancelled = true; };
  }, [activeDate]);

  useEffect(() => {
    let cancelled = false;
    setMarketsState('loading');
    fetch('/data/markets.json')
      .then((response) => {
        if (!response.ok) throw new Error('markets');
        return response.json() as Promise<{ markets: MarketMeta[] }>;
      })
      .then((payload) => {
        if (cancelled) return;
        const map: Record<string, MarketMeta> = {};
        for (const market of payload.markets ?? []) map[market.id] = market;
        setMarkets(map);
        setMarketsState('ready');
      })
      .catch(() => { if (!cancelled) setMarketsState('error'); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setPricesState('loading');
    fetch('/data/mozzart-prices.json')
      .then(async (response) => {
        if (response.status === 404) {
          if (!cancelled) { setPrices(null); setPricesState('unpriced'); }
          return;
        }
        if (!response.ok) {
          if (!cancelled) setPricesState('error');
          return;
        }
        const payload = (await response.json()) as MozzartPricesFile;
        if (!cancelled) { setPrices(payload); setPricesState('ready'); }
      })
      .catch(() => { if (!cancelled) setPricesState('error'); });
    return () => { cancelled = true; };
  }, []);

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

  const isAny = bet === 'any';
  const isStrict = !isAny && mode === 'strict';
  const evaluatedAny = useMemo<EvaluatedRow[]>(() => {
    return evaluateRows(data?.rows ?? [], (row) => priceIndex[priceKey(row.d, row.h, row.a, row.m)], 'any');
  }, [data, priceIndex]);
  const evaluatedType = useMemo<EvaluatedRow[]>(() => {
    return evaluateRows(data?.rows ?? [], (row) => priceIndex[priceKey(row.d, row.h, row.a, row.m)], 'type');
  }, [data, priceIndex]);
  const activeEvaluated = isAny ? evaluatedAny : evaluatedType;

  const baseFiltered = useMemo(() => {
    return activeEvaluated.filter((item) => {
      if (league !== 'all' && item.row.d !== league) return false;
      if (isHiddenMarketId(item.row.m)) return false;
      if (isAny) return true;
      if (bet.startsWith('group:')) return (markets[item.row.m]?.group ?? '') === bet.slice(6);
      return item.row.m === bet.slice(7);
    });
  }, [activeEvaluated, league, bet, isAny, markets]);
  const minFair = minOdds === 'any' ? 0 : Number(minOdds) > 0 ? Number(minOdds) : (isAny ? 1.70 : 0);
  const dataReady = roundState === 'ready' && marketsState === 'ready';
  const countsReady = dataReady;

  const eligible = useMemo(
    () => baseFiltered.filter((item) => item.candidate.fairOdds >= minFair),
    [baseFiltered, minFair],
  );
  const baseCount = useMemo(
    () => bet.startsWith('group:')
      ? new Set(baseFiltered.map((item) => `${item.row.d}|${item.row.h}|${item.row.a}`)).size
      : baseFiltered.length,
    [baseFiltered, bet],
  );

  const strictPassing = useMemo(() => {
    if (isAny) return selectPassing(eligible, { minFair, mozzartOnly: false });
    return selectType(eligible, {
      perMatch: bet.startsWith('group:'),
      market: bet.startsWith('group:') ? undefined : bet.slice(7),
      minFair,
    });
  }, [eligible, isAny, bet, minFair]);

  const rankedDisplayed = useMemo(() => {
    if (isAny) return [];
    if (bet.startsWith('group:')) return selectByMatch(eligible);
    return [...eligible].sort((a, b) => b.candidate.probability - a.candidate.probability);
  }, [eligible, isAny, bet]);

  const displayed = isAny || isStrict ? strictPassing : rankedDisplayed;

  // TYPE_RULE match counts for the current round + league, per group and market.
  const typeCounts = useMemo(() => {
    const groupMatches = new Map<string, Set<string>>();
    const marketMatches = new Map<string, Set<string>>();
    for (const item of evaluatedType) {
      if (league !== 'all' && item.row.d !== league) continue;
      if (isHiddenMarketId(item.row.m)) continue;
      if (mode === 'strict' && !item.passed) continue;
      if (item.candidate.fairOdds < minFair) continue;
      const group = markets[item.row.m]?.group;
      if (!group) continue;
      const key = `${item.row.d}|${item.row.h}|${item.row.a}`;
      if (!groupMatches.has(group)) groupMatches.set(group, new Set());
      groupMatches.get(group)?.add(key);
      if (!marketMatches.has(item.row.m)) marketMatches.set(item.row.m, new Set());
      marketMatches.get(item.row.m)?.add(key);
    }
    return { groups: groupMatches, markets: marketMatches };
  }, [evaluatedType, league, markets, minFair, mode]);

  const failedCandidates = useMemo(() => {
    if (strictPassing.length > 0) return [];
    const seen = new Set<string>();
    const rows: { item: EvaluatedRow; failed: VettingCheck[] }[] = [];
    const ordered = [...eligible].sort((a, b) => b.candidate.probability - a.candidate.probability);
    for (const item of ordered) {
      const key = `${item.row.d}|${item.row.h}|${item.row.a}`;
      if (seen.has(key)) continue;
      const failed = item.checks.filter((check) => !check.flag && !check.passed);
      if (failed.length === 0) continue;
      seen.add(key);
      rows.push({ item, failed });
      if (rows.length >= 3) break;
    }
    return rows;
  }, [eligible, strictPassing.length]);

  const priceNote = pricesState === 'loading'
    ? 'Loading Mozzart prices…'
    : pricesState === 'error'
      ? 'Mozzart prices could not be loaded.'
      : pricesState === 'unpriced'
        ? 'Mozzart prices are not embedded in this build.'
        : snapshot
          ? null
          : 'No Mozzart snapshot for this round.';

  function priceUnavailableText(): string {
    if (pricesState === 'loading') return 'Loading Mozzart price…';
    if (pricesState === 'error') return 'Mozzart price unavailable (prices could not be loaded).';
    if (pricesState === 'unpriced') return 'Mozzart price unavailable (not embedded in this build).';
    if (!snapshot) return 'No Mozzart snapshot for this round.';
    return 'No Mozzart price for this bet.';
  }

  function toLeg(row: RankRow): TicketLeg {
    const meta = markets[row.m];
    const price = priceIndex[priceKey(row.d, row.h, row.a, row.m)];
    const fixture = snapshot?.fixtures.find((item) => item.div === row.d && item.home === row.h && item.away === row.a);
    const probability = pcOf(row);
    return {
      d: row.d, h: row.h, a: row.a, m: row.m, label: meta?.plain ?? row.m, mozzart: meta?.mozzart ?? '',
      pc: probability, fair: 1 / Math.max(probability, 0.0001), minPlay: minPlay(probability), odds: price?.odds ?? null,
      fetchedAt: price?.fetchedAt, kickoff: fixture?.kickoff ?? null, st: row.st, ht: row.ht, ft: row.ft,
    };
  }
  function toggleLeg(row: RankRow) {
    const key = legKey(row);
    setTicket((current) => current.some((leg) => legKey(leg) === key) ? current.filter((leg) => legKey(leg) !== key) : [...current, toLeg(row)]);
  }
  function saveCurrent() {
    if (ticket.length === 0) return;
    addTicket({ id: `${Date.now()}`, date: activeDate, legs: ticket, bonus, stake, savedAt: new Date().toISOString() });
    setTicket([]);
    setTicketOpen(false);
  }

  const targetTickets = useMemo(() => {
    const candidates = valueOnly ? strictPassing.filter(isValue) : strictPassing;
    const legs = candidates.map((item) => toLeg(item.row));
    if (legs.length === 0) return [];
    return TARGETS.map((target) => ({ target, ticket: optimiseTickets(legs, target, 5, 1, 1.0)[0] ?? null }));
  }, [strictPassing, markets, priceIndex, snapshot, valueOnly]);

  const betLabel = bet === 'any' ? 'Any bet' : bet.startsWith('group:') ? (GROUP_LABEL[bet.slice(6)] ?? 'group') : (markets[bet.slice(7)]?.plain ?? 'bet');
  const leagueLabel = league === 'all' ? 'any league' : (leagueNames[league] ?? league);
  const settledPicks = displayed.filter((item) => item.row.st === 'landed' || item.row.st === 'lost');
  const landedPicks = settledPicks.filter((item) => item.row.st === 'landed').length;
  const ticketProbability = combinedProbability(ticket);
  const ticketFair = combinedFair(ticket);
  const ticketMozzart = combinedMozzart(ticket);
  const ticketMinPlay = combinedMinPlay(ticket);
  const ticketValue = ticketVsFair(ticket, bonus);
  const ticketPayout = payout(stake, ticket, bonus);
  const correlated = sameMatchWarning(ticket);

  return (
    <div className="space-y-4 pb-40">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{activeMeta.label} — best bets</h2>
        {activeKind === 'example' ? <Badge variant="secondary">Example</Badge> : null}
      </div>

      {roundOptions.length > 1 ? (
        <div className="flex flex-wrap gap-1.5">
          {roundOptions.map(([value, label]) => (
            <button key={value} type="button" onClick={() => setRound(value)} className={cn('rounded-full border px-3 py-1 text-xs font-medium', activeDate === value ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground')}>{label}</button>
          ))}
        </div>
      ) : null}

      <div className="grid gap-2 sm:grid-cols-3">
        <select value={league} onChange={(event) => setLeague(event.target.value)} aria-label="League" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
          <option value="all">All leagues</option>
          {countries.map(([country, leagues]) => (
            <optgroup key={country} label={country}>
              {leagues.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
            </optgroup>
          ))}
        </select>
        <select value={bet} onChange={(event) => setBet(event.target.value)} aria-label="Bet" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
          <option value="any">Any bet</option>
          {GROUP_ORDER.map((group) => (
            <optgroup key={group} label={GROUP_LABEL[group]}>
              <option value={`group:${group}`}>{GROUP_LABEL[group]} ({countsReady ? (typeCounts.groups.get(group)?.size ?? 0) : '…'})</option>
              {(marketGroups.get(group) ?? []).map((market) => (
                <option key={market.id} value={`market:${market.id}`}>{market.plain} ({countsReady ? (typeCounts.markets.get(market.id)?.size ?? 0) : '…'})</option>
              ))}
            </optgroup>
          ))}
        </select>
        <select value={minOdds} onChange={(event) => { minParamRef.current = true; setMinOdds(event.target.value); }} aria-label="Minimum fair odds" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
          <option value="any">Any odds</option>
          <option value="1.40">Min fair odds 1.40</option>
          <option value="1.70">Min fair odds 1.70</option>
          <option value="2.00">Min fair odds 2.00</option>
          <option value="2.50">Min fair odds 2.50</option>
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-1">
        {!isAny ? (
          <>
            <span className="text-xs text-muted-foreground">Mode</span>
            <button type="button" onClick={() => setMode('ranked')} className={cn('rounded-full border px-2.5 py-1 text-xs', mode !== 'strict' ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground')}>Ranked — all candidates</button>
            <button type="button" onClick={() => setMode('strict')} className={cn('rounded-full border px-2.5 py-1 text-xs', mode === 'strict' ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground')}>Strict checks only</button>
          </>
        ) : null}
        <span className="ml-auto text-xs text-muted-foreground">Counts follow the current league, mode and minimum odds.</span>
      </div>
      <p className="text-xs text-muted-foreground">
        Any bet defaults to minimum fair 1.70. Group and single-market views default to any odds; a
        numeric minimum still applies when selected. Ranked mode is a probability ranking; strict checks
        are optional and are not proof of profit.
      </p>

      {!dataReady ? (
        <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
          {roundState === 'error'
            ? 'Could not load the round data. Choose another round or try again.'
            : marketsState === 'error'
              ? 'Could not load the market data. The list needs league and bet metadata.'
              : 'Loading the round and market data…'}
        </p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            {isAny
              ? `${displayed.length} best ${displayed.length === 1 ? 'bet' : 'bets'} this round · ${betLabel} · ${leagueLabel} · ${minFair === 0 ? 'any odds' : `fair ≥ ${minFair.toFixed(2)}`}`
              : `${displayed.length} candidates this round · ${betLabel} · ${leagueLabel} · ${isStrict ? 'Strict checks only' : 'Ranked — all candidates'} · ${minFair === 0 ? 'any odds' : `fair ≥ ${minFair.toFixed(2)}`} · sorted by probability`}
            {activeKind === 'example' ? ' · Example round' : ''}
          </p>
          <p className="text-xs text-muted-foreground">
            Strong = probability ≥ 55%; Possible otherwise. Strong is a probability label, not a value
            or profit label.
          </p>
          <p className="text-sm">
            {settledPicks.length > 0 ? (
              <>Result: <span className="font-medium">{landedPicks} of {settledPicks.length} landed</span></>
            ) : (
              <span className="text-muted-foreground">Results pending</span>
            )}
          </p>
          {priceNote ? <p className="text-xs text-muted-foreground">{priceNote}</p> : null}

          {displayed.length === 0 ? (
            <div className="space-y-2">
              <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
                {baseFiltered.length === 0
                  ? `No ${betLabel} candidates for ${leagueLabel} in this round.`
                  : eligible.length === 0
                    ? minFair === 0
                      ? `No ${betLabel} candidates for ${leagueLabel} in this round.`
                      : bet.startsWith('group:')
                        ? `${baseCount} matches have ${betLabel} candidates, but none reach fair odds ≥ ${minFair.toFixed(2)}.`
                        : bet.startsWith('market:')
                          ? `${baseCount} fixtures have ${betLabel}, but none reach fair odds ≥ ${minFair.toFixed(2)}.`
                          : `${baseCount} candidates do not reach fair odds ≥ ${minFair.toFixed(2)}.`
                    : isAny
                      ? `0 of ${eligible.length} candidates passed the Any-bet rule.`
                      : isStrict
                        ? `0 of ${eligible.length} candidates passed the strict checks.`
                        : 'No candidates to display.'}
              </p>
              {eligible.length === 0 && baseFiltered.length > 0 && minFair > 0 ? (
                <button type="button" onClick={() => { minParamRef.current = true; setMinOdds('any'); }} className="rounded-md border px-2.5 py-1 text-xs">Show all odds</button>
              ) : null}
              {!isAny && isStrict && eligible.length > 0 ? (
                <p className="text-sm text-muted-foreground">
                  Ranked has {rankedDisplayed.length} {rankedDisplayed.length === 1 ? 'candidate' : 'candidates'} at these filters.{' '}
                  <button type="button" onClick={() => setMode('ranked')} className="underline underline-offset-2">Show ranked candidates</button>
                </p>
              ) : null}
              {failedCandidates.length > 0 ? (
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold">Highest-probability candidates that failed</h3>
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    {failedCandidates.map(({ item, failed }) => (
                      <li key={`${item.row.d}|${item.row.h}|${item.row.a}|${item.row.m}`} className="rounded-md border px-2 py-1">
                        <span className="font-medium text-foreground">{item.row.h} v {item.row.a}</span> · {markets[item.row.m]?.plain ?? item.row.m} · {pct(item.candidate.probability)}
                        {' — '}{failed.map((check) => `${check.label}: ${check.value}`).join('; ')}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : (
            <ul className="space-y-2">
              {displayed.map((item) => {
                const { row, price, candidate, checks } = item;
                const meta = markets[row.m];
                const key = `${row.h}|${row.a}|${row.m}`;
                const open = expanded === key;
                const checked = ticket.some((leg) => legKey(leg) === key);
                const strong = candidate.probability >= 0.55;
                const groupKey = bet.startsWith('group:') ? bet.slice(6) : null;
                const matchOptions = groupKey
                  ? activeEvaluated
                      .filter((option) =>
                        option.row.d === row.d && option.row.h === row.h && option.row.a === row.a
                        && (markets[option.row.m]?.group ?? '') === groupKey
                        && !isHiddenMarketId(option.row.m)
                        && option.candidate.fairOdds >= minFair
                        && (!isStrict || option.passed),
                      )
                      .sort((a, b) => b.candidate.probability - a.candidate.probability)
                  : [];
                const ladderRows = (data?.ladder ?? []).map((id) => (data?.rows ?? []).find((candidateRow) => candidateRow.h === row.h && candidateRow.a === row.a && candidateRow.m === id)).filter(Boolean) as RankRow[];
                return (
                  <li key={key} className="rounded-xl border p-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="text-muted-foreground">{row.k ?? ''}</span>
                          <span className="font-semibold">{row.h} <span className="text-muted-foreground">v</span> {row.a}</span>
                          <span className="text-xs text-muted-foreground">{leagueNames[row.d] ?? row.d}</span>
                          <Badge variant="secondary">{strong ? 'Strong' : 'Possible'}</Badge>
                          {isValue(item) ? <Badge variant="value">Value</Badge> : null}
                        </div>
                        <div className="mt-1 text-sm">
                          {meta?.plain ?? row.m} <span className="text-xs text-muted-foreground">({meta?.mozzart ?? ''})</span>
                        </div>
                      </div>
                      <div className="tabular text-right text-sm">
                        <div className="text-base font-semibold">{pct(candidate.probability)}</div>
                        <div className="text-xs text-muted-foreground">fair {candidate.fairOdds.toFixed(2)}</div>
                        {!isAny ? <div className="text-xs text-muted-foreground">lift {item.lift.toFixed(2)}× usual</div> : null}
                        <div className="text-xs text-muted-foreground">Play only at odds ≥ {item.minPlay.toFixed(2)}</div>
                      </div>
                    </div>

                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <StatusBadge status={row.st} />
                      {row.ht || row.ft ? <span className="tabular">HT {row.ht ?? '–'} · FT {row.ft ?? '–'}</span> : null}
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-1">
                      <button type="button" onClick={() => toggleLeg(row)} className={cn('ml-auto rounded-md border px-2.5 py-1 text-xs', checked ? 'border-primary bg-primary text-primary-foreground' : '')}>
                        {checked ? 'In ticket' : 'Add to ticket'}
                      </button>
                      <button type="button" onClick={() => setExpanded(open ? null : key)} aria-label="Details">
                        <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform', open && 'rotate-180')} />
                      </button>
                    </div>

                    {open ? (
                      <div className="mt-2 space-y-2 rounded-md bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                        {price ? <p>Mozzart {price.odds.toFixed(2)} ({utcTime(price.fetchedAt)})</p> : <p>{priceUnavailableText()}</p>}
                        <p>League usual {pct(row.lr)} (n={row.ln}) · lift {item.lift.toFixed(2)}× usual</p>
                        <p>Home at home {pct(row.hr)} (n={row.hn}) · away away {pct(row.ar)} (n={row.an}) · league usual {pct(row.lr)}</p>
                        <p>Model {pct(row.p)} · team empirical {pct(candidate.countsProbability ?? 0)} · agreement difference {pct(Math.abs(row.p - (candidate.countsProbability ?? 0)))}</p>
                        <p>Fair odds {candidate.fairOdds.toFixed(2)} · play only at odds ≥ {item.minPlay.toFixed(2)} · needs {(10 / item.minPlay).toFixed(1)} in 10 at that price; our chance {pct(candidate.probability)}</p>
                        <div>
                          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">{isAny ? 'Any-bet checks' : 'Strict checks'}</h4>
                          <ul className="space-y-0.5">
                            {checks.filter((check) => !check.flag).map((check) => (
                              <li key={check.id}>{check.label}: {check.passed ? 'Pass' : 'Does not pass'} — {check.value}</li>
                            ))}
                          </ul>
                        </div>
                        {groupKey && matchOptions.length > 0 ? (
                          <div>
                            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">{isStrict ? 'Strict-passing' : 'All'} {GROUP_LABEL[groupKey]} options for this match</h4>
                            <p className="text-xs font-medium text-foreground">
                              Highest-probability {groupKey} option for this match: {markets[matchOptions[0].row.m]?.plain ?? matchOptions[0].row.m} · {pct(matchOptions[0].candidate.probability)}
                            </p>
                            {matchOptions.length > 1 ? (
                              <>
                                <p className="mt-1 text-xs font-medium">Lower-probability alternatives</p>
                                <ul className="space-y-0.5">
                                  {matchOptions.slice(1).map((option) => (
                                    <li key={option.row.m} className="flex justify-between gap-2">
                                      <span>{markets[option.row.m]?.plain ?? option.row.m}</span>
                                      <span className="tabular">{pct(option.candidate.probability)} · fair {option.candidate.fairOdds.toFixed(2)} · {option.candidate.probability >= 0.55 ? 'Strong' : 'Possible'}</span>
                                    </li>
                                  ))}
                                </ul>
                              </>
                            ) : null}
                          </div>
                        ) : null}
                        <div>
                          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">Goal ladder</h4>
                          <ul className="grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
                            {ladderRows.map((line) => (
                              <li key={line.m} className={cn('flex justify-between gap-2', line.m === row.m && 'font-medium text-foreground')}>
                                <span>{LADDER_LABELS[line.m] ?? line.m}</span>
                                <span className="tabular">{pct(pcOf(line))} · {(1 / Math.max(pcOf(line), 1e-4)).toFixed(2)}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <MatchStats date={activeDate} div={row.d} home={row.h} away={row.a} />
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}

      <section className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Target tickets</h2>
          <button type="button" onClick={() => setValueOnly(!valueOnly)} className={cn('rounded-full border px-2.5 py-1 text-xs', valueOnly ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground')}>
            Value legs only
          </button>
        </div>
        <p className="text-sm text-muted-foreground">
          Built only from passing picks, one leg per match{valueOnly ? ' that is a Value bet' : ''}.
        </p>
        {targetTickets.some((entry) => entry.ticket) ? (
          <ul className="grid gap-2 sm:grid-cols-3">
            {targetTickets.map(({ target, ticket: suggestion }) => (
              <li key={target} className="rounded-xl border p-3 text-sm">
                {suggestion ? (
                  <>
                    <div className="flex justify-between"><span className="font-semibold">Target {target.toFixed(2)}</span><span className="tabular">{pct(suggestion.probability)}</span></div>
                    <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                      {suggestion.legs.map((leg) => <li key={legKey(leg)} className="truncate">{leg.h} v {leg.a} · {leg.label} · {pct(leg.pc)}</li>)}
                    </ul>
                    <div className="mt-1 text-xs text-muted-foreground">fair {suggestion.fair.toFixed(2)} · min play {(combinedMinPlay(suggestion.legs) ?? 0).toFixed(2)}</div>
                    <button type="button" onClick={() => setTicket(suggestion.legs)} className="mt-2 rounded-md border px-2.5 py-1 text-xs">Add to my ticket</button>
                  </>
                ) : <p className="text-xs text-muted-foreground">No passing ticket reaches {target.toFixed(2)}.</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-xl border border-dashed px-4 py-4 text-sm text-muted-foreground">
            {valueOnly ? 'No target ticket from Value legs this round.' : 'No target ticket reaches these targets.'}
          </p>
        )}
      </section>

      {ticket.length > 0 ? (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/95 backdrop-blur">
          <div className="mx-auto max-w-5xl px-4 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button type="button" onClick={() => setTicketOpen(!ticketOpen)} className="text-sm font-medium">My ticket · {ticket.length} legs · {pct(ticketProbability)}</button>
              <div className="flex gap-2">
                <button type="button" onClick={() => setTicketOpen(!ticketOpen)} className="rounded-md border px-2.5 py-1 text-xs">{ticketOpen ? 'Hide' : 'View'}</button>
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
                {correlated ? <p className="text-sm text-muted-foreground">Same-match legs are correlated; combined % is not reliable.</p> : null}
                <div className="grid gap-2 text-sm sm:grid-cols-4">
                  <label className="flex flex-col gap-1">Bonus %
                    <input type="number" value={bonus} onChange={(event) => setBonus(Number(event.target.value) || 0)} className="w-full rounded-md border bg-background px-2 py-1" />
                  </label>
                  <label className="flex flex-col gap-1">Stake
                    <input type="number" value={stake} onChange={(event) => setStake(Number(event.target.value) || 0)} className="w-full rounded-md border bg-background px-2 py-1" />
                  </label>
                  <div>Combined %<div className="tabular font-medium">{pct(ticketProbability)}</div></div>
                  <div>Fair odds<div className="tabular font-medium">{ticketFair.toFixed(2)}</div></div>
                  <div>Min play<div className="tabular font-medium">{ticketMinPlay === null ? '–' : ticketMinPlay.toFixed(2)}</div></div>
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

      <nav className="flex flex-wrap gap-3 border-t pt-3 text-xs text-muted-foreground">
        <a className="underline underline-offset-2" href="/leagues">Leagues</a>
        <a className="underline underline-offset-2" href="/record">Record</a>
        <a className="underline underline-offset-2" href="/report">Report</a>
        <a className="underline underline-offset-2" href="/rounds">Rounds</a>
        <a className="underline underline-offset-2" href="/tickets">Tickets</a>
      </nav>
    </div>
  );
}
