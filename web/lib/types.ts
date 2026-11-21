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
  ft_only?: boolean;
  has_odds?: boolean;
  seasons?: number;
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
  league_base?: number;
  lift?: number;
  no_odds?: boolean;
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

export type RoundView = { label: string; picks: RoundPick[]; hits: number; settled_count: number };

export type RoundDocument = {
  date: string;
  label: string;
  weekday: string;
  kind: 'round' | 'example' | 'upcoming';
  cutoff?: string;
  trained_matches?: number;
  fixtures?: number;
  views?: Record<string, RoundView>;
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
  fixtures?: number;
  leagues?: number;
  rows?: number;
  picks: number;
  stand_out?: number;
  hits: number;
  settled_count: number;
  settled: boolean;
};

export type BinRow = { bin: string; shown: number; n: number; hits: number; landed: number | null };

export type CalibrationBlock = { bins: BinRow[] };

export type TypeBacktestRow = {
  group: string;
  rounds: number;
  picks: number;
  picks_per_round: number | null;
  landed: number | null;
  predicted: number | null;
  return: number | null;
  return_ci: [number | null, number | null];
};

export type TypeBacktestFile = {
  seasons: string[];
  groups: TypeBacktestRow[];
  rule: Record<string, number>;
  bootstrap?: { resamples: number; seed: number; unit: string };
  note?: string;
};

export type BestBetsSplit = { settled: number; landed: number };

export type BestBetsRound = {
  date: string;
  label: string;
  kind: string;
  passing: number;
  settled: number;
  landed: number;
  pending: number;
  expected: number;
  strong: BestBetsSplit;
  possible: BestBetsSplit;
};

export type BestBetsRecordFile = {
  min_fair: number;
  strong_probability: number;
  rounds: BestBetsRound[];
  cumulative: Omit<BestBetsRound, 'date' | 'label' | 'kind'>;
};

export type MozzartSummary = {
  n: number;
  landed: number | null;
  return: number | null;
  ci: [number | null, number | null];
};

export type MozzartVettedRecordFile = {
  cumulative: Record<string, MozzartSummary>;
  rounds: ({ date: string } & Record<string, MozzartSummary>)[];
};

export type MozzartStatusRound = {
  round_date: string;
  last_fetch: string | null;
  priced: number;
  started: number;
  matched: number;
  unmatched: number;
};

export type MozzartStatusFile = {
  rounds: MozzartStatusRound[];
  usage: { month: string | null; used: number; cap: number } | null;
  last_run: { at: string; ok: boolean; note: string } | null;
};

export type ValueSummaryRow = {
  bets: number;
  landed: number;
  needed: number;
  profit: number;
  return: number | null;
  ci: [number | null, number | null];
};

export type ValueRecordFile = {
  rounds: { date: string; label: string; summary: ValueSummaryRow }[];
  cumulative: ValueSummaryRow;
  groups: Record<string, ValueSummaryRow>;
  bands: Record<string, ValueSummaryRow>;
  profit_series: { date: string; profit: number }[];
  bootstrap?: { resamples: number; seed: number; unit: string };
  note?: string;
};

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
  missing_odds?: { fixtures: number; fixtures_without_odds: number; brier_without_odds: number | null; brier_with_odds: number | null };
  picker_backtest?: PickerBacktest;
  ranking_backtest?: { seasons: string[]; levels?: string[]; strategies?: string[]; groups: RankBacktestRow[]; level_summary?: LevelSummaryRow[] };
};

export type PickerRow = {
  name: string;
  label: string;
  picks: number;
  mean_probability: number | null;
  hits: number;
  hit_rate: number;
  ci: [number | null, number | null];
};

export type PickerViewSummary = {
  rounds: number;
  picks: number;
  mean_probability: number | null;
  hits: number;
  hit_rate: number | null;
  ci: [number | null, number | null];
  by_play: PickerRow[];
  by_league: PickerRow[];
  no_odds_picks: number;
};

export type PickerBacktest = {
  seasons: string[];
  weekdays: string[];
  degraded_groups: string[];
  views: Record<string, PickerViewSummary>;
  play_bands?: BandStat[];
};

export type BandStat = {
  outcome: string;
  label: string;
  band: string;
  picks: number;
  mean_probability: number;
  hits: number;
  hit_rate: number;
  ci: [number, number];
};

export type ByPlayRow = {
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
  league_base: number;
  lift: number;
  fair_odds: number;
  band: string;
  confidence: 'High' | 'Medium' | 'Low';
  no_odds: boolean;
  counts: number;
  goals: number;
  eligible: boolean;
};

export type ByPlayFile = {
  date: string;
  label: string;
  weekday: string;
  fixtures: number;
  bands: { key: string; label: string }[];
  rows: ByPlayRow[];
};

export type PlayLeagueRow = {
  code: string;
  name: string;
  country: string;
  ft_only: boolean;
  n: number;
  rate: number;
  ci: [number | null, number | null];
};

export type PlayLeaguesFile = { outcomes: Record<string, PlayLeagueRow[]> };

export type RecordFile = {
  calibration: { overall: CalibrationBlock; groups: Record<string, CalibrationBlock> };
  rounds: RoundIndexRow[];
  totals: { rounds: number; picks: number; hits: number; settled: number; hit_rate: number | null };
  picker_backtest?: PickerBacktest;
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

export type MarketMeta = {
  id: string;
  code: string;
  mozzart: string;
  plain: string;
  group: string;
  family: string;
  needs_ht: boolean;
};

export type RankRow = {
  d: string;
  k: string | null;
  h: string;
  a: string;
  m: string;
  p: number;
  pc?: number;
  pl: number;
  pp: number;
  lr: number;
  ln: number;
  hr: number;
  hn: number;
  ar: number;
  an: number;
  c: 'High' | 'Medium' | 'Low';
  s: number;
  st: 'pending' | 'landed' | 'lost' | 'void';
  ht: string | null;
  ft: string | null;
  ld?: boolean | null;
  rs?: string;
};

export type RankFile = {
  date: string;
  label: string;
  weekday: string;
  kind?: string;
  fixtures: number;
  leagues: number;
  markets: number;
  levels?: { key: string; label: string }[];
  ladder?: string[];
  rows: RankRow[];
  market_bands?: Record<string, { landed: number; shown: number; n: number }>;
};

export type LevelSummaryRow = {
  strategy: string;
  level: string;
  picks: number;
  mean_fair_odds: number;
  hit_rate: number;
  mean_shown: number;
  mean_return: number | null;
  return_ci: [number | null, number | null];
};

export type RankBacktestRow = {
  strategy: string;
  group: string;
  band: string;
  picks: number;
  mean_probability: number;
  hits: number;
  hit_rate: number;
  ci: [number, number];
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
