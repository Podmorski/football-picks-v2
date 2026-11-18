'use client';

import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';

import { Button } from '@/components/ui/button';

export default function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains('dark'));
  }, []);

  function toggle() {
    const next = !document.documentElement.classList.contains('dark');
    document.documentElement.classList.toggle('dark', next);
    try {
      window.localStorage.setItem('theme', next ? 'dark' : 'light');
    } catch {
      /* storage may be unavailable */
    }
    setDark(next);
  }

  return (
    <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle dark mode">
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}
