import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";

import { Brand } from "@/components/Brand";
import { authOptions } from "@/lib/auth";

import { SignInButton } from "./SignInButton";

export const metadata = { title: "Sign in" };

export default async function Login() {
  if (await getServerSession(authOptions)) redirect("/dashboard");
  return (
    <main className="wrap" style={{ maxWidth: 420, paddingTop: 96 }}>
      <div className="card stack" style={{ padding: 28 }}>
        <Brand />
        <h1>Sign in</h1>
        <p className="muted">Tapedeck uses your GitHub account. We only read your public profile and email.</p>
        <SignInButton />
      </div>
    </main>
  );
}
