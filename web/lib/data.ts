import fs from 'node:fs';
import path from 'node:path';

import type { LeagueFile, LeagueIndex, ModelFile, RecordFile, RoundDocument, RoundIndexRow } from './types';

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

export function readRoundIndex(): { rounds: RoundIndexRow[] } {
  const file = path.join(DATA_DIR, 'rounds', 'index.json');
  if (!fs.existsSync(file)) return { rounds: [] };
  return readJson<{ rounds: RoundIndexRow[] }>(path.join('rounds', 'index.json'));
}

export function readRound(date: string): RoundDocument | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const file = path.join(DATA_DIR, 'rounds', `${date}.json`);
  if (!fs.existsSync(file)) return null;
  return readJson<RoundDocument>(path.join('rounds', `${date}.json`));
}

export function readModel(): ModelFile | null {
  const file = path.join(DATA_DIR, 'model.json');
  return fs.existsSync(file) ? readJson<ModelFile>('model.json') : null;
}

export function readRecord(): RecordFile | null {
  const file = path.join(DATA_DIR, 'record.json');
  return fs.existsSync(file) ? readJson<RecordFile>('record.json') : null;
}
