import Link from "next/link";
import { notFound } from "next/navigation";

import { money, pValue } from "@/components/format";
import { requireMember } from "@/lib/auth";
import { caseResults, projectBySlug, runById } from "@/lib/data";

export default async function RunPage({
  params,
}: {
  params: Promise<{ org: string; project: string; id: string }>;
}) {
  const { org: orgSlug, project: projectSlug, id } = await params;
  const { org } = await requireMember(orgSlug);
  const project = await projectBySlug(org.id, projectSlug);
  if (!project) notFound();
  const run = await runById(project.id, id, org.plan);
  if (!run) notFound();
  const cases = await caseResults(run.id);
  const regressed = cases.filter((c) => c.regressed);

  return (
    <div className="stack">
      <p className="small"><Link href={`/o/${org.slug}/p/${project.slug}`}>← {project.name}</Link></p>
      <div className="spread">
        <h1>Run #{run.id}</h1>
        <span className="muted small">{new Date(run.created_at).toUTCString()}</span>
      </div>

      <div className={`notice ${run.passed ? "good" : "bad"}`}>
        <strong>{run.passed ? `✅ No regressions across ${run.case_count} cases` : `❌ ${run.regressed_count} regression${run.regressed_count === 1 ? "" : "s"} in ${run.case_count} cases`}</strong>
        {regressed.length > 0 && (
          <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
            {regressed.map((c) => (
              <li key={c.case_id}>
                <span className="mono">{c.case_id}</span>: {c.explanation}
                {c.failing_check && <div className="small" style={{ opacity: 0.85 }}>Example failing check: {c.failing_check}</div>}
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="muted small">
        {run.pr_number && <>PR #{run.pr_number} · </>}
        {run.branch && <><span className="mono">{run.branch}</span> · </>}
        {run.commit_sha && <><span className="mono">{run.commit_sha.slice(0, 7)}</span> · </>}
        model <span className="mono">{run.model}</span> · {run.runs_per_case} runs per case · alpha {run.alpha} with Holm correction · min effect {run.min_effect} · {money(run.cost_usd)}
        {run.error_count > 0 && <> · <span style={{ color: "var(--bad)" }}>{run.error_count} crashed runs</span></>}
      </p>

      <div className="table-scroll">
        <table>
          <thead><tr><th>Case</th><th>Baseline</th><th>Candidate</th><th>p (adj.)</th><th>Status</th></tr></thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.case_id} className={c.regressed ? "bad" : undefined}>
                <td className="mono small">{c.case_id}</td>
                <td className="num">{c.base_passes}/{c.base_n}</td>
                <td className="num">{c.cand_passes}/{c.cand_n}</td>
                <td className="num">{pValue(c.p_adjusted)}</td>
                <td>{c.regressed ? <span className="pill bad">regressed</span> : <span className="pill good">ok</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="faint small">Full trajectories stay in your repository; download the HTML report from the CI run for step-by-step detail.</p>
    </div>
  );
}
