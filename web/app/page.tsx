import Dashboard from '@/components/Dashboard';
import { Badge } from '@/components/ui/badge';
import { readIndex, readRoundIndex } from '@/lib/data';

export default function HomePage() {
  const index = readRoundIndex();
  const leagues = readIndex().divisions;
  const leagueOptions: [string, string, string][] = leagues.map((division) => [
    division.code,
    division.name,
    division.country,
  ]);

  const byDate = (a: { date: string }, b: { date: string }) => (a.date < b.date ? 1 : -1);
  const round = index.rounds.filter((row) => row.kind === 'round' && row.picks > 0).sort(byDate)[0];
  const example = index.rounds.filter((row) => row.kind === 'example' && row.picks > 0).sort(byDate)[0];
  const chosen = round ?? example;

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">
          {chosen ? `${chosen.label} — best plays` : 'Best plays'}
        </h1>
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          {chosen?.kind === 'example' ? <Badge variant="secondary">Example — {chosen.label}</Badge> : null}
          <span>
            Every play is a calibrated probability with fair odds shown. Nothing here is a certainty.
          </span>
        </div>
      </header>

      {chosen ? (
        <Dashboard date={chosen.date} kind={chosen.kind} leagueOptions={leagueOptions} />
      ) : (
        <p className="rounded-xl border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
          No round published yet. Saturday picks appear Friday around 18:00 UK; Tuesday picks Tuesday around 14:00 UK.
        </p>
      )}
    </div>
  );
}
