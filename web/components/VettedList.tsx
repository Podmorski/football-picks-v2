'use client';

import { useEffect, useMemo, useState } from 'react';
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
import { addTicket, combinedFair, combinedMozzart, combinedProbability, legKey, payout, sameMatchWarning, type TicketLeg } from '@/lib/ticket';
import { optimiseTickets } from '@/lib/ticketOpt';
import {
  BAND_OPTIONS,
  DAILY_LIMIT,
  DEFAULT_BAND,
  REFINEMENTS,
  applyRefinement,
  decodeRankRows,
  legacyMinToBand,
  parseBand,
  parseRefinement,
  selectDaily,
  selectGroupRows,
  selectMarketRows,
  visibleDailyRows,
} from '@/lib/dailyBest';
import { breakEvenChance, evaluateRows, expectedReturn, isHiddenMarketId, pcOf, type Evaluated } from '@/lib/vetted';
import { minPlay } from '@/lib/vetting';
import type { DailyBestPrivateFile, MarketMeta, RankRow } from '@/lib/types';

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

// A dashboard row with flattened identity so the pure Daily-best helpers can
// rank it without knowing about the evaluation wrapper.
type PickItem = Evaluated & {
  d: string;
  h: string;
  a: string;
  m: string;
  pc: number;
  odds: number | null;
  st?: string;
};
type PricedItem = PickItem & { odds: number };

function bandLabelOf(band: ReturnType<typeof parseBand>): string {
  if (band.all) return 'All 1.20+';
  return band.max === null ? `${band.min.toFixed(2)}+` : `${band.min.toFixed(2)}–${band.max.toFixed(2)}`;
}

