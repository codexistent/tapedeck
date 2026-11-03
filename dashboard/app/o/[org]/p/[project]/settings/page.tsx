import Link from "next/link";
import { notFound } from "next/navigation";

import { createTokenAction, revokeTokenAction } from "@/app/actions";
import { ago } from "@/components/format";
import { TokenForm } from "@/components/forms";
import { requireMember } from "@/lib/auth";
import { projectBySlug, tokensForProject } from "@/lib/data";

const API_URL = process.env.NEXTAUTH_URL ?? "https://your-tapedeck-domain";

export default async function Settings({
  params,
  searchParams,
}: {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ new?: string }>;
}) {
  const { org: orgSlug, project: projectSlug } = await params;
  const { new: isNew } = await searchParams;
  const { org } = await requireMember(orgSlug);
  const project = await projectBySlug(org.id, projectSlug);
  if (!project) notFound();
  const tokens = await tokensForProject(project.id);

  return (
    <div className="stack">
      <p className="small"><Link href={`/o/${org.slug}/p/${project.slug}`}>← {project.name}</Link></p>
      <h1>Settings</h1>
      {isNew && <div className="notice good">Project created. Make a token below and add it to CI.</div>}

      <section className="card stack">
        <h2>API tokens</h2>
        <p className="muted small">Tokens let CI upload results to this project. Store one as a repository secret named <code>TAPEDECK_TOKEN</code>.</p>
        <TokenForm action={createTokenAction} org={org.slug} project={project.slug} />
        {tokens.length > 0 && (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Name</th><th>Token</th><th className="hide-sm">Last used</th><th /></tr></thead>
              <tbody>
                {tokens.map((t) => (
                  <tr key={t.id}>
                    <td>{t.name}</td>
                    <td className="mono small">{t.prefix}…</td>
                    <td className="hide-sm muted small">{t.last_used_at ? ago(t.last_used_at) : "never"}</td>
                    <td style={{ textAlign: "right" }}>
                      <form action={revokeTokenAction}>
                        <input type="hidden" name="org" value={org.slug} />
                        <input type="hidden" name="project" value={project.slug} />
                        <input type="hidden" name="token" value={t.id} />
                        <button className="btn danger" type="submit">Revoke</button>
                      </form>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card stack">
        <div className="spread"><h2>Connect CI</h2><Link href="/docs#token">Full step-by-step guide →</Link></div>
        <p className="muted small">
          Save the token as a repository secret named <code>TAPEDECK_TOKEN</code> (GitHub repo → Settings →
          Secrets and variables → Actions). Your agent&apos;s own model key goes in as a secret too: replays run
          your agent, so Tapedeck never needs a key of its own. Only results are uploaded; tapes stay in your repo.
        </p>
        <pre className="code">{`# .github/workflows/tapedeck.yml
on: pull_request
permissions: { contents: read, pull-requests: write }
jobs:
  tapedeck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: codexistent/tapedeck@v0.2.0
        env:
          TAPEDECK_TOKEN: \${{ secrets.TAPEDECK_TOKEN }}
          TAPEDECK_URL: ${API_URL}
          OPENAI_API_KEY: \${{ secrets.OPENAI_API_KEY }}  # your agent's model key
        with:
          config: tapedeck.yaml`}</pre>
        <p className="muted small">Or from a terminal: <code>TAPEDECK_TOKEN=tdk_… TAPEDECK_URL={API_URL} tapedeck test --upload</code></p>
      </section>
    </div>
  );
}
