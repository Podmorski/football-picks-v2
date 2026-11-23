import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const DATA = join(process.cwd(), 'public', 'data');
const PRICES_OUT = join(DATA, 'mozzart-prices.json');
const RECORD_OUT = join(DATA, 'mozzart-record.json');
const VETTED_OUT = join(DATA, 'mozzart-vetted-record.json');
const STATUS_OUT = join(DATA, 'mozzart-status.json');
const PROPOSALS_OUT = join(DATA, 'proposed-tickets-private.json');
const DAILY_BEST_OUT = join(DATA, 'daily-best-private.json');
const PROPOSAL_ACTIVATION_DATE = '2026-11-24';

function clean() {
  for (const path of [PRICES_OUT, RECORD_OUT, VETTED_OUT, STATUS_OUT, PROPOSALS_OUT, DAILY_BEST_OUT]) {
    try {
      if (existsSync(path)) rmSync(path);
    } catch {
      // best effort
    }
  }
}

if (process.env.PRICED !== '1') {
  clean();
  console.log('prices: PRICED not set; serving without Mozzart prices');
  process.exit(0);
}

const key = process.env.PRICES_SSH_KEY;
const localDir = process.env.PRICES_LOCAL_DIR;
const repo = process.env.PRICES_REPO || 'Podmorski/football-picks-prices';
if (!localDir && !key) {
  clean();
  console.log('prices: PRICES_SSH_KEY missing; serving without Mozzart prices');
  process.exit(0);
}