function identityOf(item: { d: string; h: string; a: string; m: string }): string {
  return `${item.d}|${item.h}|${item.a}|${item.m}`;
}

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
  const [dailyBest, setDailyBest] = useState<DailyBestPrivateFile | null>(null);
  const [dailyBestState, setDailyBestState] = useState<'loading' | 'ready' | 'unpriced' | 'error'>('loading');
  const [league, setLeague] = useParam('league', 'all');
  const [bet, setBet] = useParam('bet', 'any');
  const [bandParam, setBandParam] = useParam('band', '');
  const [minParam, setMinParam] = useParam('min', '');
  const [refineParam, setRefineParam] = useParam('refine', '');
  const [showParam, setShowParam] = useParam('show', '');
  const [roundParam, setRound] = useParam('round', date);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [ticket, setTicket] = useState<TicketLeg[]>([]);
  const [bonus, setBonus] = useState(0);
  const [stake, setStake] = useState(10);
  const [ticketOpen, setTicketOpen] = useState(false);

  const activeDate = /^\d{4}-\d{2}-\d{2}$/.test(roundParam) ? roundParam : date;
  const activeMeta = roundMeta[activeDate] ?? { label: activeDate, kind };
  const activeKind = activeMeta.kind;

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
          setData({ rows: decodeRankRows(payload), ladder: (payload.ladder as string[]) ?? [] });
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

  useEffect(() => {
    let cancelled = false;
    setDailyBestState('loading');
    fetch('/data/daily-best-private.json')
      .then(async (response) => {
        if (response.status === 404) {
          if (!cancelled) { setDailyBest(null); setDailyBestState('unpriced'); }
          return;
        }
        if (!response.ok) throw new Error('daily-best');
        const payload = (await response.json()) as DailyBestPrivateFile;
        if (!cancelled) { setDailyBest(payload); setDailyBestState('ready'); }
      })
      .catch(() => { if (!cancelled) setDailyBestState('error'); });
    return () => { cancelled = true; };
  }, []);

  const leagueNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const [code, name] of leagueOptions) map[code] = name;
    return map;
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
  const groupKey = bet.startsWith('group:') ? bet.slice(6) : null;
  const marketId = bet.startsWith('market:') ? bet.slice(7) : null;

  // An explicit `?band=` wins. Legacy `?min=` links are read as an actual-odds
  // floor (`min=1.70` -> `1.70+`, `min=any` -> `all`).
  const effectiveBandToken = bandParam || legacyMinToBand(minParam) || DEFAULT_BAND;
  const band = useMemo(() => parseBand(effectiveBandToken), [effectiveBandToken]);
  const refinement = parseRefinement(refineParam);

  function dropParams(keys: string[]) {
    const params = new URLSearchParams(window.location.search);
    for (const key of keys) params.delete(key);
    const query = params.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`);
  }
  function chooseBand(next: string) {
    setBandParam(next);
    dropParams(['min']);
  }
  function clearShow() {
    setShowParam('');
    dropParams(['show']);
  }
  function resetAll() {
    setLeague('all');
    setBet('any');
    setBandParam('');
    setMinParam('');
    setRefineParam('');
    setShowParam('');
    setRound(date);
    dropParams(['band', 'min', 'refine', 'show']);
  }

  const activeEvaluated = useMemo<PickItem[]>(() => {
    const rows = data?.rows ?? [];
    return evaluateRows(rows, (row) => priceIndex[priceKey(row.d, row.h, row.a, row.m)], 'any').map((item) => ({
      ...item,
      d: item.row.d,
      h: item.row.h,
      a: item.row.a,
      m: item.row.m,
      pc: item.candidate.probability,
      odds: item.price?.odds ?? null,
      st: item.row.st,
    }));
  }, [data, priceIndex]);

  const roundRows = useMemo(() => activeEvaluated.filter((item) => !isHiddenMarketId(item.m)), [activeEvaluated]);
  const leagueScoped = useMemo(
    () => roundRows.filter((item) => league === 'all' || item.d === league),
    [roundRows, league],
  );
  const dataReady = roundState === 'ready' && marketsState === 'ready';
  const countsReady = dataReady;

  // Daily best is one row per fixture: prefer the highest pc inside the actual
  // odds band, otherwise fill with the nearest band candidate.
  const daily = useMemo(() => selectDaily(leagueScoped, band), [leagueScoped, band]);
  const showAll = isAny && league !== 'all' && showParam === 'all';
  const interactiveDaily = useMemo<PricedItem[]>(
    () => visibleDailyRows(daily, showAll),
    [daily, showAll],
  );

  // The forward record covers exactly All leagues + the default 1.70-2.30 band.
  // When the private frozen file exists, this exact ordered list is displayed.
  const isDefaultView = isAny && league === 'all' && band.token === DEFAULT_BAND;
  const frozenRound = useMemo(
    () => dailyBest?.rounds.find((round) => round.round_date === activeDate) ?? null,
    [dailyBest, activeDate],
  );
  const frozenDefault = isDefaultView && frozenRound !== null;
  const frozenItems = useMemo<PricedItem[]>(() => {
    if (!frozenRound) return [];
    const byKey = new Map(activeEvaluated.map((item) => [identityOf(item), item]));
    const fetchedAt = frozenRound.snapshot_identity?.fetched_at ?? snapshot?.fetched_at ?? '';
    const items: PricedItem[] = [];
    for (const frozen of frozenRound.rows) {
      const base = byKey.get(identityOf(frozen));
      if (!base) continue;
      items.push({
        ...base,
        pc: frozen.pc,
        candidate: { ...base.candidate, probability: frozen.pc, fairOdds: 1 / Math.max(frozen.pc, 0.0001) },
        odds: frozen.odds,
        price: { odds: frozen.odds, fetchedAt },
      });
    }
    return items;
  }, [frozenRound, activeEvaluated, snapshot]);

  // Group and exact-market views leave the curated Daily-best algorithm. They
  // apply no probability, price or band gate; refinements are opt-in only.
  const marketBase = useMemo(() => {
    if (isAny) return [];
    const scoped = leagueScoped.filter((item) => {
      if (groupKey) return (markets[item.m]?.group ?? '') === groupKey;
      if (marketId) return item.m === marketId;
      return false;
    });
    return groupKey ? selectGroupRows(scoped) : selectMarketRows(scoped);
  }, [isAny, leagueScoped, groupKey, marketId, markets]);
  const refined = useMemo(() => applyRefinement(marketBase, refinement), [marketBase, refinement]);
  const displayed = useMemo<PickItem[]>(
    () => (frozenDefault ? frozenItems : isAny ? interactiveDaily : refined.rows),
    [frozenDefault, frozenItems, isAny, interactiveDaily, refined],
  );

  // League options: every division with fixtures in the active round stays
  // selectable even when its preferred-band count is zero.
  const roundDivisions = useMemo(() => {
    const present = new Set<string>();
    for (const item of roundRows) present.add(item.d);
    return [...present].sort((a, b) => (leagueNames[a] ?? a).localeCompare(leagueNames[b] ?? b));
  }, [roundRows, leagueNames]);
  const countries = useMemo(() => {
    const present = new Set(roundDivisions);
    if (league !== 'all' && !present.has(league)) present.add(league);
    const meta = new Map<string, { name: string; country: string }>();
    for (const [code, name, country] of leagueOptions) meta.set(code, { name, country });
    const groups = new Map<string, [string, string][]>();
    for (const code of [...present].sort((a, b) => (meta.get(a)?.name ?? a).localeCompare(meta.get(b)?.name ?? b))) {
      const entry = meta.get(code);
      const country = entry?.country ?? 'Other';
      if (!groups.has(country)) groups.set(country, []);
      groups.get(country)?.push([code, entry?.name ?? code]);
    }
    return [...groups.entries()];
  }, [leagueOptions, roundDivisions, league]);

  // Daily counts per league: in-band fixtures over all fixtures in that league.
  // Group and exact-market counts are fixtures with at least one row in the mode.
  const leagueCounts = useMemo(() => {
    const map = new Map<string, { inBand: number; total: number }>();
    if (isAny) {
      const byDivision = new Map<string, PickItem[]>();
      for (const item of roundRows) {
        if (!byDivision.has(item.d)) byDivision.set(item.d, []);
        byDivision.get(item.d)?.push(item);
      }
      for (const [code, list] of byDivision) {
        map.set(code, {
          inBand: selectDaily(list, band).inBandFixtures,
          total: new Set(list.map((item) => `${item.h}|${item.a}`)).size,
        });
      }
    } else {
      const fixtures = new Map<string, Set<string>>();
      for (const item of roundRows) {
        const matches = groupKey
          ? (markets[item.m]?.group ?? '') === groupKey
          : marketId !== null && item.m === marketId;
        if (!matches) continue;
        if (!fixtures.has(item.d)) fixtures.set(item.d, new Set());
        fixtures.get(item.d)?.add(`${item.h}|${item.a}`);
      }
      for (const [code, set] of fixtures) map.set(code, { inBand: 0, total: set.size });
    }
    return map;
  }, [isAny, roundRows, band, groupKey, marketId, markets]);

  const counts = useMemo(() => {
    const groupMatches = new Map<string, Set<string>>();
    const marketMatches = new Map<string, Set<string>>();
    for (const item of leagueScoped) {
      const group = markets[item.m]?.group;
      if (!group) continue;
      const key = `${item.d}|${item.h}|${item.a}`;
      if (!groupMatches.has(group)) groupMatches.set(group, new Set());
      groupMatches.get(group)?.add(key);
      if (!marketMatches.has(item.m)) marketMatches.set(item.m, new Set());
      marketMatches.get(item.m)?.add(key);
    }
    return { groups: groupMatches, markets: marketMatches };
  }, [leagueScoped, markets]);

  const leagueLabel = league === 'all' ? 'any league' : (leagueNames[league] ?? league);
  const betLabel = isAny ? 'Daily best' : groupKey ? (GROUP_LABEL[groupKey] ?? 'group') : (markets[marketId ?? '']?.plain ?? 'market');
  const bandLabel = bandLabelOf(band);
  const roundFixtureCount = new Set(roundRows.map((item) => `${item.d}|${item.h}|${item.a}`)).size;
  const leagueHasFixtures = league === 'all' ? roundFixtureCount > 0 : roundRows.some((item) => item.d === league);
  const marketUnavailable = marketId !== null && marketsState === 'ready' && !markets[marketId];
  const pricedInLeague = leagueScoped.filter((item) => item.odds !== null).length;
  const refinementOnly = !isAny && displayed.length === 0 && marketBase.length > 0 && refinement !== 'all';

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

  function dailyEmptyText(): string {
    if (!leagueHasFixtures) return `No fixtures for ${leagueLabel} in this round.`;
    if (pricesState === 'loading') return 'Loading Mozzart prices…';
    if (pricesState === 'error') return 'Mozzart prices could not be loaded, so Daily best cannot rank games.';
    if (pricesState === 'unpriced') return 'Daily best needs frozen Mozzart prices. This build is unpriced.';
    if (!snapshot) return 'No Mozzart snapshot for this round.';
    if (pricedInLeague === 0) return 'No Mozzart price for this league in this round.';
    return 'No priced candidate has a model probability strictly between 0% and 100% at odds of 1.20 or more.';
  }

  function toLeg(row: RankRow, oddsOverride?: number | null, pcOverride?: number): TicketLeg {
    const meta = markets[row.m];
    const price = priceIndex[priceKey(row.d, row.h, row.a, row.m)];
    const fixture = snapshot?.fixtures.find((item) => item.div === row.d && item.home === row.h && item.away === row.a);
    const probability = pcOverride ?? pcOf(row);
    const odds = oddsOverride === undefined ? price?.odds ?? null : oddsOverride;
    const fetchedAt = oddsOverride === undefined ? price?.fetchedAt : snapshot?.fetched_at;
    return {
      d: row.d, h: row.h, a: row.a, m: row.m, label: meta?.plain ?? row.m, mozzart: meta?.mozzart ?? '',
      pc: probability, fair: 1 / Math.max(probability, 0.0001), minPlay: minPlay(probability), odds,
      fetchedAt, kickoff: fixture?.kickoff ?? null, st: row.st, ht: row.ht, ft: row.ft,
    };
  }
  function toggleLeg(row: RankRow, oddsOverride?: number | null, pcOverride?: number) {
    const key = legKey(row);
    setTicket((current) => current.some((leg) => legKey(leg) === key) ? current.filter((leg) => legKey(leg) !== key) : [...current, toLeg(row, oddsOverride, pcOverride)]);
  }
  function saveCurrent() {
    if (ticket.length === 0) return;
    addTicket({ id: `${Date.now()}`, date: activeDate, legs: ticket, bonus, stake, savedAt: new Date().toISOString() });
    setTicket([]);
    setTicketOpen(false);
  }

  const targetTickets = useMemo(() => {
    const legs = displayed.map((item) => toLeg(item.row, item.odds, item.pc));
    if (legs.length === 0) return [];
    return TARGETS.map((target) => ({ target, ticket: optimiseTickets(legs, target, 5, 1, 1.0)[0] ?? null }));
  }, [displayed, markets, priceIndex, snapshot]);

  const settledPicks = displayed.filter((item) => item.row.st === 'landed' || item.row.st === 'lost');
  const landedPicks = settledPicks.filter((item) => item.row.st === 'landed').length;
  const ticketProbability = combinedProbability(ticket);
  const ticketFair = combinedFair(ticket);
  const ticketMozzart = combinedMozzart(ticket);
  const ticketPayout = payout(stake, ticket, bonus);
  const correlated = sameMatchWarning(ticket);

  function summaryLine(): string {
    if (isAny) {
      const mode = frozenDefault ? 'Frozen Daily-best-v1' : isDefaultView ? 'Daily best preview' : 'Daily best exploration';
      return `${displayed.length} game${displayed.length === 1 ? '' : 's'} · ${mode} · ${leagueLabel} · actual odds ${bandLabel}`;
    }
    const base = `${betLabel} · ${leagueLabel} · exploration · sorted by model probability`;
    if (refined.hidden > 0) return `${displayed.length} of ${marketBase.length} fixtures · ${base} · optional refinement hides ${refined.hidden}`;
    return `${displayed.length} fixture${displayed.length === 1 ? '' : 's'} · ${base}`;
  }

  const shortList = !frozenDefault && isAny && daily.rows.length > 0 && daily.rows.length < DAILY_LIMIT;

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
              {leagues.map(([code, name]) => {
                const count = leagueCounts.get(code);
                const label = !count
                  ? name
                  : isAny
                    ? `${name} (${count.inBand} in band / ${count.total} fixtures)`
                    : `${name} (${count.total} fixtures)`;
                return <option key={code} value={code}>{label}</option>;
              })}
            </optgroup>
          ))}
        </select>
        <select value={bet} onChange={(event) => setBet(event.target.value)} aria-label="Bet" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
          <option value="any">Daily best</option>
          {GROUP_ORDER.map((group) => (
            <optgroup key={group} label={GROUP_LABEL[group]}>
              <option value={`group:${group}`}>{GROUP_LABEL[group]} ({countsReady ? (counts.groups.get(group)?.size ?? 0) : '…'} fixtures)</option>
              {(marketGroups.get(group) ?? []).map((market) => (
                <option key={market.id} value={`market:${market.id}`}>{market.plain} ({countsReady ? (counts.markets.get(market.id)?.size ?? 0) : '…'} fixtures)</option>
              ))}
            </optgroup>
          ))}
        </select>
        {isAny ? (
          <select value={band.token} onChange={(event) => chooseBand(event.target.value)} aria-label="Daily-best actual-odds band" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
            {BAND_OPTIONS.map((option) => <option key={option.token} value={option.token}>{option.label}</option>)}
            {!BAND_OPTIONS.some((option) => option.token === band.token) ? <option value={band.token}>{bandLabel}</option> : null}
          </select>
        ) : (
          <select value={refinement} onChange={(event) => setRefineParam(event.target.value)} aria-label="Optional refinement" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
            {REFINEMENTS.map((option) => <option key={option.token} value={option.token}>{option.label}</option>)}
          </select>
        )}
        <button type="button" onClick={resetAll} className="w-full rounded-md border px-2 py-1.5 text-sm">Reset</button>
      </div>

      <p className="text-xs text-muted-foreground">
        Daily best needs an actual Mozzart price: one pick per fixture, actual odds at least 1.20, preferring the
        selected band. League, market group and exact-market choices leave the curated algorithm and apply no
        probability, vetting or odds gate. Legacy ?min= links map to an actual-odds floor: 1.70 becomes 1.70+,
        any becomes All 1.20+.
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
          <p className="text-sm text-muted-foreground">{summaryLine()}</p>
          {frozenDefault ? (
            <p className="text-xs text-muted-foreground">Frozen Daily-best-v1 list — this exact ordered list is measured by the forward record.</p>
          ) : isDefaultView ? (
            <p className="text-xs text-muted-foreground">
              {dailyBestState === 'loading'
                ? 'Loading frozen Daily-best data…'
                : dailyBestState === 'error'
                  ? 'Frozen Daily-best data could not be loaded.'
                  : dailyBestState === 'unpriced'
                    ? 'Frozen Daily-best data is not embedded in this build.'
                    : dailyBest?.activation && activeDate >= dailyBest.activation.activated_round
                      ? 'Frozen Daily-best-v1 data is unavailable for this round.'
                      : 'Pre-activation preview; not part of the forward record.'}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">Exploration view — not part of the frozen Daily-best record.</p>
          )}
          {isAny ? (
            <p className="text-sm text-muted-foreground">
              {frozenDefault && frozenRound ? (
                <>
                  Showing {displayed.length} of {frozenRound.eligible_counts.fixtures} eligible fixtures ·{' '}
                  {frozenRound.eligible_counts.in_band} in band · {frozenRound.fallback_selected} filled from outside the band
                  (nearest first) · frozen order
                </>
              ) : (
                <>
                  Showing {interactiveDaily.length} of {daily.eligibleFixtures} eligible fixtures · {daily.inBandFixtures} have a
                  candidate in {bandLabel} · {daily.outside.length} filled from outside the band (nearest first) · one market per fixture
                </>
              )}
            </p>
          ) : null}
          <p className="text-sm">
            {settledPicks.length > 0 ? (
              <>Result: <span className="font-medium">{landedPicks} of {settledPicks.length} landed</span></>
            ) : (
              <span className="text-muted-foreground">Results pending</span>
            )}
          </p>
          {priceNote ? <p className="text-xs text-muted-foreground">{priceNote}</p> : null}

          {!frozenDefault && isAny && daily.rows.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              {shortList ? (
                <span className="text-muted-foreground">
                  Only {daily.rows.length} eligible fixture{daily.rows.length === 1 ? '' : 's'} for this round and league;
                  the list is not padded with sub-1.20 odds or a second market from the same fixture.
                </span>
              ) : null}
              {league !== 'all' && daily.rows.length > DAILY_LIMIT ? (
                showAll ? (
                  <button type="button" onClick={clearShow} className="rounded-md border px-2.5 py-1">Show top {DAILY_LIMIT}</button>
                ) : (
                  <button type="button" onClick={() => setShowParam('all')} className="rounded-md border px-2.5 py-1">Show all eligible games ({daily.rows.length})</button>
                )
              ) : null}
            </div>
          ) : null}

          {isAny && displayed.length === 0 ? (
            <div className="space-y-2">
              <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
                {frozenDefault
                  ? 'The frozen Daily-best-v1 list is empty for this round; it is not padded.'
                  : dailyEmptyText()}
              </p>
              {!frozenDefault && daily.rejected > 0 ? (
                <p className="text-xs text-muted-foreground">
                  {daily.rejected} priced candidate{daily.rejected === 1 ? '' : 's'} were below the 1.20 floor or outside
                  0 &lt; pc &lt; 1 and are not shown.
                </p>
              ) : null}
            </div>
          ) : null}

          {!isAny && displayed.length === 0 ? (
            <div className="space-y-2">
              {marketUnavailable ? (
                <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
                  This market is not in the production market data.
                </p>
              ) : !leagueHasFixtures ? (
                <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
                  No fixtures for {leagueLabel} in this round.
                </p>
              ) : marketBase.length === 0 ? (
                <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
                  No {betLabel} rows in this round&apos;s data. The round file may not carry every market.
                </p>
              ) : (
                <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
                  The optional refinement hides all {marketBase.length} rows. Nothing is missing from the market itself.
                </p>
              )}
              {refinement !== 'all' && marketBase.length > 0 ? (
                <button type="button" onClick={() => setRefineParam('all')} className="rounded-md border px-2.5 py-1 text-xs">
                  Show all {marketBase.length}
                </button>
              ) : null}
            </div>
          ) : null}

          {!isAny && displayed.length > 0 && refined.hidden > 0 ? (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-muted-foreground">The optional refinement hides {refined.hidden} of {marketBase.length} rows.</span>
              <button type="button" onClick={() => setRefineParam('all')} className="rounded-md border px-2.5 py-1">Show all</button>
            </div>
          ) : null}

          {displayed.length > 0 ? (
            <ul className="space-y-2">
              {displayed.map((item) => {
                const { row, price, candidate } = item;
                const meta = markets[row.m];
                const key = identityOf(item);
                const open = expanded === key;
                const checked = ticket.some((leg) => legKey(leg) === key);
                const matchOptions = groupKey
                  ? activeEvaluated
                      .filter((option) =>
                        option.d === row.d && option.h === row.h && option.a === row.a
                        && !isHiddenMarketId(option.m)
                        && (markets[option.m]?.group ?? '') === groupKey,
                      )
                      .sort((a, b) => b.pc - a.pc || identityOf(a).localeCompare(identityOf(b)))
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
                        </div>
                        <div className="mt-1 text-sm">
                          {meta?.plain ?? row.m} <span className="text-xs text-muted-foreground">({meta?.mozzart ?? ''})</span>
                        </div>
                      </div>
                      <div className="tabular text-right text-sm">
                        <div className="text-base font-semibold">{pct(candidate.probability)}</div>
                        <div className="text-xs text-muted-foreground">fair {candidate.fairOdds.toFixed(2)}</div>
                      </div>
                    </div>

                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <StatusBadge status={row.st} />
                      {item.odds !== null ? (
                        <span className="tabular">
                          Actual {item.odds.toFixed(2)} · break-even {(breakEvenChance(item.odds) * 100).toFixed(1)}% ·
                          model return {signedPct(expectedReturn(candidate.probability, item.odds) * 100)}
                        </span>
                      ) : (
                        <span>No actual price · no actual-EV claim</span>
                      )}
                      {row.ht || row.ft ? <span className="tabular">HT {row.ht ?? '–'} · FT {row.ft ?? '–'}</span> : null}
                    </div>

                    <div className="mt-2 flex flex-wrap items-center gap-1">
                      <button type="button" onClick={() => toggleLeg(row, item.odds, item.pc)} className={cn('ml-auto rounded-md border px-2.5 py-1 text-xs', checked ? 'border-primary bg-primary text-primary-foreground' : '')}>
                        {checked ? 'In ticket' : 'Add to ticket'}
                      </button>
                      <button type="button" onClick={() => setExpanded(open ? null : key)} aria-label="Details">
                        <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform', open && 'rotate-180')} />
                      </button>
                    </div>

                    {open ? (
                      <div className="mt-2 space-y-2 rounded-md bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                        {price ? (
                          <div className="space-y-0.5">
                            <p>Mozzart {price.odds.toFixed(2)} ({utcTime(price.fetchedAt)})</p>
                            <p>
                              Model chance {pct(candidate.probability)} · offered odds {price.odds.toFixed(2)} · break-even
                              chance {(breakEvenChance(price.odds) * 100).toFixed(1)}% · model expected return{' '}
                              {signedPct(expectedReturn(candidate.probability, price.odds) * 100)}
                            </p>
                            <p className="text-xs">Arithmetic at the offered price only; no positive-edge claim.</p>
                          </div>
                        ) : <p>{priceUnavailableText()}</p>}
                        <p>League usual {pct(row.lr)} (n={row.ln}) · lift {item.lift.toFixed(2)}× usual</p>
                        <p>Home at home {pct(row.hr)} (n={row.hn}) · away away {pct(row.ar)} (n={row.an}) · league usual {pct(row.lr)}</p>
                        <p>Model {pct(row.p)} · team empirical {pct(candidate.countsProbability ?? 0)} · agreement difference {pct(Math.abs(row.p - (candidate.countsProbability ?? 0)))}</p>
                        <p>Fair odds {candidate.fairOdds.toFixed(2)}</p>
                        {groupKey && matchOptions.length > 0 ? (
                          <div>
                            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">All {GROUP_LABEL[groupKey]} options for this match</h4>
                            <p className="text-xs font-medium text-foreground">
                              Highest model probability: {markets[matchOptions[0].m]?.plain ?? matchOptions[0].m} · {pct(matchOptions[0].pc)}
                            </p>
                            <ul className="space-y-0.5">
                              {matchOptions.map((option) => (
                                <li key={option.m} className={cn('flex justify-between gap-2', option.m === row.m && 'font-medium text-foreground')}>
                                  <span>{markets[option.m]?.plain ?? option.m}</span>
                                  <span className="tabular">
                                    {pct(option.pc)} · fair {option.candidate.fairOdds.toFixed(2)}
                                    {option.odds !== null ? ` · actual ${option.odds.toFixed(2)}` : ''}
                                  </span>
                                </li>
                              ))}
                            </ul>
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
          ) : null}
        </>
      )}

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Target tickets</h2>
        <p className="text-sm text-muted-foreground">
          Built only from the displayed candidates, one leg per match.
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
                    <div className="mt-1 text-xs text-muted-foreground">fair {suggestion.fair.toFixed(2)}</div>
                    <button type="button" onClick={() => setTicket(suggestion.legs)} className="mt-2 rounded-md border px-2.5 py-1 text-xs">Add to my ticket</button>
                  </>
                ) : <p className="text-xs text-muted-foreground">No displayed ticket reaches {target.toFixed(2)}.</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-xl border border-dashed px-4 py-4 text-sm text-muted-foreground">
            No target ticket reaches these targets.
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
                  <div>Mozzart<div className="tabular font-medium">{ticketMozzart === null ? 'incomplete' : ticketMozzart.toFixed(2)}</div></div>
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
        <a className="underline underline-offset-2" href="/how-it-works">How it works</a>
      </nav>
    </div>
  );
}
