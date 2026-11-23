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

export type BestBetsRound = {
  date: string;
  label: string;
  kind: string;
  passing: number;
  settled: number;
  landed: number;
  lost: number;
  void: number;
  pending: number;
  expected: number;
};

export type BestBetsRecordFile = {
  min_pc: number;
  min_fair?: number;
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

export type DescriptiveFrequency = { count: number; rate: number | null };

export type DescriptiveResultFrequency = {
  n: number;
  '1': number | null;
  X: number | null;
  '2': number | null;
};

export type DescriptiveHTFTFrequency = { n: number } & Record<string, number | null>;

export type DescriptiveWindow = {
  n: number;
  w: number;
  d: number;
  l: number;
  gf: number;
  ga: number;
  gf_pm: number | null;
  ga_pm: number | null;
  points: number;
  points_pm: number | null;
  btts: DescriptiveFrequency;
  over25: DescriptiveFrequency;
  ft: DescriptiveResultFrequency;
  ht: DescriptiveResultFrequency;
  htft: DescriptiveHTFTFrequency;
};

export type DescriptiveStreaks = Record<
  'win' | 'unbeaten' | 'winless' | 'losing' | 'drawing' | 'btts' | 'no_btts' | 'over25' | 'under25',
  number
>;

export type DescriptiveTeam = {
  windows: {
    overall6: DescriptiveWindow;
    overall12: DescriptiveWindow;
    venue6: DescriptiveWindow;
    venue12: DescriptiveWindow;
  };
  streaks: { overall: DescriptiveStreaks; venue: DescriptiveStreaks };
};

export type DescriptiveMeeting = {
  date: string;
  home: string;
  away: string;
  fthg: number;
  ftag: number;
  hthg: number | null;
  htag: number | null;
};

export type DescriptiveH2H = {
  n: number;
  w: number;
  d: number;
  l: number;
  gf: number;
  ga: number;
  btts: DescriptiveFrequency;
  over25: DescriptiveFrequency;
  meetings: DescriptiveMeeting[];
};

export type DescriptiveFixture = {
  d: string;
  h: string;
  a: string;
  k: string | null;
  cutoff: string;
  home: DescriptiveTeam;
  away: DescriptiveTeam;
  h2h: DescriptiveH2H;
};

export type DescriptiveFile = {
  schema_version: number;
  definitions_version: string;
  round_date: string;
  cutoff_date: string;
  note: string;
  definitions: Record<string, unknown>;
  fixtures: DescriptiveFixture[];
};

export type ProposedLeg = {
  d: string;
  h: string;
  a: string;
  k: string | null;
  m: string;
  pc: number;
  fair: number;
  odds: number;
  q?: number;
  cohort?: string;
};

export type ProposalConstruction = {
  policy: string;
  band: string;
  band_message?: string;
  band_low?: number | null;
  band_high?: number | null;
  floor?: number | null;
  achieved_odds?: number;
  individual_price_tier?: string;
  individual_price_min?: number;
  individual_floor_relaxed: boolean;
  individual_floor_message?: string;
  overlap_relaxed: boolean;
  overlap_message?: string;
  overlap_level?: string;
  method?: string;
  exact?: boolean;
  note?: string;
};

export type ProposedTicket = {
  type: 'best2' | 'around3' | 'around5';
  label: string;
  status: 'available' | 'unavailable';
  reason: string;
  flat_stake: number;
  legs: ProposedLeg[];
  combined_probability: number | null;
  combined_odds: number | null;
  model_ev?: number | null;
  construction?: ProposalConstruction;
  mel?: {
    stake: number; total_stake?: number; mandatory_exposure?: boolean;
    negative_ev?: boolean; message?: string; solver?: Record<string, unknown>;
    stress?: Record<string, unknown>; reason?: string;
  };
  policies?: Record<string, { stake: number }>;
  benchmarks?: Record<string, { stake: number }>;
  adaptive?: {
    stake: number;
    edge?: number | null;
    kelly_full?: number | null;
    kelly_quarter?: number | null;
    cap_applied?: boolean;
    reason?: string;
    policy?: string;
  };
};

export type ProposalRound = {
  schema_version: number;
  round_date: string;
  snapshot_identity: { round_date: string | null; fetched_at: string | null };
  policy: Record<string, unknown>;
  state_before: Record<string, number>;
  proposals: ProposedTicket[];
};

export type PrivateProposalsFile = { rounds: ProposalRound[] };

export type ProposalRoundRecord = {
  round_date: string;
  terminal: boolean;
  available: number;
  unavailable: number;
  pending: number;
  void: number;
  settled: number;
  flat_staked: number;
  flat_returned: number;
  flat_net: number;
  mel_staked: number;
  mel_returned: number;
  mel_net: number;
};

export type ProposalLedger = {
  staked: number;
  returned: number;
  net: number;
  roi: number | null;
};

export type ProposalRecordFile = {
  schema_version: number;
  policy_version: string;
  construction_version?: string;
  evaluation_id?: string;
  rounds: ProposalRoundRecord[];
  counts: {
    rounds: number; tickets: number; settled: number; pending: number;
    void: number; unavailable: number; unpriced: number; legacy_rounds?: number;
  };
  flat: ProposalLedger & { return_ci: [number | null, number | null]; ci_rounds: number };
  mel: ProposalLedger & {
    initial_bankroll: number; bankroll: number; peak: number;
    current_drawdown: number; maximum_drawdown: number; unresolved_exposure: number;
    return_ci: [number | null, number | null]; ci_rounds: number;
    series: { round_date: string; bankroll: number; terminal?: boolean; unresolved_exposure?: number }[];
  };
  benchmarks: Record<string, ProposalLedger & {
    initial_bankroll: number; bankroll: number; peak: number;
    current_drawdown: number; maximum_drawdown: number; unresolved_exposure: number;
    return_ci: [number | null, number | null]; ci_rounds: number;
  }>;
  types: Record<string, Record<string, number>>;
  note: string;
};

export type ReconstructionLeg = {
  d: string;
  h: string;
  a: string;
  k: string | null;
  m: string;
  label: string;
  group: string;
  pc: number;
  fair: number;
};

export type ReconstructionConstruction = {
  policy: string;
  algorithm: string;
  applied_later: boolean;
  band: string;
  band_message?: string;
  achieved_fair_odds?: number;
  individual_floor_relaxed: boolean;
  individual_floor_message?: string;
  overlap_relaxed: boolean;
  overlap_message?: string;
  method?: string;
  exact?: boolean;
  [key: string]: string | number | boolean | undefined;
};

export type ReconstructionProposal = {
  type: 'best2' | 'around3' | 'around5';
  label: string;
  status: 'available' | 'unavailable';
  reason: string;
  legs: ReconstructionLeg[];
  combined_probability: number | null;
  combined_fair_odds: number | null;
  construction: ReconstructionConstruction;
  settlement: {
    status: 'unavailable' | 'pending' | 'landed' | 'lost' | 'void' | 'not_reconstructed';
    source_pending: boolean;
    leg_statuses: string[];
  };
};

export type ReconstructionProvenance = {
  source_publication_commit: string;
  publication_time: string;
  rule_version: string;
  rule_source: string;
  prediction_input_hash: string;
  pool_hash: string;
  pricing_mode: string;
  pre_match_publication: boolean;
  current_fields_match: boolean;
  construction_version: string;
};

export type ReconstructionRound = {
  round_date: string;
  kind: string;
  pre_match_publication: boolean;
  disclaimer: string;
  example_disclaimer: string;
  pricing_note: string;
  pick_pool_count: number;
  provenance: ReconstructionProvenance;
  proposals: ReconstructionProposal[];
};

export type PublishedReconstructionFile = {
  schema_version: number;
  definition_version: string;
  pricing_mode: string;
  rounds: ReconstructionRound[];
  cumulative: {
    tickets: number; settled: number; landed: number; lost: number; void: number;
    pending: number; unavailable: number; not_reconstructed: number; source_pending: number;
  };
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

export type DataHealthRound = {
  date: string;
  label: string;
  kind: string;
  fixtures: number;
  settled_fixtures: number;
  pending_fixtures: number;
  rows: { total: number; settled: number; pending: number };
  sources: {
    football_data_fixtures: number; api_football_fixtures: number; unknown_fixtures: number;
    football_data_rows: number; api_football_rows: number; unknown_rows: number;
  };
  fallback: {
    attempted: boolean; fetched_at?: string | null; requests?: number | null;
    final_count?: number | null; matched?: number; ambiguous?: number; unmatched?: number;
    reason?: string;
  };
  pending_reasons: {
    source_pending_fixtures: number; ambiguous_fixtures: number; unmatched_fixtures: number;
    source_pending_sample: string[];
  };
  next_retry: string;
};

export type DataHealthFile = {
  schema_version: number;
  latest_football_data_result_date: string | null;
  unsettled_rounds: DataHealthRound[];
};

export type ForwardProposalsFile = {
  schema_version: number;
  activation_date: string;
  policy_version: string;
  construction_version: string;
  evaluation_id?: string;
  eligible_round: string | null;
  evaluation_start_round?: string | null;
  state: string;
  errors: string[];
  rounds_with_proposals: number;
  legacy_rounds?: number;
  counts: {
    tickets: number; available: number; unavailable: number;
    bands: Record<string, number>;
    individual_floor_relaxed: number; overlap_relaxed: number;
    negative_model_ev: number; negative_model_ev_share: number | null;
    search_methods: Record<string, number>;
  };
  price_coverage: {
    snapshot_rounds: number; fixtures: number; priced_fixtures: number; priced_markets: number;
    started_not_priced: number; unmatched_fixtures: number;
  };
  results: {
    source: string;
    counts: Record<string, number>;
    flat: Record<string, number | null>;
    mel: Record<string, number | null>;
    types: Record<string, Record<string, number>>;
    note: string;
    has_settled_data: boolean;
  };
};

export type PreregistrationFile = {
  schema_version: number;
  construction_version: string;
  policy_version: string;
  proposal_schema_version: number;
  activation_date: string;
  primary_comparison: string[];
  exploratory: string[];
  protocol: Record<string, string | number | boolean | Record<string, string | number>>;
  research_note: string;
  version_rule: string;
  [key: string]: unknown;
};

export type ForwardValidationSeries = {
  terminal_rounds: number;
  staked: number;
  returned: number;
  net: number;
  roi: number | null;
  bankroll: number;
  peak: number;
  maximum_drawdown: number;
  losing_round_frequency: number | null;
  unresolved_exposure?: number;
  round_log_growth: number[];
  bootstrap: { rounds: number; roi_ci: [number | null, number | null]; log_growth_ci: [number | null, number | null]; max_drawdown_ci?: [number | null, number | null]; unresolved_exposure_ci?: [number | null, number | null]; mean_log_growth: number | null };
};

export type ForwardValidationFile = {
  schema_version: number;
  state: string;
  counts: { rounds: number; terminal_rounds: number; tickets: number; void: number; pending: number; void_frequency?: number | null; pending_frequency?: number | null };
  primary: { flat: ForwardValidationSeries; mel: ForwardValidationSeries };
  exploratory: Record<string, { terminal_rounds: number; roi: number | null; maximum_drawdown: number }>;
  exposure: { by_type_mel_stake: Record<string, number>; fixtures: number; shared_leg_instances: number; shared_leg_tickets: number };
  fallbacks: Record<string, number | null>;
  power: { n_star: number | null; reason?: string; observed_rounds?: number; observed_sd?: number; meaningful_log_growth?: number; alpha_one_sided?: number; power?: number; source?: string };
  evidence: { n_star: number | null; settled_playable_rounds: number; lower_95_log_growth: number | null; positive: boolean; inconclusive: boolean; rule: string; no_early_efficacy_stopping: boolean };
  safety: { maximum_drawdown: number; drawdown_review: boolean; identity_failure: boolean; ruin_upper_95: number | null; stop_adaptive: boolean; owner_loss_budget?: number | null };
  protocol: Record<string, string | number | boolean | Record<string, string | number>>;
  notes: string[];
  small_sample?: boolean;
  multiple_comparisons?: string;
  bootstrap: { unit: string; resamples: number; seed: number };
};

export type DailyBestBand = { low: number; high: number };

export type DailyBestFrozenRow = {
  d: string; h: string; a: string; m: string; k?: string | null;
  pc: number; fair: number; odds: number; group: string;
};

export type DailyBestFrozenRound = {
  schema_version: number;
  rule_version: string;
  activation_marker: string;
  round_date: string;
  snapshot_identity: { round_date: string | null; fetched_at: string | null };
  band: DailyBestBand;
  min_odds: number;
  limit: number;
  eligible_counts: { fixtures: number; in_band: number; outside: number; rejected: number };
  selected: number;
  in_band_selected: number;
  fallback_selected: number;
  rows: DailyBestFrozenRow[];
};

export type DailyBestActivation = {
  schema_version: number;
  marker: string;
  rule_version: string;
  activation_date: string;
  activated_round: string;
  snapshot_identity?: { round_date: string | null; fetched_at: string | null };
};

export type DailyBestPrivateFile = {
  activation: DailyBestActivation | null;
  rounds: DailyBestFrozenRound[];
};

export type DailyBestStats = {
  selected: number; settled: number; landed: number; lost: number; void: number; pending: number;
  staked: number; returned: number; net: number; roi: number | null;
};

export type DailyBestRecordRow = {
  d: string; h: string; a: string; m: string; pc: number; group: string; in_band: boolean; st: string;
};

export type DailyBestRoundRecord = {
  round_date: string;
  snapshot_identity?: { round_date: string | null; fetched_at: string | null };
  selected: number; settled: number; landed: number; lost: number; void: number; pending: number;
  expected_landed: number; expected_landed_settled: number;
  staked: number; returned: number; net: number; roi: number | null;
  pending_exposure: number;
  state: 'unavailable' | 'pending' | 'partial' | 'settled';
  terminal: boolean;
  round_data_available: boolean;
  source_pending: boolean;
  in_band_selected: number; fallback_selected: number;
  eligible_counts: { fixtures: number; in_band: number; outside: number; rejected: number };
  by_group: Record<string, DailyBestStats>;
  band_split: Record<'in_band' | 'fallback', DailyBestStats>;
  rows: DailyBestRecordRow[];
};

export type DailyBestCumulative = {
  selected: number; settled: number; landed: number; lost: number; void: number; pending: number;
  expected_landed: number; expected_landed_settled: number;
  staked: number; returned: number; net: number; roi: number | null;
  pending_exposure: number;
  settled_rounds: number; terminal_rounds: number;
  settled_forward_rows: number;
  return_ci: [number | null, number | null];
  interval_state: string;
  in_band_selected: number; fallback_selected: number;
  by_group: Record<string, DailyBestStats>;
  band_split: Record<'in_band' | 'fallback', DailyBestStats>;
  mean_actual_odds: number | null; median_actual_odds: number | null; mean_model_ev: number | null;
  odds_aggregate_state: string;
};

export type DailyBestRecordFile = {
  schema_version: number;
  rule_version: string;
  activation_marker: string;
  band: DailyBestBand;
  min_odds: number;
  limit: number;
  activation: DailyBestActivation | null;
  rounds: DailyBestRoundRecord[];
  cumulative: DailyBestCumulative;
  note: string;
  prices_published: boolean;
};

