import type { NextAuthOptions } from "next-auth";
import { getServerSession } from "next-auth";
import GitHubProvider from "next-auth/providers/github";
import { notFound, redirect } from "next/navigation";

import { membership, type Org, onSignIn, type User, userByGithubId } from "./accounts";

interface GitHubOAuthProfile {
  id: number;
  login: string;
  name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
}

export const authOptions: NextAuthOptions = {
  providers: [
    GitHubProvider({
      clientId: process.env.GITHUB_ID ?? "",
      clientSecret: process.env.GITHUB_SECRET ?? "",
    }),
  ],
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
  callbacks: {
    async signIn({ profile }) {
      const p = profile as unknown as GitHubOAuthProfile | undefined;
      if (!p?.id || !p.login) return false;
      await onSignIn({
        githubId: p.id,
        login: p.login,
        name: p.name,
        email: p.email,
        avatarUrl: p.avatar_url,
      });
      return true;
    },
    async jwt({ token, profile }) {
      const p = profile as unknown as GitHubOAuthProfile | undefined;
      if (p?.id) token.githubId = String(p.id);
      return token;
    },
    async session({ session, token }) {
      if (token.githubId) session.githubId = String(token.githubId);
      return session;
    },
  },
};

declare module "next-auth" {
  interface Session {
    githubId?: string;
  }
}

/** The signed-in user, or a redirect to /login. */
export async function requireUser(): Promise<User> {
  const session = await getServerSession(authOptions);
  const user = session?.githubId ? await userByGithubId(session.githubId) : null;
  if (!user) redirect("/login");
  return user;
}

/** The user and their membership in ``orgSlug``; 404 if they are not a member. */
export async function requireMember(
  orgSlug: string,
  role?: "owner",
): Promise<{ user: User; org: Org & { role: string } }> {
  const user = await requireUser();
  const org = await membership(user.id, orgSlug);
  if (!org || (role && org.role !== role)) notFound();
  return { user, org };
}
