import type { Metadata } from 'next';

import SiteHeader from '@/components/SiteHeader';
import './globals.css';

export const metadata: Metadata = {
  title: 'Football Picks — historical rates and best plays',
  description:
    'Counted football outcomes, calibrated probabilities and one best play per match, from football-data.co.uk results and pre-match odds.',
};

const THEME_SCRIPT = `(function(){try{var s=localStorage.getItem('theme');var d=s?s==='dark':window.matchMedia('(prefers-color-scheme: dark)').matches;if(d)document.documentElement.classList.add('dark');}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-screen flex-col">
        <SiteHeader />
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>
        <footer className="border-t bg-muted/40">
          <div className="mx-auto max-w-5xl space-y-1 px-4 py-6 text-sm text-muted-foreground">
            <p>
              Data:{' '}
              <a
                className="underline underline-offset-2"
                href="https://football-data.co.uk/"
                target="_blank"
                rel="noopener noreferrer"
              >
                football-data.co.uk
              </a>
            </p>
            <p className="text-xs">
              Derived counts and rates only — no raw match data is republished. Statistics, not certainty. 18+ —
              gamble responsibly.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
