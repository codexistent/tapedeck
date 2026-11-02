import type { ReactNode } from "react";

import { Brand } from "@/components/Brand";
import { Tabs } from "@/components/Tabs";
import { orgsForUser } from "@/lib/accounts";
import { requireMember } from "@/lib/auth";
import { plan } from "@/lib/plans";

export const dynamic = "force-dynamic";

export default async function OrgLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ org: string }>;
}) {
  const { org: slug } = await params;
  const { user, org } = await requireMember(slug);
  const orgs = await orgsForUser(user.id);
  return (
    <>
      <header className="topbar">
        <div className="wrap">
          <Brand href="/dashboard" />
          <span className="faint hide-sm">/</span>
          <details className="hide-sm" style={{ position: "relative" }}>
            <summary style={{ cursor: "pointer", listStyle: "none", fontWeight: 600 }}>
              {org.name} <span className="pill plain">{plan(org.plan).name}</span>
            </summary>
            <div className="card" style={{ position: "absolute", top: 32, left: 0, zIndex: 10, minWidth: 220, padding: 8 }}>
              {orgs.map((o) => (
                <a key={o.id} href={`/o/${o.slug}`} style={{ display: "block", padding: "6px 8px" }}>{o.name}</a>
              ))}
              <a href="/new-org" style={{ display: "block", padding: "6px 8px", borderTop: "1px solid var(--rule)" }}>+ New organization</a>
            </div>
          </details>
          <Tabs org={org.slug} />
          <a href="/api/auth/signout" className="small muted hide-sm">Sign out</a>
          {user.avatar_url && <img className="avatar" src={user.avatar_url} alt={`@${user.login}`} />}
        </div>
      </header>
      <main className="page wrap">{children}</main>
    </>
  );
}
