// Mirror of pipeline/vetting.py for the live dashboard.

export type VettingRule = Record<string, number | boolean | undefined>;

export type VettingCandidate = {
  probability: number;
  modelProbability: number;
  leagueRate: number;
  leagueN: number;
  homeRate: number;
  homeN: number;
  awayRate: number;
  awayN: number;
  fairOdds: number;
  countsProbability?: number | null;
  homeForm?: number | null;
  awayForm?: number | null;
  mozzartOdds?: number | null;
  bookmakerDisagreement?: number | null;
  bookmakerP80?: number | null;
  xgFor?: number | null;
  xgAgainst?: number | null;
  leagueXg?: number | null;
  betDirection?: string;
  divisionMatches?: number;
  daysSinceHome?: number | null;
  daysSinceAway?: number | null;
  divisionGap?: number | null;
};

export type VettingCheck = { id: string; label: string; passed: boolean; value: string; flag?: boolean };

export const DEFAULT_RULE: VettingRule = {
  c1: 0.45, c2: true, c3: true, c4: true, c5: false, c6: true, c7: true,
  c8: false, c9: false, c10: false, c11: false, c12: false,
};

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

export function evaluateCandidate(candidate: VettingCandidate, rule: VettingRule = DEFAULT_RULE): { passed: boolean; checks: VettingCheck[] } {
  const checks: VettingCheck[] = [];
  const add = (id: string, label: string, passed: boolean, value: string) => checks.push({ id, label, passed, value });

  const threshold = rule.c1 === false ? null : Number(rule.c1 ?? 0.45);
  if (threshold !== null) add('c1', 'Prob', candidate.probability >= threshold, `${pct(candidate.probability)} >= ${pct(threshold)}`);
  if (rule.c2) {
    const target = candidate.leagueRate + 0.05;
    add('c2', 'vs usual', candidate.probability >= target, `${pct(candidate.probability)} vs ${pct(target)}`);
  }
  if (rule.c3) {
    const passed = candidate.homeN >= 8 && candidate.awayN >= 8
      && candidate.homeRate >= candidate.leagueRate && candidate.awayRate >= candidate.leagueRate;
    add('c3', 'Team records', passed, `home ${pct(candidate.homeRate)}/${candidate.homeN}, away ${pct(candidate.awayRate)}/${candidate.awayN}`);
  }
  if (rule.c4) {
    const gap = candidate.countsProbability == null ? null : Math.abs(candidate.modelProbability - candidate.countsProbability);
    add('c4', 'Agreement', gap !== null && gap <= 0.10, gap === null ? 'no counts' : `gap ${(gap * 100).toFixed(1)} pts`);
  }
  if (rule.c5) {
    const passed = candidate.homeForm != null && candidate.awayForm != null
      && candidate.homeForm >= candidate.leagueRate && candidate.awayForm >= candidate.leagueRate;
    add('c5', 'Form', passed, candidate.homeForm == null ? 'no form' : `${pct(candidate.homeForm)}/${pct(candidate.awayForm as number)}`);
  }
  if (rule.c6) add('c6', 'Fair', candidate.fairOdds >= 1.40, `fair ${candidate.fairOdds.toFixed(2)}`);
  if (rule.c8) {
    const passed = candidate.bookmakerDisagreement != null && candidate.bookmakerP80 != null
      && candidate.bookmakerDisagreement <= candidate.bookmakerP80;
    add('c8', 'Book spread', passed, candidate.bookmakerDisagreement == null ? 'no spread' : pct(candidate.bookmakerDisagreement));
  }
  if (rule.c10) add('c10', 'Promoted', (candidate.divisionMatches ?? 999) >= 8, `${candidate.divisionMatches ?? 999} matches`);
  if (rule.c11) {
    const days = [candidate.daysSinceHome, candidate.daysSinceAway].filter((value): value is number => value != null);
    add('c11', 'Rest', days.length > 0 && Math.min(...days) >= 3, days.length ? `${Math.min(...days)}d` : 'no rest');
  }
  if (rule.c12) add('c12', 'Break', candidate.divisionGap != null && candidate.divisionGap < 10, candidate.divisionGap == null ? 'no gap' : `${candidate.divisionGap}d`);

  const passed = checks.every((check) => check.passed);
  if (rule.c7) {
    const flagged = candidate.mozzartOdds != null && candidate.mozzartOdds >= candidate.fairOdds;
    checks.push({
      id: 'c7',
      label: 'Mozzart',
      passed: flagged,
      value: candidate.mozzartOdds == null ? 'no price' : `${candidate.mozzartOdds.toFixed(2)} vs ${candidate.fairOdds.toFixed(2)}`,
      flag: true,
    });
  }
  return { passed, checks };
}