let workdir;
let cloneDir;
try {
  if (localDir) {
    cloneDir = localDir;
  } else {
    workdir = mkdtempSync(join(tmpdir(), 'prices-'));
    const keyFile = join(workdir, 'deploy_key');
    writeFileSync(keyFile, key, { mode: 0o600 });
    cloneDir = join(workdir, 'repo');
    const ssh = 'ssh -i ' + keyFile + ' -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes';
    const url = 'ssh://git@ssh.github.com:443/' + repo + '.git';
    execFileSync('git', ['clone', '--depth', '1', url, cloneDir], {
      stdio: ['ignore', 'ignore', 'inherit'],
      env: { ...process.env, GIT_SSH_COMMAND: ssh },
    });
  }
  const roundsDir = join(cloneDir, 'rounds');
  const rounds = existsSync(roundsDir)
    ? readdirSync(roundsDir)
        .filter((name) => name.endsWith('.json'))
        .sort()
        .map((name) => JSON.parse(readFileSync(join(roundsDir, name), 'utf8')))
    : [];
  mkdirSync(DATA, { recursive: true });
  writeFileSync(PRICES_OUT, JSON.stringify({ rounds }));
  const proposalsDir = join(cloneDir, 'proposals');
  const proposals = existsSync(proposalsDir)
    ? readdirSync(proposalsDir)
        .filter((name) => name.endsWith('.json'))
        .sort()
        .map((name) => JSON.parse(readFileSync(join(proposalsDir, name), 'utf8')))
    : [];
  const validProposalDates = new Set(
    proposals
      .filter((round) => {
        const types = new Set((round.proposals ?? []).map((item) => item.type));
        return Number(round.schema_version ?? 0) >= 2 && types.size === 3 && ['best2', 'around3', 'around5'].every((type) => types.has(type));
      })
      .map((round) => round.round_date),
  );
  const missingProposals = rounds
    .filter((snapshot) => String(snapshot.round_date ?? '') >= PROPOSAL_ACTIVATION_DATE && (snapshot.fixtures ?? []).length > 0)
    .map((snapshot) => snapshot.round_date)
    .filter((date) => !validProposalDates.has(date));
  if (missingProposals.length > 0) {
    throw new Error(
      'required frozen proposal data missing for snapshot round(s): ' + missingProposals.join(', ') +
      ' (activation ' + PROPOSAL_ACTIVATION_DATE + ')',
    );
  }
  writeFileSync(PROPOSALS_OUT, JSON.stringify({ rounds: proposals }));
  const dailyBestDir = join(cloneDir, 'daily-best');
  const dailyBest = existsSync(dailyBestDir)
    ? readdirSync(dailyBestDir)
        .filter((name) => name.endsWith('.json') && name !== 'activation.json')
        .sort()
        .map((name) => JSON.parse(readFileSync(join(dailyBestDir, name), 'utf8')))
    : [];
  const activationPath = join(dailyBestDir, 'activation.json');
  const rawActivation = existsSync(activationPath)
    ? JSON.parse(readFileSync(activationPath, 'utf8'))
    : null;
  const dailyBestActivation = rawActivation && rawActivation.marker === 'daily-best-v1' ? rawActivation : null;
  const validDailyBest = new Set(
    dailyBest
      .filter((round) => round.rule_version === 'daily-best-v1' && round.round_date && Array.isArray(round.rows))
      .map((round) => round.round_date),
  );
  const activatedRound = dailyBestActivation?.activated_round ? String(dailyBestActivation.activated_round) : null;
  const missingDailyBest = activatedRound
    ? rounds
        .filter((snapshot) => String(snapshot.round_date ?? '') >= activatedRound && (snapshot.fixtures ?? []).length > 0)
        .map((snapshot) => snapshot.round_date)
        .filter((date) => !validDailyBest.has(date))
    : [];
  if (missingDailyBest.length > 0) {
    throw new Error(
      'required frozen Daily best data missing for snapshot round(s): ' + missingDailyBest.join(', ') +
      ' (marker daily-best-v1, activated ' + activatedRound + ')',
    );
  }
  writeFileSync(DAILY_BEST_OUT, JSON.stringify({ activation: dailyBestActivation, rounds: dailyBest }));
  const recordPath = join(cloneDir, 'record.json');
  if (existsSync(recordPath)) writeFileSync(RECORD_OUT, readFileSync(recordPath));
  const vettedPath = join(cloneDir, 'vetted-record.json');
  if (existsSync(vettedPath)) writeFileSync(VETTED_OUT, readFileSync(vettedPath));
  const usagePath = join(cloneDir, 'usage.json');
  const usage = existsSync(usagePath) ? JSON.parse(readFileSync(usagePath, 'utf8')) : null;
  const entries = Array.isArray(usage?.entries) ? usage.entries : [];
  const lastEntry = entries.length ? entries[entries.length - 1] : null;
  const inferredRun = lastEntry
    ? {
        at: lastEntry.timestamp ?? null,
        ok: true,
        note: lastEntry.note ?? `last usage entry (status ${lastEntry.status ?? 'n/a'})`,
      }
    : null;
  const statusRounds = rounds
    .map((snap) => {
      const priced = (snap.fixtures ?? []).length;
      const started = (snap.started_not_priced ?? []).length;
      return {
        round_date: snap.round_date,
        last_fetch: snap.fetched_at ?? null,
        priced,
        started,
        matched: priced + started,
        unmatched: (snap.unmatched_fixtures ?? []).length,
      };
    })
    .sort((a, b) => String(a.round_date).localeCompare(String(b.round_date)));
  writeFileSync(
    STATUS_OUT,
    JSON.stringify({
      rounds: statusRounds,
      usage: usage ? { month: usage.month ?? null, used: Number(usage.used ?? 0), cap: 90 } : null,
      last_run: usage?.last_run ?? inferredRun,
    }),
  );
  console.log(
    'prices: embedded ' + rounds.length + ' round snapshot(s), ' + proposals.length +
    ' proposal round(s) and ' + dailyBest.length + ' frozen Daily best round(s)',
  );
} catch (error) {
  clean();
  // A priced build must never fall back to an unpriced one: throw so Vercel
  // keeps the previous successful (priced) deployment live.
  throw new Error(
    'prices: could not read the private store, refusing to publish an unpriced build: ' +
      (error && error.message ? error.message : error),
  );
} finally {
  if (workdir) {
    try {
      rmSync(workdir, { recursive: true, force: true });
    } catch {
      // best effort
    }
  }
}
