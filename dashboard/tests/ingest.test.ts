import { beforeEach, describe, expect, it } from "vitest";

import "./setup";
import { resetDb } from "./setup";

import { POST } from "@/app/api/v1/runs/route";
import { onSignIn, orgsForUser } from "@/lib/accounts";
import { caseResults, caseTrends, runsForProject, unstable } from "@/lib/data";
import { one, query } from "@/lib/db";
import { newToken } from "@/lib/tokens";

async function project(): Promise<{ projectId: string; token: string }> {
  const user = await onSignIn({ githubId: 7, login: "pearl" });
  const [org] = await orgsForUser(user.id);
  const p = await one<{ id: string }>(
    `insert into projects (org_id, slug, name) values ($1, 'agent', 'agent') returning id`,
    [org.id],
  );
  const t = newToken();
  await query(`insert into api_tokens (project_id, name, prefix, token_hash) values ($1,'ci',$2,$3)`, [
    p!.id, t.prefix, t.hash,
  ]);
  return { projectId: p!.id, token: t.token };
}

function upload(overrides: Record<string, unknown> = {}) {
  return {
    tapedeck_upload: 1,
    passed: false,
    model: "openai/gpt-5-mini",
    prompt_label: "broken.txt",
    prompt_sha: "abc",
    baseline_prompt_sha: "def",
    runs_per_case: 10,
    alpha: 0.05,
    min_effect: 0.2,
    cost_usd: 0.12,
    error_count: 0,
    commit_sha: "0123456789abcdef",
    branch: "feature/x",
    pr_number: 42,
    cases: [
      { case: "trap", baseline: { passes: 10, n: 10 }, candidate: { passes: 1, n: 10 },
        p_adjusted: 0.0005, regressed: true, explanation: "Candidate added a call", failing_check: "never_called" },
      { case: "ok", baseline: { passes: 10, n: 10 }, candidate: { passes: 10, n: 10 },
        p_adjusted: 1, regressed: false },
    ],
    ...overrides,
  };
}

function post(body: unknown, token?: string) {
  return POST(
    new Request("http://localhost/api/v1/runs", {
      method: "POST",
      headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
      body: typeof body === "string" ? body : JSON.stringify(body),
    }),
  );
}

beforeEach(resetDb);

describe("POST /api/v1/runs", () => {
  it("stores a run and returns its dashboard URL", async () => {
    const { projectId, token } = await project();
    const res = await post(upload(), token);
    expect(res.status).toBe(201);
    const json = (await res.json()) as { id: string; url: string };
    expect(json.url).toMatch(/\/o\/pearl\/p\/agent\/runs\/\d+$/);
    const [run] = await runsForProject(projectId, "free");
    expect(run).toMatchObject({ passed: false, regressed_count: 1, case_count: 2, pr_number: 42 });
    const cases = await caseResults(run.id);
    expect(cases[0]).toMatchObject({ case_id: "trap", regressed: true, cand_passes: 1 });
    const used = await one<{ last_used_at: Date | null }>(`select last_used_at from api_tokens`);
    expect(used?.last_used_at).not.toBeNull();
  });

  it("rejects missing, unknown and revoked tokens", async () => {
    const { token } = await project();
    expect((await post(upload())).status).toBe(401);
    expect((await post(upload(), "tdk_nope")).status).toBe(401);
    await query(`update api_tokens set revoked_at = now()`);
    expect((await post(upload(), token)).status).toBe(401);
  });

  it("validates the payload with a useful message", async () => {
    const { token } = await project();
    expect((await post("{not json", token)).status).toBe(400);
    const bad = await post(upload({ cases: [{ case: "x", baseline: { passes: 11, n: 10 },
      candidate: { passes: 1, n: 10 }, p_adjusted: 0.5, regressed: false }] }), token);
    expect(bad.status).toBe(422);
    expect(((await bad.json()) as { error: string }).error).toContain("passes cannot exceed n");
    expect((await post(upload({ tapedeck_upload: 2 }), token)).status).toBe(422);
  });

  it("hides runs older than the plan's history window", async () => {
    const { projectId, token } = await project();
    await post(upload(), token);
    await query(`update runs set created_at = now() - interval '30 days'`);
    expect(await runsForProject(projectId, "free")).toHaveLength(0);
    expect(await runsForProject(projectId, "team")).toHaveLength(1);
  });

  it("builds per-case trends and flags unstable cases", async () => {
    const { projectId, token } = await project();
    for (const passes of [10, 3, 9, 2]) {
      await post(upload({ passed: true, cases: [
        { case: "flaky", baseline: { passes: 10, n: 10 }, candidate: { passes, n: 10 }, p_adjusted: 1, regressed: false },
        { case: "steady", baseline: { passes: 10, n: 10 }, candidate: { passes: 10, n: 10 }, p_adjusted: 1, regressed: false },
      ] }), token);
    }
    const trends = await caseTrends(projectId, "team");
    expect(trends.find((t) => t.case_id === "flaky")?.points.map((p) => p.rate)).toEqual([1, 0.3, 0.9, 0.2]);
    expect(unstable(trends).map((t) => t.case_id)).toEqual(["flaky"]);
  });
});
