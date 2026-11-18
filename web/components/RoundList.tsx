'use client';

import { useMemo, useState } from 'react';
import { Check, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import type { RoundDocument, RoundPick } from '@/lib/types';

const CONFIDENCE_VARIANT = { High: 'success', Medium: 'warning', Low: 'secondary' } as const;

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function PickCard({ pick }: { pick: RoundPick }) {
  const league = pick.league || pick.div;
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">
            {league}
            {pick.kickoff ? ` · ${pick.kickoff}` : ''}
          </p>
          <h3 className="truncate text-base font-semibold">
            {pick.home} <span className="text-muted-foreground">v</span> {pick.away}
          </h3>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {pick.settled && pick.landed !== null ? (
            <Badge variant={pick.landed ? 'success' : 'destructive'}>
              {pick.landed ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
              {pick.landed ? 'Landed' : 'Missed'}
            </Badge>
          ) : null}
          <Badge variant={CONFIDENCE_VARIANT[pick.confidence] ?? 'secondary'}>{pick.confidence}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="font-medium">{pick.play}</p>
        <div className="space-y-1.5">
          <Progress value={pick.probability * 100} />
          <div className="flex items-baseline justify-between text-sm">
            <span className="tabular font-semibold">{pct(pick.probability)}</span>
            <span className="text-muted-foreground">
              fair odds <span className="tabular">{pick.fair_odds.toFixed(2)}</span>
            </span>
          </div>
        </div>
        <details className="group rounded-md border bg-muted/40 px-3 py-2">
          <summary className="cursor-pointer text-sm font-medium text-muted-foreground select-none">
            Why
          </summary>
          <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
            <li>
              Home at home:{' '}
              <span className="tabular text-foreground">
                {pick.why.home_at_home[0]}/{pick.why.home_at_home[1]}
              </span>
            </li>
            <li>
              Away away:{' '}
              <span className="tabular text-foreground">
                {pick.why.away_away[0]}/{pick.why.away_away[1]}
              </span>
            </li>
            <li>
              League rate:{' '}
              <span className="tabular text-foreground">{pct(pick.why.league_rate[0])}</span> ({pick.why.league_rate[1].toLocaleString('en-GB')})
            </li>
            <li>
              Engines agree: counts <span className="tabular text-foreground">{pct(pick.why.engines.counts)}</span>, goals{' '}
              <span className="tabular text-foreground">{pct(pick.why.engines.goals)}</span> (gap {pct(pick.why.engines.gap)})
            </li>
            {pick.why.bin ? (
              <li>
                Backtest bin {pick.why.bin.bin}%: shown {pct(pick.why.bin.shown)}, landed{' '}
                <span className="tabular text-foreground">
                  {pick.why.bin.landed !== null ? pct(pick.why.bin.landed) : '–'}
                </span>{' '}
                ({pick.why.bin.n.toLocaleString('en-GB')} samples)
              </li>
            ) : null}
            {pick.result ? <li>Result: <span className="tabular text-foreground">{pick.result}</span></li> : null}
          </ul>
        </details>
      </CardContent>
    </Card>
  );
}

export default function RoundList({ round }: { round: RoundDocument }) {
  const leagues = useMemo(
    () => Array.from(new Set(round.picks.map((pick) => pick.div))).sort(),
    [round.picks],
  );
  const [filter, setFilter] = useState('all');
  const picks = filter === 'all' ? round.picks : round.picks.filter((pick) => pick.div === filter);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={() => setFilter('all')}
          className={cn(
            'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
            filter === 'all' ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          All ({round.picks.length})
        </button>
        {leagues.map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => setFilter(code)}
            className={cn(
              'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
              filter === code ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {round.picks.find((pick) => pick.div === code)?.league ?? code}
          </button>
        ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {picks.map((pick) => (
          <PickCard key={`${pick.home}-${pick.away}`} pick={pick} />
        ))}
      </div>
    </div>
  );
}
