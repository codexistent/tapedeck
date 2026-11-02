import Link from "next/link";

import { cancelInviteAction, inviteAction, removeMemberAction } from "@/app/actions";
import { InlineForm } from "@/components/forms";
import { requireMember } from "@/lib/auth";
import { invites, members } from "@/lib/data";
import { canAddMember } from "@/lib/plans";

export const metadata = { title: "Members" };

export default async function Members({ params }: { params: Promise<{ org: string }> }) {
  const { org: slug } = await params;
  const { user, org } = await requireMember(slug);
  const [people, pending] = await Promise.all([members(org.id), invites(org.id)]);
  const owner = org.role === "owner";
  const canInvite = canAddMember(org.plan, people.length + pending.length);

  return (
    <div className="stack">
      <h1>Members</h1>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Person</th><th>Role</th><th /></tr></thead>
          <tbody>
            {people.map((m) => (
              <tr key={m.user_id}>
                <td>
                  <div className="row">
                    {m.avatar_url && <img className="avatar" src={m.avatar_url} alt="" />}
                    <span><strong>{m.name ?? m.login}</strong> <span className="faint">@{m.login}</span></span>
                  </div>
                </td>
                <td><span className="pill plain">{m.role}</span></td>
                <td style={{ textAlign: "right" }}>
                  {owner && m.role !== "owner" && m.user_id !== user.id && (
                    <form action={removeMemberAction}>
                      <input type="hidden" name="org" value={org.slug} />
                      <input type="hidden" name="user" value={m.user_id} />
                      <button className="btn danger" type="submit">Remove</button>
                    </form>
                  )}
                </td>
              </tr>
            ))}
            {pending.map((i) => (
              <tr key={`invite-${i.id}`}>
                <td className="muted">@{i.github_login} <span className="small">· joins on first sign-in</span></td>
                <td><span className="pill warn">invited</span></td>
                <td style={{ textAlign: "right" }}>
                  {owner && (
                    <form action={cancelInviteAction}>
                      <input type="hidden" name="org" value={org.slug} />
                      <input type="hidden" name="id" value={i.id} />
                      <button className="btn" type="submit">Cancel</button>
                    </form>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {owner && (
        <section className="card stack">
          <h2>Invite by GitHub username</h2>
          {canInvite ? (
            <InlineForm action={inviteAction} hidden={{ org: org.slug }} field="login" placeholder="octocat" label="Invite" ariaLabel="GitHub username" />
          ) : (
            <p className="muted">The Free plan is for one person. <Link href={`/o/${org.slug}/billing`}>Upgrade to Team</Link> to invite your team.</p>
          )}
        </section>
      )}
    </div>
  );
}
