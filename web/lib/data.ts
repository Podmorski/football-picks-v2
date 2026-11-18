import fs from 'node:fs';
import path from 'node:path';

import type { LeagueFile, LeagueIndex } from './types';

// The pipeline writes here; Next serves the same files statically. Reads happen at build time.
const DATA_DIR = path.join(process.cwd(), 'public', 'data');

const CODE_PATTERN = /^[A-Za-z0-9]{2,4}$/;

function readJson<T>(file: string): T {
  const raw = fs.readFileSync(path.join(DATA_DIR, file), 'utf8');
  return JSON.parse(raw) as T;
}

export function readIndex(): LeagueIndex {
  return readJson<LeagueIndex>('leagues.json');
}

export function readLeague(code: string): LeagueFile | null {
  if (!CODE_PATTERN.test(code)) return null;
  const file = path.join(DATA_DIR, `${code}.json`);
  if (!fs.existsSync(file)) return null;
  return readJson<LeagueFile>(`${code}.json`);
}
