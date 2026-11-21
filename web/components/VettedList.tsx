'use client';

import { useEffect, useMemo, useState } from 'react';
import { Check, ChevronDown, Minus, X } from 'lucide-react';

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
import { addTicket, combinedFair, combinedMozzart, combinedProbability, legKey, payout, sameMatchWarning, ticketVsFair, type TicketLeg } from '@/lib/ticket';
import { optimiseTickets } from '@/lib/ticketOpt';
import { evaluateRows, pcOf, selectPassing, type Evaluated } from '@/lib/vetted';
import type { VettingCheck } from '@/lib/vetting';
import type { MarketMeta, RankRow } from '@/lib/types';

const GROUP_ORDER = ['Combos', 'HT/FT', 'Goals', 'BTTS', 'Half-time', 'Team goals', 'Result & double chance', 'Correct score'];
const GROUP_LABEL: Record<string, string> = {
  Combos: 'All combos', 'HT/FT': 'All HT/FT', Goals: 'All goals', BTTS: 'All BTTS',
  'Half-time': 'All half-time', 'Team goals': 'All team goals',
  'Result & double chance': 'All result & double chance', 'Correct score': 'All correct score',
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
  date, kind, leagueOptions, roundOptions = [],
}: {
  date: string; kind: string; leagueOptions: [string, string, string][]; roundOptions?: [string, string][];
}) {
  const [data, setData] = useState<{ rows: RankRow[]; ladder: string[] } | null>(null);
  const [markets, setMarkets] = useState<Record<string, MarketMeta>>({});
  const [prices, setPrices] = useState<MozzartPricesFile | null>(null);
  const [league, setLeague] = useParam('league', 'all');
  const [bet, setBet] = useParam('bet', 'any');
  const [minOdds, setMinOdds] = useParam('min', '1.70');
  const [roundParam, setRound] = useParam('round', date);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [ticket, setTicket] = useState<TicketLeg[]>([]);
  const [bonus, setBonus] = useState(0);
  const [stake, setStake] = useState(10);
  const [ticketOpen, setTicketOpen] = useState(false);

  const activeDate = /^\d{4}-\d{2}-\d{2}$/.test(roundParam) ? roundParam : date;

  useEffect(() => {
    let cancelled = false;
    setData(null);
    (async () => {
      for (const url of [`/data/rounds/${activeDate}.full.json`, `/data/rounds/${activeDate}.json`]) {
        const response = await fetch(url);
        if (!response.ok) continue;
        const payload = (await response.json()) as Record<string, unknown>;
        if (!cancelled) setData({ rows: decodeRows(payload), ladder: (payload.ladder as string[]) ?? [] });
        return;
      }
      if (!cancelled) setData({ rows: [], ladder: [] });
    })().catch(() => { if (!cancelled) setData({ rows: [], ladder: [] }); });
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

  const evaluated = useMemo<EvaluatedRow[]>(() => {
    return evaluateRows(data?.rows ?? [], (row) => priceIndex[priceKey(row.d, row.h, row.a, row.m)]);
  }, [data, priceIndex]);

  const betMatches = (row: RankRow) => {
    if (bet === 'any') return true;
    if (bet.startsWith('group:')) return (markets[row.m]?.group ?? '') === bet.slice(6);
    return row.m === bet.slice(7);
  };
  const baseFiltered = evaluated.filter((item) => (league === 'all' || item.row.d === league) && betMatches(item.row));
  const minFair = Number(minOdds) || 1.70;

  const passing = useMemo(() => {
    return selectPassing(baseFiltered, { minFair, mozzartOnly: false });
  }, [baseFiltered, minFair]);

  const closest = useMemo(() => {
    if (passing.length > 0) return [];
    const seen = new Set<string>();
    const rows: { item: EvaluatedRow; failed: VettingCheck[] }[] = [];
    for (const item of [...baseFiltered].sort((a, b) => b.candidate.probability - a.candidate.probability)) {
      const key = `${item.row.h}|${item.row.a}`;
      if (seen.has(key)) continue;
      const failed = item.checks.filter((check) => !check.flag && !check.passed);
      if (failed.length === 0) continue;
      seen.add(key);
      rows.push({ item, failed });
      if (rows.length >= 3) break;
    }
    return rows;
  }, [baseFiltered, passing]);

  function toLeg(row: RankRow): TicketLeg {
    const meta = markets[row.m];
    const price = priceIndex[priceKey(row.d, row.h, row.a, row.m)];
    const fixture = snapshot?.fixtures.find((item) => item.div === row.d && item.home === row.h && item.away === row.a);
    const probability = pcOf(row);
    return {
      d: row.d, h: row.h, a: row.a, m: row.m, label: meta?.plain ?? row.m, mozzart: meta?.mozzart ?? '',
      pc: probability, fair: 1 / Math.max(probability, 0.0001), odds: price?.odds ?? null,
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
    const legs = passing.map((item) => toLeg(item.row));
    if (legs.length === 0) return [];
    return TARGETS.map((target) => ({ target, ticket: optimiseTickets(legs, target, 5, 1, 1.0)[0] ?? null }));
  }, [passing, markets, priceIndex, snapshot]);

  const betLabel = bet === 'any' ? 'Any bet' : bet.startsWith('group:') ? (GROUP_LABEL[bet.slice(6)] ?? 'group') : (markets[bet.slice(7)]?.plain ?? 'bet');
  const leagueLabel = league === 'all' ? 'any league' : (leagueNames[league] ?? league);
  const settledPicks = passing.filter((item) => item.row.st === 'landed' || item.row.st === 'lost');
  const landedPicks = settledPicks.filter((item) => item.row.st === 'landed').length;
  const ticketProbability = combinedProbability(ticket);
  const ticketFair = combinedFair(ticket);
  const ticketMozzart = combinedMozzart(ticket);
  const ticketValue = ticketVsFair(ticket, bonus);
  const ticketPayout = payout(stake, ticket, bonus);
  const correlated = sameMatchWarning(ticket);

  return (
    <div className="space-y-4 pb-40">
      {roundOptions.length > 1 ? (
        <div className="flex flex-wrap gap-1.5">
          {roundOptions.map(([value, label]) => (
            <button key={value} type="button" onClick={() => setRound(value)} className={cn('rounded-full border px-3 py-1 text-xs font-medium', activeDate === value ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground')}>{label}</button>
          ))}
        </div>
      ) : null}

      <div className="grid gap-2 sm:grid-cols-3">
        <select value={league} onChange={(event) => setLeague(event.target.value)} aria-label="League" className="rounded-md border bg-background px-2 py-1.5 text-sm">
          <option value="all">All leagues</option>
          {countries.map(([country, leagues]) => (
            <optgroup key={country} label={country}>
              {leagues.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
            </optgroup>
          ))}
        </select>
        <select value={bet} onChange={(event) => setBet(event.target.value)} aria-label="Bet" className="rounded-md border bg-background px-2 py-1.5 text-sm">
          <option value="any">Any bet</option>
          {GROUP_ORDER.map((group) => (
            <optgroup key={group} label={GROUP_LABEL[group]}>
              <option value={`group:${group}`}>{GROUP_LABEL[group]}</option>
              {(marketGroups.get(group) ?? []).map((market) => <option key={market.id} value={`market:${market.id}`}>{market.plain} ({market.mozzart})</option>)}
            </optgroup>
          ))}
        </select>
        <select value={minOdds} onChange={(event) => setMinOdds(event.target.value)} aria-label="Minimum fair odds" className="rounded-md border bg-background px-2 py-1.5 text-sm">
          <option value="1.40">Min fair odds 1.40</option>
          <option value="1.70">Min fair odds 1.70</option>
          <option value="2.00">Min fair odds 2.00</option>
        </select>
      </div>

      <p className="text-sm text-muted-foreground">
        {passing.length} best {passing.length === 1 ? 'bet' : 'bets'} this round · {betLabel} · {leagueLabel} · fair ≥ {minFair.toFixed(2)}
        {kind === 'example' ? ' · Example round' : ''}
      </p>
      <p className="text-sm">
        {settledPicks.length > 0 ? (
          <>Result: <span className="font-medium">{landedPicks} of {settledPicks.length} landed</span></>
        ) : (
          <span className="text-muted-foreground">Results pending</span>
        )}
      </p>

      {passing.length === 0 ? (
        <div className="space-y-2">
          <p className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
            No {leagueLabel} match fits {betLabel} this round.
          </p>
          {closest.length > 0 ? (
            <div className="space-y-1">
              <h3 className="text-sm font-semibold">Closest candidates</h3>
              <ul className="space-y-1 text-sm text-muted-foreground">
                {closest.map(({ item, failed }) => (
                  <li key={`${item.row.h}|${item.row.a}|${item.row.m}`} className="rounded-md border px-2 py-1">
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
          {passing.map((item) => {
            const { row, price, candidate, checks } = item;
            const meta = markets[row.m];
            const key = `${row.h}|${row.a}|${row.m}`;
            const open = expanded === key;
            const checked = ticket.some((leg) => legKey(leg) === key);
            const strong = candidate.probability >= 0.55;
            const ladderRows = (data?.ladder ?? []).map((id) => (data?.rows ?? []).find((candidateRow) => candidateRow.h === row.h && candidateRow.a === row.a && candidateRow.m === id)).filter(Boolean) as RankRow[];
            return (
              <li key={key} className="rounded-xl border p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="text-muted-foreground">{row.k ?? ''}</span>
                      <span className="font-semibold">{row.h} <span className="text-muted-foreground">v</span> {row.a}</span>
                      <span className="text-xs text-muted-foreground">{leagueNames[row.d] ?? row.d}</span>
                      <Badge variant={strong ? 'success' : 'secondary'}>{strong ? 'Strong' : 'Possible'}</Badge>
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

                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <StatusBadge status={row.st} />
                  {row.ht || row.ft ? <span className="tabular">HT {row.ht ?? '–'} · FT {row.ft ?? '–'}</span> : null}
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-1">
                  {checks.filter((check) => !check.flag).map((check) => (
                    <span key={check.id} title={check.value} className={cn('rounded-full border px-2 py-0.5 text-[11px]', check.passed ? 'border-emerald-500 text-emerald-700' : 'border-rose-400 text-rose-600')}>
                      {check.passed ? '✓' : '✗'} {check.label}
                    </span>
                  ))}
                  <button type="button" onClick={() => toggleLeg(row)} className={cn('ml-auto rounded-md border px-2.5 py-1 text-xs', checked ? 'border-primary bg-primary text-primary-foreground' : '')}>
                    {checked ? 'In ticket' : 'Add to ticket'}
                  </button>
                  <button type="button" onClick={() => setExpanded(open ? null : key)} aria-label="Details">
                    <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform', open && 'rotate-180')} />
                  </button>
                </div>

                {open ? (
                  <div className="mt-2 space-y-2 rounded-md bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                    {price ? <p>Mozzart {price.odds.toFixed(2)} ({utcTime(price.fetchedAt)})</p> : null}
                    <p>Home at home {pct(row.hr)} (n={row.hn}) · away away {pct(row.ar)} (n={row.an}) · league usual {pct(row.lr)} (n={row.ln})</p>
                    <p>Model {pct(row.p)} · counts/empirical {pct(row.lr)} · agreement gap {pct(Math.abs(row.p - row.lr))}</p>
                    <ul className="space-y-0.5">
                      {checks.filter((check) => !check.flag).map((check) => (
                        <li key={check.id} className={cn(check.passed ? 'text-foreground' : 'text-rose-600')}>
                          {check.passed ? '✓' : '✗'} {check.label}: {check.value}{check.flag ? ' (flag)' : ''}
                        </li>
                      ))}
                    </ul>
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
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      {targetTickets.some((entry) => entry.ticket) ? (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Target tickets</h2>
          <p className="text-sm text-muted-foreground">Built only from passing picks, one leg per match.</p>
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
                ) : <p className="text-xs text-muted-foreground">No passing ticket reaches {target.toFixed(2)}.</p>}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

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

      <nav className="flex flex-wrap gap-3 border-t pt-3 text-xs text-muted-foreground">
        <a className="underline underline-offset-2" href="/leagues">Leagues</a>
        <a className="underline underline-offset-2" href="/record">Record</a>
        <a className="underline underline-offset-2" href="/rounds">Rounds</a>
        <a className="underline underline-offset-2" href="/tickets">Tickets</a>
      </nav>
    </div>
  );
}
