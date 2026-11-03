import Link from "next/link";

import { createProjectAction } from "@/app/actions";
import { ago } from "@/components/format";
import { InlineForm } from "@/components/forms";
import { requireMember } from "@/lib/auth";
import { projectsForOrg } from "@/lib/data";
import { canAddProject, plan } from "@/lib/plans";

export default async function Projects({ params }: { params: Promise<{ org: string }> }) {
  const { org: slug } = await params;
  const { org } = await requireMember(slug);
  const projects = await projectsForOrg(org.id);
  const canAdd = canAddProject(org.plan, projects.length);

  return (
    <div className="stack">
      <div className="spread">
        <h1>Projects</h1>
      </div>

      {projects.length === 0 ? (
        <div className="card empty">
          <h2>Create your first project</h2>
          <p className="muted">A project is one agent and its Tapedeck suite. CI uploads each run&apos;s results here.</p>
        </div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead><tr><th>Project</th><th>Last run</th><th>Status</th></tr></thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id}>
                  <td><Link href={`/o/${org.slug}/p/${p.slug}`}><strong>{p.name}</strong></Link> <span className="faint mono small">{p.slug}</span></td>
                  <td className="muted">{p.last_run ? ago(p.last_run) : "No runs yet"}</td>
                  <td>
                    {p.last_passed === null ? <span className="pill plain">waiting</span>
                      : p.last_passed ? <span className="pill good">passing</span>
                      : <span className="pill bad">regressed</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card stack">
        <h2>New project</h2>
        {canAdd ? (
          <InlineForm action={createProjectAction} hidden={{ org: org.slug }} field="name" placeholder="support-agent" label="Create project" ariaLabel="Project name" />
        ) : (
          <p className="muted">
            The {plan(org.plan).name} plan includes {plan(org.plan).maxProjects} project.{" "}
            <Link href={`/o/${org.slug}/billing`}>Upgrade to Team</Link> for unlimited projects.
          </p>
        )}
      </div>
    </div>
  );
}
