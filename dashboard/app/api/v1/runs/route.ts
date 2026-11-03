import { NextResponse } from "next/server";

import { authenticate, insertRun, MAX_BODY_BYTES, runSchema } from "@/lib/ingest";
import { bearer } from "@/lib/tokens";

export const runtime = "nodejs";

function error(status: number, message: string) {
  return NextResponse.json({ error: message }, { status });
}

/** Receive one run's results from `tapedeck test --upload`. */
export async function POST(request: Request) {
  const token = bearer(request.headers.get("authorization"));
  if (!token) return error(401, "missing or malformed token: send Authorization: Bearer tdk_...");

  const owner = await authenticate(token);
  if (!owner) return error(401, "unknown or revoked token");

  const length = Number(request.headers.get("content-length") ?? "0");
  if (length > MAX_BODY_BYTES) return error(413, "payload too large");
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return error(413, "payload too large");

  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    return error(400, "body is not valid JSON");
  }
  const parsed = runSchema.safeParse(body);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    return error(422, `invalid upload at ${issue.path.join(".") || "(root)"}: ${issue.message}`);
  }

  const runId = await insertRun(owner.project_id, parsed.data);
  const base = process.env.NEXTAUTH_URL ?? new URL(request.url).origin;
  return NextResponse.json(
    {
      id: runId,
      url: `${base}/o/${owner.org_slug}/p/${owner.project_slug}/runs/${runId}`,
    },
    { status: 201 },
  );
}
