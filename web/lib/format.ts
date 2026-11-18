import type { Stat } from './types';

export function rate(stat?: Stat): string {
  if (!stat) return '–';
  const [, , value] = stat;
  return value === null ? '–' : `${(value * 100).toFixed(1)}%`;
}

export function nOf(stat?: Stat): string {
  if (!stat) return '0';
  return stat[0].toLocaleString('en-GB');
}

export function ci(stat?: Stat): string {
  if (!stat) return '–';
  const [, , , lo, hi] = stat;
  if (lo === null || hi === null) return '–';
  return `${(lo * 100).toFixed(1)}–${(hi * 100).toFixed(1)}%`;
}

export function confidence(stat?: Stat): string {
  const value = ci(stat);
  return value === '–' ? value : `95% CI ${value}`;
}
