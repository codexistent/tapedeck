import { beforeEach, describe, expect, it } from "vitest";

import "./setup";
import { resetDb } from "./setup";

import { createOrg, onSignIn, orgsForUser } from "@/lib/accounts";
import { one, query } from "@/lib/db";
import { canAddMember, canAddProject, isPaidStatus, plan } from "@/lib/plans";
import { bearer, hashToken, isSlug, newToken, slugify } from "@/lib/tokens";

beforeEach(resetDb);

describe("tokens", () => {
  it("creates prefixed tokens and stores only a hash", () => {
    const t = newToken();
    expect(t.token).toMatch(/^tdk_[A-Za-z0-9_-]{32}$/);
    expect(t.prefix).toBe(t.token.slice(0, 10));
    expect(t.hash).toBe(hashToken(t.token));
    expect(t.hash).not.toContain(t.token);
    expect(newToken().token).not.toBe(t.token);
  });

  it("parses bearer headers strictly", () => {
    expect(bearer("Bearer tdk_abc")).toBe("tdk_abc");
    expect(bearer("bearer   tdk_abc ")).toBe("tdk_abc");
    expect(bearer("Bearer sk_live_x")).toBeNull();
    expect(bearer("tdk_abc")).toBeNull();
    expect(bearer(null)).toBeNull();
  });

  it("slugifies names", () => {
    expect(slugify("  Acme AI, Inc.  ")).toBe("acme-ai-inc");
    expect(slugify("!!!")).toBe("");
    expect(isSlug("support-agent")).toBe(true);
    expect(isSlug("-bad")).toBe(false);
  });
});

describe("plans", () => {
  it("gates projects and members on Free", () => {
    expect(canAddProject("free", 0)).toBe(true);
    expect(canAddProject("free", 1)).toBe(false);
    expect(canAddProject("team", 500)).toBe(true);
    expect(canAddMember("free", 1)).toBe(false);
    expect(canAddMember("team", 50)).toBe(true);
    expect(plan("nonsense").id).toBe("free");
    expect(isPaidStatus("active") && isPaidStatus("past_due")).toBe(true);
    expect(isPaidStatus("canceled") || isPaidStatus("incomplete_expired")).toBe(false);
  });
});

describe("sign-in", () => {
  it("creates the user and a personal org once", async () => {
    const user = await onSignIn({ githubId: 1, login: "Pearl", email: "p@example.com" });
    await onSignIn({ githubId: 1, login: "Pearl", email: null });
    const orgs = await orgsForUser(user.id);
    expect(orgs).toHaveLength(1);
    expect(orgs[0]).toMatchObject({ slug: "pearl", role: "owner", plan: "free" });
    const again = await one<{ email: string }>(`select email from users where id = $1`, [user.id]);
    expect(again?.email).toBe("p@example.com"); // a missing email doesn't erase a known one
  });

  it("picks a free slug when the login is taken", async () => {
    const a = await onSignIn({ githubId: 1, login: "sam" });
    await createOrg(a.id, "Bob");
    const b = await onSignIn({ githubId: 2, login: "bob" });
    const orgs = await orgsForUser(b.id);
    expect(orgs[0].slug).toBe("bob-2");
  });

  it("accepts pending invites instead of creating a personal org", async () => {
    const owner = await onSignIn({ githubId: 1, login: "owner" });
    const [org] = await orgsForUser(owner.id);
    await query(`insert into invites (org_id, github_login) values ($1, 'NewDev')`, [org.id]);
    const dev = await onSignIn({ githubId: 2, login: "newdev" });
    const orgs = await orgsForUser(dev.id);
    expect(orgs.map((o) => [o.slug, o.role])).toEqual([["owner", "member"]]);
    expect(await query(`select * from invites`)).toHaveLength(0);
  });
});
