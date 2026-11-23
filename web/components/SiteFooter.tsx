import Link from 'next/link';

const SECONDARY = [
  { href: '/value', label: 'Value bets' },
  { href: '/explore', label: 'Explore' },
  { href: '/rounds', label: 'Rounds' },
  { href: '/leagues', label: 'Leagues' },
  { href: '/record', label: 'Record' },
  { href: '/how-it-works', label: 'How it works' },
];

export default function SiteFooter() {
  return (
    <footer className="border-t border-border bg-card/40">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-6 text-sm text-muted-foreground sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p>
            Data:{' '}
            <a
              className="font-medium text-foreground underline decoration-border underline-offset-4 hover:text-primary"
              href="https://football-data.co.uk/"
              target="_blank"
              rel="noopener noreferrer"
            >
              football-data.co.uk
            </a>
          </p>
          <p className="max-w-xl text-xs">
            Derived counts and rates only — no raw match data is republished. Predictions are probabilities, not
            certainties. 18+ BeGambleAware.org
          </p>
        </div>
        <nav aria-label="Secondary" className="flex max-w-md flex-wrap gap-x-4 gap-y-1 text-xs">
          {SECONDARY.map((link) => (
            <Link key={link.href} href={link.href} className="inline-flex min-h-11 items-center hover:text-foreground sm:min-h-0">
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
