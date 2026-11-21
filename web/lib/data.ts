import fs from 'node:fs';
import path from 'node:path';

import type { BestBetsRecordFile, LeagueFile, LeagueIndex, ModelFile, MozzartStatusFile, MozzartVettedRecordFile, RankRow, RecordFile, RoundDocument, RoundIndexRow, TypeBacktestFile } from './types';

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

function decodeRankDocument(document: RoundDocument | null): (RoundDocument & { rows: RankRow[] }) | null {
  if (!document) return null;
  const raw = (document as unknown as Record<string, unknown>).rows as unknown[] | undefined;
  if (raw && raw.length && Array.isArray(raw[0])) {
    const fixtures = ((document as unknown as Record<string, unknown>).fixture_list ?? []) as { d: string; k: string | null; h: string; a: string }[];
    const fields = (((document as unknown as Record<string, unknown>).fields as string[] | undefined) ?? []);
    const decoded = document as unknown as Record<string, unknown>;
    decoded.rows = (raw as unknown[][]).map((values) => {
      const fixture = fixtures[values[0] as number];
      const row: Record<string, unknown> = { d: fixture.d, k: fixture.k, h: fixture.h, a: fixture.a };
      fields.forEach((name, index) => {
        if (index < values.length) row[name] = values[index];
      });
      if (row.pc === undefined) row.pc = row.p;
      return row as RankRow;
    });
  }
  return document as unknown as RoundDocument & { rows: RankRow[] };
}

export function readRankRound(date: string): (RoundDocument & { rows: RankRow[] }) | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const file = path.join(DATA_DIR, 'rounds', `${date}.json`);
  if (!fs.existsSync(file)) return null;
  return decodeRankDocument(readJson<RoundDocument>(path.join('rounds', `${date}.json`)));
}

// The Best bets dashboard loads `*.full.json` first; the rounds tally must read
// the same rows, so it prefers the companion too and falls back to the compact file.
export function readRankRoundComplete(date: string): (RoundDocument & { rows: RankRow[] }) | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  for (const name of [`${date}.full.json`, `${date}.json`]) {
    const file = path.join(DATA_DIR, 'rounds', name);
    if (fs.existsSync(file)) return decodeRankDocument(readJson<RoundDocument>(path.join('rounds', name)));
  }
  return null;
}

export function readModel(): ModelFile | null {
  const file = path.join(DATA_DIR, 'model.json');
  return fs.existsSync(file) ? readJson<ModelFile>('model.json') : null;
}

export function readRecord(): RecordFile | null {
  const file = path.join(DATA_DIR, 'record.json');
  return fs.existsSync(file) ? readJson<RecordFile>('record.json') : null;
}

export function readTypeBacktest(): TypeBacktestFile | null {
  const file = path.join(DATA_DIR, 'type_backtest.json');
  return fs.existsSync(file) ? readJson<TypeBacktestFile>('type_backtest.json') : null;
}

export function readBestBetsRecord(): BestBetsRecordFile | null {
  const file = path.join(DATA_DIR, 'best-bets-record.json');
  return fs.existsSync(file) ? readJson<BestBetsRecordFile>('best-bets-record.json') : null;
}

export function readMozzartVettedRecord(): MozzartVettedRecordFile | null {
  const file = path.join(DATA_DIR, 'mozzart-vetted-record.json');
  return fs.existsSync(file) ? readJson<MozzartVettedRecordFile>('mozzart-vetted-record.json') : null;
}

export function readMozzartStatus(): MozzartStatusFile | null {
  const file = path.join(DATA_DIR, 'mozzart-status.json');
  return fs.existsSync(file) ? readJson<MozzartStatusFile>('mozzart-status.json') : null;
}
