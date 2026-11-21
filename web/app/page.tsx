import VettedList from '@/components/VettedList';
import { Badge } from '@/components/ui/badge';
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

function utcStamp(iso: string | undefined): string | null {
  if (!iso) return null;
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return null;
  const hours = String(value.getUTCHours()).padStart(2, '0');
  const minutes = String(value.getUTCMinutes()).padStart(2, '0');
  return `${hours}:${minutes} UTC`;
}

export default function HomePage() {
  const index = readRoundIndex();
  const leagues = readIndex().divisions;
  const leagueOptions: [string, string, string][] = leagues.map((division) => [
    division.code,
    division.name,
    division.country,
  ]);

  const next = nextRoundDate(new Date());
  const nextIso = isoDate(next);
  const nextRound = index.rounds.find((row) => row.kind === 'round' && row.date === nextIso);
  const nextHasPicks = Boolean(nextRound && nextRound.picks > 0);

  const seenDates = new Set<string>();
  const withPicks = index.rounds
    .filter((row) => row.kind === 'round' && row.picks > 0)
    .filter((row) => {
      if (seenDates.has(row.date)) return false;
      seenDates.add(row.date);
      return true;
    });
  const upcoming = withPicks
    .filter((row) => row.date >= nextIso)
    .sort((a, b) => (a.date < b.date ? -1 : 1));
  const latest = [...withPicks].sort((a, b) => (a.date < b.date ? 1 : -1))[0];
  const example = index.rounds
    .filter((row) => row.kind === 'example' && row.picks > 0)
    .sort((a, b) => (a.date < b.date ? 1 : -1))[0];
  const chosen = upcoming[0] ?? latest ?? example;

  const roundOptions: [string, string][] = [...withPicks]
    .sort((a, b) => (a.date < b.date ? -1 : 1))
    .slice(-6)
    .map((row) => [row.date, row.label]);

  const updated = utcStamp(index.generated_at) ?? utcStamp(new Date().toISOString());
  const weekend = next.getUTCDay() === 0 || next.getUTCDay() === 6;
  const checkTimes = weekend ? 'Fri 18:00, Fri 21:00, Sat 08:00, Sun 08:00' : 'Tue 14:00, Tue 16:00';
  const below = chosen
    ? `${chosen.kind === 'example' ? 'example round' : 'latest finished round'}, ${chosen.label}`
    : 'no round yet';

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">
          {chosen ? `${chosen.label} — best plays` : 'Best plays'}
        </h1>
        {updated ? <p className="text-xs text-muted-foreground">Last updated: {updated}</p> : null}
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          {chosen?.kind === 'example' ? <Badge variant="secondary">Example — {chosen.label}</Badge> : null}
          <span>
            Every play is a calibrated probability with fair odds shown. Nothing here is a certainty.
          </span>
        </div>
      </header>

      {!nextHasPicks ? (
        <div className="rounded-xl border border-dashed bg-muted/40 px-4 py-3 text-sm">
          <p className="font-medium">No picks yet for {roundLabel(next)}.</p>
          <p className="text-muted-foreground">
            They appear once football-data.co.uk posts the fixtures (usually Friday afternoon UK for weekend
            rounds, Tuesday for midweek; we check at {checkTimes} UTC). Below: {below}.
          </p>
        </div>
      ) : null}

      {chosen ? (
        <VettedList
          date={chosen.date}
          kind={chosen.kind}
          leagueOptions={leagueOptions}
          roundOptions={roundOptions}
        />
      ) : (
        <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          No round published yet. Saturday and Sunday picks appear Friday around 18:00 UK; Tuesday picks Tuesday
          around 14:00 UK.
        </p>
      )}
    </div>
  );
}
