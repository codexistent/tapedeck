import { one, query } from "./db";
import { plan } from "./plans";

export interface Project {
  id: string;
  org_id: string;
  slug: string;
  name: string;
  created_at: Date;
}

export interface RunRow {
  id: string;
  created_at: Date;
  passed: boolean;
  commit_sha: string | null;
  branch: string | null;
  pr_number: number | null;
  model: string;
  prompt_label: string | null;
  runs_per_case: number;
  alpha: number;
  min_effect: number;
  cost_usd: number;
  error_count: number;
  case_count: number;
  regressed_count: number;
}

export interface CaseResult {
  case_id: string;
  base_passes: number;
  base_n: number;
  cand_passes: number;
  cand_n: number;
  p_adjusted: number;
  regressed: boolean;
  explanation: string | null;
  failing_check: string | null;
}

export async function projectsForOrg(orgId: string): Promise<(Project & { last_run: Date | null; last_passed: boolean | null })[]> {
  return query(
    `select p.*, r.created_at as last_run, r.passed as last_passed
       from projects p
       left join lateral (
         select created_at, passed from runs where project_id = p.id
         order by created_at desc limit 1
       ) r on true
      where p.org_id = $1 order by p.created_at`,
    [orgId],
  );
}

export async function projectBySlug(orgId: string, slug: string): Promise<Project | null> {
  return one<Project>(`select * from projects where org_id = $1 and slug = $2`, [orgId, slug]);
}

export async function runsForProject(
  projectId: string,
  planId: string,
  limit = 100,
): Promise<RunRow[]> {
  return query<RunRow>(
    `select * from runs
      where project_id = $1 and created_at > now() - ($2 || ' days')::interval
      order by created_at desc limit $3`,
    [projectId, String(plan(planId).historyDays), limit],
  );
}

export async function runById(
  projectId: string,
  runId: string,
  planId: string,
): Promise<RunRow | null> {
  if (!/^\d+$/.test(runId)) return null;
  return one<RunRow>(
    `select * from runs where project_id = $1 and id = $2
        and created_at > now() - ($3 || ' days')::interval`,
    [projectId, runId, String(plan(planId).historyDays)],
  );
}

export async function caseResults(runId: string): Promise<CaseResult[]> {
  return query<CaseResult>(
    `select * from case_results where run_id = $1 order by regressed desc, case_id`,
    [runId],
  );
}

export interface CaseTrend {
  case_id: string;
  points: { run_id: string; at: Date; rate: number; regressed: boolean }[];
  mean: number;
  spread: number;
}

/**
 * Candidate pass rate per case across the most recent runs, oldest first.
 * A case is "unstable" when its rate moves a lot between runs; that usually
 * means an ambiguous task or a flaky verifier, not a real regression.
 */
export async function caseTrends(
  projectId: string,
  planId: string,
  lastRuns = 30,
): Promise<CaseTrend[]> {
  const rows = await query<{
    case_id: string;
    run_id: string;
    at: Date;
    cand_passes: number;
    cand_n: number;
    regressed: boolean;
  }>(
    `with recent as (
       select id, created_at from runs
        where project_id = $1 and created_at > now() - ($2 || ' days')::interval
        order by created_at desc limit $3
     )
     select c.case_id, c.run_id, r.created_at as at, c.cand_passes, c.cand_n, c.regressed
       from case_results c join recent r on r.id = c.run_id
      order by c.case_id, r.created_at`,
    [projectId, String(plan(planId).historyDays), lastRuns],
  );
  const byCase = new Map<string, CaseTrend["points"]>();
  for (const row of rows) {
    const points = byCase.get(row.case_id) ?? [];
    points.push({
      run_id: row.run_id,
      at: row.at,
      rate: row.cand_n ? row.cand_passes / row.cand_n : 0,
      regressed: row.regressed,
    });
    byCase.set(row.case_id, points);
  }
  return [...byCase.entries()].map(([case_id, points]) => {
    const rates = points.map((p) => p.rate);
    const mean = rates.reduce((a, b) => a + b, 0) / Math.max(1, rates.length);
    const spread = rates.length ? Math.max(...rates) - Math.min(...rates) : 0;
    return { case_id, points, mean, spread };
  });
}

export function unstable(trends: CaseTrend[]): CaseTrend[] {
  return trends
    .filter((t) => t.points.length >= 3 && t.spread >= 0.3)
    .sort((a, b) => b.spread - a.spread);
}

export interface TokenRow {
  id: string;
  name: string;
  prefix: string;
  created_at: Date;
  last_used_at: Date | null;
}

export async function tokensForProject(projectId: string): Promise<TokenRow[]> {
  return query<TokenRow>(
    `select id, name, prefix, created_at, last_used_at from api_tokens
      where project_id = $1 and revoked_at is null order by created_at desc`,
    [projectId],
  );
}

export interface MemberRow {
  user_id: string;
  login: string;
  name: string | null;
  avatar_url: string | null;
  role: string;
}

export async function members(orgId: string): Promise<MemberRow[]> {
  return query<MemberRow>(
    `select u.id as user_id, u.login, u.name, u.avatar_url, m.role
       from memberships m join users u on u.id = m.user_id
      where m.org_id = $1 order by m.role desc, u.login`,
    [orgId],
  );
}

export async function invites(orgId: string): Promise<{ id: string; github_login: string }[]> {
  return query(`select id, github_login from invites where org_id = $1 order by created_at`, [
    orgId,
  ]);
}
