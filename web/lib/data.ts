import fs from 'node:fs';
import path from 'node:path';

import type { LeagueFile, LeagueIndex, ModelFile, RankRow, RecordFile, RoundDocument, RoundIndexRow } from './types';

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

export function readRoundIndex(): { rounds: RoundIndexRow[]; generated_at?: string } {
  const file = path.join(DATA_DIR, 'rounds', 'index.json');
  if (!fs.existsSync(file)) return { rounds: [] };
  return readJson<{ rounds: RoundIndexRow[]; generated_at?: string }>(path.join('rounds', 'index.json'));
}

export function readRound(date: string): RoundDocument | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const file = path.join(DATA_DIR, 'rounds', `${date}.json`);
  if (!fs.existsSync(file)) return null;
  return readJson<RoundDocument>(path.join('rounds', `${date}.json`));
}

export function readRankRound(date: string): (RoundDocument & { rows: RankRow[] }) | null {
  const document = readRound(date) as unknown as Record<string, unknown> | null;
  if (!document) return null;
  const raw = document.rows as unknown[] | undefined;
  if (raw && raw.length && Array.isArray(raw[0])) {
    const fixtures = (document.fixture_list ?? []) as { d: string; k: string | null; h: string; a: string }[];
    document.rows = (raw as unknown[][]).map((values) => {
      const fixture = fixtures[values[0] as number];
      return {
        d: fixture.d,
        k: fixture.k,
        h: fixture.h,
        a: fixture.a,
        m: values[1],
        p: values[2],
        pl: values[3],
        pp: values[4],
        lr: values[5],
        ln: values[6],
        hr: values[7],
        hn: values[8],
        ar: values[9],
        an: values[10],
        c: values[11],
        s: values[12],
        st: values[13],
        ht: values[14],
        ft: values[15],
      } as RankRow;
    });
  }
  return document as unknown as RoundDocument & { rows: RankRow[] };
}

export function readModel(): ModelFile | null {
  const file = path.join(DATA_DIR, 'model.json');
  return fs.existsSync(file) ? readJson<ModelFile>('model.json') : null;
}

export function readRecord(): RecordFile | null {
  const file = path.join(DATA_DIR, 'record.json');
  return fs.existsSync(file) ? readJson<RecordFile>('record.json') : null;
}
