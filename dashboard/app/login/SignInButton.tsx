"use client";

import { signIn } from "next-auth/react";
import { useState } from "react";

export function SignInButton() {
  const [busy, setBusy] = useState(false);
  return (
    <button
      className="btn primary"
      style={{ justifyContent: "center" }}
      disabled={busy}
      onClick={() => {
        setBusy(true);
        void signIn("github", { callbackUrl: "/dashboard" });
      }}
    >
      {busy ? "Redirecting to GitHub…" : "Continue with GitHub"}
    </button>
  );
}
