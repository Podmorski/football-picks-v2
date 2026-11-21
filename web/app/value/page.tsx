import ValueList from '@/components/ValueList';
import { readIndex, readRoundIndex } from '@/lib/data';

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function nextRoundDate(now: Date): Date {
  const cursor = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  for (let step = 0; step < 8; step += 1) {
    const day = cursor.getUTCDay();
    if (day === 0 || day === 2 || day === 6) return cursor;
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return cursor;
}

function roundLabel(date: Date): string {
  return `${WEEKDAYS[date.getUTCDay()]} ${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}`;
}

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export default function ValuePage() {
  const index = readRoundIndex();
  const leagues = readIndex().divisions;
  const leagueOptions: [string, string, string][] = leagues.map((division) => [division.code, division.name, division.country]);
  const next = nextRoundDate(new Date());
  const nextIso = isoDate(next);

  const seen = new Set<string>();
  const withPicks = index.rounds
    .filter((row) => row.kind === 'round' && row.picks > 0)
    .filter((row) => {
      if (seen.has(row.date)) return false;
      seen.add(row.date);
      return true;
    });
  const upcoming = withPicks.filter((row) => row.date >= nextIso).sort((a, b) => (a.date < b.date ? -1 : 1));
  const latest = [...withPicks].sort((a, b) => (a.date < b.date ? 1 : -1))[0];
  const example = index.rounds
    .filter((row) => row.kind === 'example' && row.picks > 0)
    .sort((a, b) => (a.date < b.date ? 1 : -1))[0];
  const chosen = upcoming[0] ?? latest ?? example;
  const roundOptions: [string, string][] = [...withPicks]
    .sort((a, b) => (a.date < b.date ? -1 : 1))
    .slice(-6)
    .map((row) => [row.date, row.label]);
  const roundMeta: Record<string, { label: string; kind: string }> = {};
  for (const row of index.rounds) roundMeta[row.date] = { label: row.label, kind: row.kind };

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Value bets</h1>
        <p className="text-sm text-muted-foreground">
          Mozzart price at or above the minimum play odds, plus the team-record and agreement checks.
          One per match, strongest edge first. Value is unproven: it is a price signal, not a guarantee.
        </p>
      </header>

      {chosen ? (
        <ValueList
          date={chosen.date}
          kind={chosen.kind}
          leagueOptions={leagueOptions}
          roundOptions={roundOptions}
          roundMeta={roundMeta}
        />
      ) : (
        <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          No round published yet. {roundLabel(next)} is the next round.
        </p>
      )}
    </div>
  );
}
