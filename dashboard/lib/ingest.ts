import { z } from "zod";

import { one, tx } from "./db";
import { hashToken } from "./tokens";

const counts = z.object({
  passes: z.number().int().min(0),
  n: z.number().int().min(0).max(10_000),
});

export const caseSchema = z
  .object({
    case: z.string().min(1).max(200),
    baseline: counts,
    candidate: counts,
    p_adjusted: z.number().min(0).max(1),
    regressed: z.boolean(),
    explanation: z.string().max(2000).nullish(),
    failing_check: z.string().max(2000).nullish(),
  })
  .refine((c) => c.baseline.passes <= c.baseline.n && c.candidate.passes <= c.candidate.n, {
    message: "passes cannot exceed n",
  });

/** What `tapedeck test --upload` sends. Results only: tapes never leave the repo. */
export const runSchema = z.object({
  tapedeck_upload: z.literal(1),
  passed: z.boolean(),
  model: z.string().min(1).max(200),
  prompt_label: z.string().max(200).nullish(),
  prompt_sha: z.string().max(64).nullish(),
  baseline_prompt_sha: z.string().max(64).nullish(),
  runs_per_case: z.number().int().min(1).max(10_000),
  alpha: z.number().gt(0).lt(1),
  min_effect: z.number().min(0).max(1),
  cost_usd: z.number().min(0).max(1_000_000).default(0),
  error_count: z.number().int().min(0).default(0),
  commit_sha: z.string().max(64).nullish(),
  branch: z.string().max(255).nullish(),
  pr_number: z.number().int().positive().nullish(),
  cases: z.array(caseSchema).min(1).max(2000),
});

export type RunUpload = z.infer<typeof runSchema>;

export interface TokenOwner {
  token_id: string;
  project_id: string;
  project_slug: string;
  org_slug: string;
}

/** Resolve a bearer token to its project, or null if unknown or revoked. */
export async function authenticate(token: string): Promise<TokenOwner | null> {
  return one<TokenOwner>(
    `update api_tokens t set last_used_at = now()
       from projects p join orgs o on o.id = p.org_id
      where t.project_id = p.id and t.token_hash = $1 and t.revoked_at is null
      returning t.id as token_id, p.id as project_id, p.slug as project_slug,
                o.slug as org_slug`,
    [hashToken(token)],
  );
}

export async function insertRun(projectId: string, run: RunUpload): Promise<string> {
  return tx(async (client) => {
    const regressed = run.cases.filter((c) => c.regressed).length;
    const { rows } = await client.query<{ id: string }>(
      `insert into runs (project_id, passed, commit_sha, branch, pr_number, model,
         prompt_label, prompt_sha, baseline_prompt_sha, runs_per_case, alpha, min_effect,
         cost_usd, error_count, case_count, regressed_count)
       values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
       returning id`,
      [projectId, run.passed, run.commit_sha ?? null, run.branch ?? null, run.pr_number ?? null,
        run.model, run.prompt_label ?? null, run.prompt_sha ?? null,
        run.baseline_prompt_sha ?? null, run.runs_per_case, run.alpha, run.min_effect,
        run.cost_usd, run.error_count, run.cases.length, regressed],
    );
    const runId = rows[0].id;
    const seen = new Set<string>();
    for (const c of run.cases) {
      if (seen.has(c.case)) continue; // first entry wins on duplicate case ids
      seen.add(c.case);
      await client.query(
        `insert into case_results (run_id, case_id, base_passes, base_n, cand_passes, cand_n,
           p_adjusted, regressed, explanation, failing_check)
         values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
        [runId, c.case, c.baseline.passes, c.baseline.n, c.candidate.passes, c.candidate.n,
          c.p_adjusted, c.regressed, c.explanation ?? null, c.failing_check ?? null],
      );
    }
    return runId;
  });
}

export const MAX_BODY_BYTES = 1_000_000;
