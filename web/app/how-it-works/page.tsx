export default function HowItWorksPage() {
  const points = [
    {
      title: 'What we count',
      body: 'Every result since 2015-16 in twelve divisions: full-time and half-time goals, both teams scoring, totals, combos. Each number is a hit rate with a sample size and a 95% confidence interval.',
    },
    {
      title: 'How a probability is built',
      body: 'Two engines run in parallel. One counts league and team history with recency weighting and shrinkage. The other builds a half-by-half goal grid from team strength and anchors it on de-margined pre-match odds. A per-group stack then picks the better source on held-out seasons.',
    },
    {
      title: 'Why nothing under fair odds 1.54 is shown',
      body: 'Plays above about 65% are dropped, which is where fair odds reach roughly 1.54. A 75% “sure thing” at short odds is where the counting gets thin and the market is already efficient — publishing it would be bravado, not analysis.',
    },
    {
      title: 'How to read a card',
      body: 'The percentage is the calibrated chance the play lands, fair odds are 1 divided by that, and the “Why” panel shows the two engines, the home/away counts and the league rate behind the pick.',
    },
    {
      title: 'The confidence badge',
      body: 'High needs at least 20 matches of team history, the two engines within 0.05 of each other and a backtest bin that landed close to what it showed. Low means one of those is weak — treat the number as a starting point, not a verdict.',
    },
    {
      title: 'When picks appear',
      body: 'Saturday rounds publish Friday around 18:00 UK, Tuesday rounds Tuesday around 14:00 UK. Only Tuesday and Saturday fixtures are considered, and a published round is never edited — only settled.',
    },
    {
      title: 'Statistics, not certainty',
      body: 'Every probability here is a historical frequency that has been calibrated. A 62% play loses four times in ten. Nothing on this site is a tip, a lock or a promise.',
    },
    {
      title: '18+ — gamble responsibly',
      body: 'If betting stops being a hobby, stop. Set limits before you start, never chase losses, and use the self-exclusion tools your operator provides.',
    },
  ];

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight">How it works</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Plain language, no model names. If a number appears on this site, this page explains where it came from.
        </p>
      </header>

      <ol className="space-y-4">
        {points.map((point, index) => (
          <li key={point.title} className="flex gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
              {index + 1}
            </span>
            <div className="space-y-1">
              <h2 className="text-base font-semibold">{point.title}</h2>
              <p className="max-w-2xl text-sm text-muted-foreground">{point.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
