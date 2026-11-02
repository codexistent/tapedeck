import Link from "next/link";
import { notFound } from "next/navigation";

import { ago, money } from "@/components/format";
import { Sparkline } from "@/components/Sparkline";
import { requireMember } from "@/lib/auth";
import { caseTrends, projectBySlug, runsForProject, unstable } from "@/lib/data";
import { plan } from "@/lib/plans";

export default async function ProjectPage({ params }: { params: Promise<{ org: string; project: string }> }) {
  const { org: orgSlug, project: projectSlug } = await params;
  const { org } = await requireMember(orgSlug);
  const project = await projectBySlug(org.id, projectSlug);
  if (!project) notFound();

  const [runs, trends] = await Promise.all([
    runsForProject(project.id, org.plan),
    caseTrends(project.id, org.plan),
  ]);
  const shaky = unstable(trends);
  const base = `/o/${org.slug}/p/${project.slug}`;
  const isTeam = org.plan !== "free";

  return (
    <div className="stack">
      <div className="spread">
        <div>
          <h1>{project.name}</h1>
          <p className="muted small">Showing the last {plan(org.plan).historyDays} days on the {plan(org.plan).name} plan.</p>
        </div>
        <Link className="btn" href={`${base}/settings`}>Settings &amp; tokens</Link>
      </div>

      {runs.length === 0 ? (
        <div className="card empty">
          <h2>No runs yet</h2>
          <p className="muted">Create a token in <Link href={`${base}/settings`}>settings</Link>, then run <code>tapedeck test --upload</code> in CI.</p>
        </div>
      ) : (
        <>
          <section className="stack">
            <h2>Runs</h2>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr><th>When</th><th>Change</th><th>Result</th><th className="hide-sm">Model</th><th className="hide-sm">Cost</th></tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id}>
                      <td><Link href={`${base}/runs/${r.id}`}>{ago(r.created_at)}</Link></td>
                      <td className="small">
                        {r.pr_number ? <span>PR #{r.pr_number}</span> : <span className="mono">{r.branch ?? "local"}</span>}
                        {r.commit_sha && <span className="faint mono"> · {r.commit_sha.slice(0, 7)}</span>}
                        {r.prompt_label && <div className="faint mono">{r.prompt_label}</div>}
                      </td>
                      <td>
                        {r.passed ? <span className="pill good">no regressions</span>
                          : <span className="pill bad">{r.regressed_count} regressed</span>}
                        {r.error_count > 0 && <span className="pill warn" style={{ marginLeft: 6 }}>{r.error_count} crashed</span>}
                      </td>
                      <td className="hide-sm mono small">{r.model}</td>
                      <td className="hide-sm num">{money(r.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="stack">
            <h2>Case pass rates</h2>
            <p className="muted small">Candidate pass rate per case across recent runs, oldest to newest. Red dots mark runs where the case regressed.</p>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Case</th><th>Trend</th><th>Latest</th></tr></thead>
                <tbody>
                  {trends.map((t) => {
                    const last = t.points[t.points.length - 1];
                    return (
                      <tr key={t.case_id}>
                        <td className="mono small">{t.case_id}</td>
                        <td><Sparkline points={t.points} label={`${t.case_id} pass rate over ${t.points.length} runs`} /></td>
                        <td className="num">{Math.round(last.rate * 100)}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card stack">
            <h2>Unstable cases</h2>
            {!isTeam ? (
              <p className="muted">Flaky-case detection across runs is part of Team. <Link href={`/o/${org.slug}/billing`}>Upgrade</Link></p>
            ) : shaky.length === 0 ? (
              <p className="muted">No unstable cases. A case shows up here when its pass rate swings by 30 points or more across recent runs, which usually means an ambiguous task or a flaky check.</p>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {shaky.map((t) => (
                  <li key={t.case_id}><span className="mono">{t.case_id}</span> <span className="muted">swings {Math.round(t.spread * 100)} points across {t.points.length} runs</span></li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
