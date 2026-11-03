"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { createOrg } from "@/lib/accounts";
import { requireMember, requireUser } from "@/lib/auth";
import { billingConfigured, checkoutUrl, portalUrl } from "@/lib/billing";
import { one, query } from "@/lib/db";
import { canAddMember, canAddProject, plan } from "@/lib/plans";
import { newToken, slugify } from "@/lib/tokens";

async function baseUrl(): Promise<string> {
  if (process.env.NEXTAUTH_URL) return process.env.NEXTAUTH_URL.replace(/\/$/, "");
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const proto = h.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  return `${proto}://${host}`;
}

function text(form: FormData, key: string, max = 80): string {
  return String(form.get(key) ?? "").trim().slice(0, max);
}

export interface FormState {
  error?: string;
  token?: string;
}

export async function createOrgAction(_: FormState, form: FormData): Promise<FormState> {
  const user = await requireUser();
  const name = text(form, "name");
  if (!name) return { error: "Give the organization a name." };
  const org = await createOrg(user.id, name);
  redirect(`/o/${org.slug}`);
}

export async function createProjectAction(_: FormState, form: FormData): Promise<FormState> {
  const { org } = await requireMember(text(form, "org"));
  const name = text(form, "name");
  const slug = slugify(name);
  if (!slug) return { error: "Use letters or numbers in the project name." };
  const count = await one<{ n: string }>(`select count(*) as n from projects where org_id = $1`, [
    org.id,
  ]);
  if (!canAddProject(org.plan, Number(count?.n ?? 0))) {
    return { error: `The ${plan(org.plan).name} plan includes ${plan(org.plan).maxProjects} project. Upgrade to Team for unlimited projects.` };
  }
  const created = await one<{ slug: string }>(
    `insert into projects (org_id, slug, name) values ($1, $2, $3)
     on conflict (org_id, slug) do nothing returning slug`,
    [org.id, slug, name],
  );
  if (!created) return { error: `A project named "${slug}" already exists.` };
  redirect(`/o/${org.slug}/p/${created.slug}/settings?new=1`);
}

export async function createTokenAction(_: FormState, form: FormData): Promise<FormState> {
  const { user, org } = await requireMember(text(form, "org"));
  const project = await one<{ id: string; slug: string }>(
    `select id, slug from projects where org_id = $1 and slug = $2`,
    [org.id, text(form, "project")],
  );
  if (!project) return { error: "Project not found." };
  const name = text(form, "name") || "CI";
  const { token, prefix, hash } = newToken();
  await query(
    `insert into api_tokens (project_id, name, prefix, token_hash, created_by)
     values ($1, $2, $3, $4, $5)`,
    [project.id, name, prefix, hash, user.id],
  );
  revalidatePath(`/o/${org.slug}/p/${project.slug}/settings`);
  return { token };
}

export async function revokeTokenAction(form: FormData): Promise<void> {
  const { org } = await requireMember(text(form, "org"));
  await query(
    `update api_tokens t set revoked_at = now() from projects p
      where t.project_id = p.id and p.org_id = $1 and t.id = $2`,
    [org.id, text(form, "token", 20)],
  );
  revalidatePath(`/o/${org.slug}/p/${text(form, "project")}/settings`);
}

export async function inviteAction(_: FormState, form: FormData): Promise<FormState> {
  const { user, org } = await requireMember(text(form, "org"), "owner");
  const login = text(form, "login", 39).replace(/^@/, "");
  if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(login)) {
    return { error: "That doesn't look like a GitHub username." };
  }
  const seats = await one<{ n: string }>(
    `select (select count(*) from memberships where org_id = $1)
          + (select count(*) from invites where org_id = $1) as n`,
    [org.id],
  );
  if (!canAddMember(org.plan, Number(seats?.n ?? 0))) {
    return { error: "The Free plan is for one person. Upgrade to Team to invite your team." };
  }
  const existing = await one(
    `select 1 from memberships m join users u on u.id = m.user_id
      where m.org_id = $1 and lower(u.login) = lower($2)`,
    [org.id, login],
  );
  if (existing) return { error: `@${login} is already a member.` };
  await query(
    `insert into invites (org_id, github_login, created_by) values ($1, $2, $3)
     on conflict do nothing`,
    [org.id, login, user.id],
  );
  revalidatePath(`/o/${org.slug}/members`);
  return {};
}

export async function cancelInviteAction(form: FormData): Promise<void> {
  const { org } = await requireMember(text(form, "org"), "owner");
  await query(`delete from invites where org_id = $1 and id = $2`, [org.id, text(form, "id", 20)]);
  revalidatePath(`/o/${org.slug}/members`);
}

export async function removeMemberAction(form: FormData): Promise<void> {
  const { user, org } = await requireMember(text(form, "org"), "owner");
  const target = text(form, "user", 20);
  if (target === user.id) return; // owners can't remove themselves and orphan the org
  await query(`delete from memberships where org_id = $1 and user_id = $2 and role <> 'owner'`, [
    org.id,
    target,
  ]);
  revalidatePath(`/o/${org.slug}/members`);
}

export async function checkoutAction(form: FormData): Promise<void> {
  const { user, org } = await requireMember(text(form, "org"), "owner");
  if (!billingConfigured()) redirect(`/o/${org.slug}/billing?error=not-configured`);
  const url = await checkoutUrl(org, user.email, await baseUrl());
  redirect(url);
}

export async function portalAction(form: FormData): Promise<void> {
  const { org } = await requireMember(text(form, "org"), "owner");
  const url = await portalUrl(org, await baseUrl());
  redirect(url);
}
