'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { cn } from '@/lib/utils';
import ThemeToggle from '@/components/ThemeToggle';

const LINKS = [
  { href: '/', label: 'This round' },
  { href: '/leagues', label: 'Leagues' },
  { href: '/record', label: 'Record' },
  { href: '/how-it-works', label: 'How it works' },
];

export default function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-20 border-b bg-background/85 backdrop-blur">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
        <Link href="/" className="text-sm font-bold tracking-tight">
          Football Picks
        </Link>
        <nav className="flex flex-1 flex-wrap items-center gap-1">
          {LINKS.map((link) => {
            const active = link.href === '/' ? pathname === '/' : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  'rounded-md px-2.5 py-1 text-sm transition-colors',
                  active ? 'bg-accent font-medium text-accent-foreground' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
        <ThemeToggle />
      </div>
    </header>
  );
}
