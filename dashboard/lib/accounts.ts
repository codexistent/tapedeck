import { one, query, tx } from "./db";
import { slugify } from "./tokens";

export interface User {
  id: string;
  github_id: string;
  login: string;
  name: string | null;
  email: string | null;
  avatar_url: string | null;
}

export interface Org {
  id: string;
  slug: string;
  name: string;
  plan: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  subscription_status: string | null;
  current_period_end: Date | null;
}

export interface GitHubProfile {
  githubId: number | string;
  login: string;
  name?: string | null;
  email?: string | null;
  avatarUrl?: string | null;
}

async function freeSlug(base: string, taken: (slug: string) => Promise<boolean>): Promise<string> {
  const root = slugify(base) || "org";
  for (let i = 0; i < 1000; i++) {
    const candidate = i === 0 ? root : `${root}-${i + 1}`;
    if (!(await taken(candidate))) return candidate;
  }
  throw new Error("could not find a free slug");
}

/**
 * Called on every sign-in: upsert the user, accept any pending invites for their
 * GitHub login, and make sure they belong to at least one organization.
 */
export async function onSignIn(profile: GitHubProfile): Promise<User> {
  return tx(async (client) => {
    const { rows } = await client.query<User>(
      `insert into users (github_id, login, name, email, avatar_url)
       values ($1, $2, $3, $4, $5)
       on conflict (github_id) do update
         set login = excluded.login, name = excluded.name,
             email = coalesce(excluded.email, users.email), avatar_url = excluded.avatar_url
       returning *`,
      [profile.githubId, profile.login, profile.name ?? null, profile.email ?? null,
        profile.avatarUrl ?? null],
    );
    const user = rows[0];

    const invites = await client.query<{ id: string; org_id: string }>(
      `delete from invites where lower(github_login) = lower($1) returning id, org_id`,
      [user.login],
    );
    for (const invite of invites.rows) {
      await client.query(
        `insert into memberships (org_id, user_id, role) values ($1, $2, 'member')
         on conflict do nothing`,
        [invite.org_id, user.id],
      );
    }

    const member = await client.query(`select 1 from memberships where user_id = $1 limit 1`, [
      user.id,
    ]);
    if (member.rowCount === 0) {
      const slug = await freeSlug(user.login, async (s) => {
        const hit = await client.query(`select 1 from orgs where slug = $1`, [s]);
        return (hit.rowCount ?? 0) > 0;
      });
      const org = await client.query<{ id: string }>(
        `insert into orgs (slug, name) values ($1, $2) returning id`,
        [slug, user.login],
      );
      await client.query(
        `insert into memberships (org_id, user_id, role) values ($1, $2, 'owner')`,
        [org.rows[0].id, user.id],
      );
    }
    return user;
  });
}

export async function userByGithubId(githubId: string): Promise<User | null> {
  return one<User>(`select * from users where github_id = $1`, [githubId]);
}

export async function orgsForUser(userId: string): Promise<(Org & { role: string })[]> {
  return query<Org & { role: string }>(
    `select o.*, m.role from orgs o join memberships m on m.org_id = o.id
     where m.user_id = $1 order by o.created_at`,
    [userId],
  );
}

export async function membership(
  userId: string,
  orgSlug: string,
): Promise<(Org & { role: string }) | null> {
  return one<Org & { role: string }>(
    `select o.*, m.role from orgs o join memberships m on m.org_id = o.id
     where m.user_id = $1 and o.slug = $2`,
    [userId, orgSlug],
  );
}

export async function createOrg(userId: string, name: string): Promise<Org> {
  return tx(async (client) => {
    const slug = await freeSlug(name, async (s) => {
      const hit = await client.query(`select 1 from orgs where slug = $1`, [s]);
      return (hit.rowCount ?? 0) > 0;
    });
    const { rows } = await client.query<Org>(
      `insert into orgs (slug, name) values ($1, $2) returning *`,
      [slug, name.trim().slice(0, 80) || slug],
    );
    await client.query(
      `insert into memberships (org_id, user_id, role) values ($1, $2, 'owner')`,
      [rows[0].id, userId],
    );
    return rows[0];
  });
}
