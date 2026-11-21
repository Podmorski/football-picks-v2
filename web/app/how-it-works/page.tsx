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
      title: 'Fair odds and minimum playable odds',
      body: 'Fair odds are 1 divided by the calibrated probability. Every card also shows a minimum playable price: 1.05 divided by that probability, rounded up to two decimals. Below it the price does not cover the estimated chance. Any bet defaults to minimum fair 1.70; group and single-market views default to any odds, with 1.40, 1.70, 2.00 and 2.50 available. There is no hidden odds floor or favourites switch.',
    },
    {
      title: 'Ranked and strict',
      body: 'Group and single-market views default to Ranked — all candidates. After the league and minimum-odds filters, a group shows one candidate per match by highest probability, while a single market shows every eligible fixture. Strict checks only is an optional filter that applies the existing lift, team-record, agreement and fair-odds conditions. Ranked mode has no established profitability record yet; it is a statistical ranking, not a value signal.',
    },
    {
      title: 'How to read a card',
      body: 'The percentage is the calibrated chance, fair odds are 1 divided by it, and the minimum playable price is the lowest price worth taking. Open the details for the league usual and lift, home/away records, team empirical estimate, model agreement difference, fair odds, strict-check results and, when available, the Mozzart snapshot price and fetch time.',
    },
    {
      title: 'Strong and Possible',
      body: 'Strong means displayed probability at or above 55% in every Best bets view; Possible is everything else. The badge is a probability label, not a value or profit label; it does not change the pick or the price.',
    },
    {
      title: 'When rounds appear',
      body: 'Rounds are Tuesday, Saturday and Sunday. Weekend fixtures and odds usually appear Friday; midweek fixtures appear Tuesday. A published round is never edited, only settled.',
    },
    {
      title: 'Mozzart snapshots and Value',
      body: 'Mozzart prices come from a private snapshot and appear only in the tap-open details. A Value row means the snapshot price is at or above the minimum playable price and the team-record and agreement checks pass with fair odds at most 6.00. Value is unproven: it is a price signal, not a tip or a guarantee; the record is reported once results settle.',
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
