// Shapes of the JSON written by pipeline/run.py. Keep in sync with SCHEMA there.

// [n, hits, rate, lo, hi] — rate and Wilson 95% bounds are 0-1, null when n = 0.
export type Stat = [number, number, number | null, number | null, number | null];

export type OutcomeMeta = {
  id: string;
  label: string;
  group: string;
  needs_ht: boolean;
};

export type DivisionSummary = {
  code: string;
  name: string;
  country: string;
  tier: number;
  matches: number;
  teams: number;
  focus_season: string;
  headline: Record<string, Stat>;
};

export type LeagueIndex = {
  seasons: string[];
  current_season: string;
  divisions: DivisionSummary[];
};

export type Top10Row = {
  team: string;
  n: number;
  hits: number;
  rate: number;
  lo: number;
  hi: number;
};

export type ScopeKey = 'home' | 'away' | 'last10';

export type TeamScopes = Record<string, Record<string, Stat>>;

export type TeamRecord = {
  current: TeamScopes;
  previous: TeamScopes;
  streak: Record<string, number>;
};

export type RoundPick = {
  div: string;
  league: string;
  kickoff: string | null;
  home: string;
  away: string;
  outcome: string;
  label: string;
  group: string;
  play: string;
  probability: number;
  fair_odds: number;
  confidence: 'High' | 'Medium' | 'Low';
  why: {
    home_at_home: [number, number];
    away_away: [number, number];
    league_rate: [number, number];
    engines: { counts: number; goals: number; gap: number };
    samples: { home: number; away: number };
    bin: { bin: string; shown: number; landed: number | null; n: number } | null;
  };
  settled: boolean;
  landed: boolean | null;
  result: string | null;
};

export type RoundDocument = {
  date: string;
  label: string;
  weekday: string;
  kind: 'round' | 'example' | 'upcoming';
  cutoff: string;
  trained_matches: number;
  picks: RoundPick[];
  published: boolean;
  settled: boolean;
  hits: number;
  settled_count: number;
};

export type RoundIndexRow = {
  date: string;
  label: string;
  weekday: string;
  kind: string;
  picks: number;
  hits: number;
  settled_count: number;
  settled: boolean;
};

export type BinRow = { bin: string; shown: number; n: number; hits: number; landed: number | null };

export type CalibrationBlock = { bins: BinRow[] };

export type ModelFile = {
  backtest: { seasons: string[]; fixtures: number };
  hyperparameters: { best: { half_life_days: number; k: number; logloss: number } };
  ablation: {
    overall: Record<string, { brier: number | null; logloss: number | null }>;
    groups: Record<string, { brier: Record<string, number | null>; logloss: Record<string, number | null>; n: number; live_component: string }>;
  };
  calibration: { overall: CalibrationBlock; groups: Record<string, CalibrationBlock> };
  decisions: Record<string, { keep_counts: boolean; keep_goals: boolean; keep_odds: boolean; keep_calibration: boolean; live_component: string }>;
  full_worse_than_base_count: number;
};

export type RecordFile = {
  calibration: { overall: CalibrationBlock; groups: Record<string, CalibrationBlock> };
  rounds: RoundIndexRow[];
  totals: { rounds: number; picks: number; hits: number; settled: number; hit_rate: number | null };
};

export type UpcomingFixture = {
  date: string;
  time: string | null;
  home: string;
  away: string;
  best: RoundPick | null;
};

export type TeamsFile = {
  code: string;
  name: string;
  focus_season: string;
  teams: Record<string, { current: Record<string, Record<string, Stat>>; previous: Record<string, Record<string, Stat>>; streak: Record<string, number> }>;
  top10: Record<string, Partial<Record<ScopeKey, Top10Row[]>>>;
  upcoming: UpcomingFixture[];
};

export type LeagueFile = {
  code: string;
  name: string;
  country: string;
  tier: number;
  seasons: string[];
  current_season: string;
  focus_season: string;
  previous_season: string | null;
  matches: number;
  team_count: number;
  outcomes: OutcomeMeta[];
  league: {
    pooled: Record<string, Stat>;
    by_season: Record<string, Record<string, Stat>>;
    by_weekday: Record<string, Record<string, Stat>>;
  };
  teams: Record<string, TeamRecord>;
  top10: Record<string, Partial<Record<ScopeKey, Top10Row[]>>>;
};
