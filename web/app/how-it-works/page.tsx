export default function HowItWorksPage() {
  const points = [
    {
      title: 'What we count',
      body: 'Twenty-two main divisions with full-time and half-time goals and pre-match odds, plus extra full-time-only leagues for statistics. Each number is a historical hit rate with its sample size and a 95% confidence interval.',
    },
    {
      title: 'How a probability is built',
      body: 'Two engines run in parallel. One counts league and team history with recency weighting and shrinkage. The other builds a half-by-half goal grid from team strength and anchors it on de-margined pre-match odds. A per-group stack then picks the better source on held-out seasons.',
    },
    {
      title: 'Fair odds and actual odds',
      body: 'Fair odds are 1 divided by the calibrated probability. Daily best ranks on the actual decimal price from a frozen Mozzart snapshot, in a visible band: 1.70–2.30 by default, with 1.20–1.69, 2.31–4.00, 4.01+ and All 1.20+ selectable. There is no hidden odds floor or favourites switch.',
    },
    {
      title: 'Best bets: the Daily best list',
      body: 'The default view is Daily best: up to 12 games with an actual price of at least 1.20, one market per fixture, preferring the selected band. If a fixture has no candidate inside the band, the nearest band candidate fills the slot; the list is never padded with sub-1.20 odds or a second market from the same match. Choosing a league reruns the same ranking and offers Show all eligible games. Choosing a market group or one exact market switches to the unrestricted picker: every eligible fixture, sorted by probability, with no probability or odds gate. Correct score stays hidden.',
    },
    {
      title: 'How to read a card',
      body: 'The percentage is the calibrated chance and fair odds are 1 divided by it. Open the details for league usual, home/away records, the team empirical estimate, model agreement difference, descriptive match statistics and, when available, the Mozzart snapshot price and fetch time.',
    },
    {
      title: 'Automatic round proposals',
      body: 'Once the first usable Mozzart snapshot exists for a round, three paper proposals are frozen: two best games, around 3.00 and around 5.00. They use actual frozen prices, one leg per match and only 58%+ plays. A flat 50/30/20 benchmark and a capped quarter-Kelly simulation are recorded separately. These are paper ledgers, not a profit guarantee.',
    },
    {
      title: 'When rounds appear',
      body: 'Rounds are Tuesday, Saturday and Sunday. Weekend fixtures and odds usually appear Friday; midweek fixtures appear Tuesday. A published round is never edited, only settled.',
    },
    {
      title: 'Mozzart snapshots and Value',
      body: 'Mozzart prices come from a private snapshot and drive the Daily best band. They appear in the daily cards and in details; unpriced builds show the probability and fair odds without an actual-EV claim. Value bets remain a separate experimental page: its price signal is unproven and is not part of the Best bets list.',
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
