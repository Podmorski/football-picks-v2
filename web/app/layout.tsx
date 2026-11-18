import type { Metadata } from 'next';
import Link from 'next/link';

import './globals.css';

export const metadata: Metadata = {
  title: 'Football Picks — historical outcome rates',
  description:
    'How often each football outcome has actually happened, by league, team and venue, counted from football-data.co.uk results.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="wrap header-inner">
            <Link className="brand" href="/">
              Football Picks
            </Link>
            <span className="badge">historical rates, not predictions</span>
          </div>
        </header>

        {children}

        <footer className="site-footer">
          <div className="wrap">
            <p>
              Data:{' '}
              <a href="https://football-data.co.uk/" target="_blank" rel="noopener noreferrer">
                football-data.co.uk
              </a>
            </p>
            <p className="sub">
              Derived counts and rates only — no raw match data is republished. Nothing here is betting advice.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
