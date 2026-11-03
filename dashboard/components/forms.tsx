"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import type { FormState } from "@/app/actions";

type Action = (state: FormState, form: FormData) => Promise<FormState>;

function Submit({ label, pending }: { label: string; pending: string }) {
  const status = useFormStatus();
  return (
    <button className="btn primary" type="submit" disabled={status.pending}>
      {status.pending ? pending : label}
    </button>
  );
}

/** A one-field form posting to a server action, showing its error inline. */
export function InlineForm({
  action,
  hidden,
  field,
  placeholder,
  label,
  pending = "Saving…",
  ariaLabel,
}: {
  action: Action;
  hidden: Record<string, string>;
  field: string;
  placeholder: string;
  label: string;
  pending?: string;
  ariaLabel: string;
}) {
  const [state, formAction] = useActionState(action, {});
  return (
    <form action={formAction} className="stack">
      {Object.entries(hidden).map(([k, v]) => (
        <input key={k} type="hidden" name={k} value={v} />
      ))}
      <div className="row">
        <input name={field} placeholder={placeholder} aria-label={ariaLabel} required style={{ flex: 1, minWidth: 180 }} />
        <Submit label={label} pending={pending} />
      </div>
      {state.error && <p className="error" role="alert">{state.error}</p>}
    </form>
  );
}

/** Creates an API token and shows it exactly once. */
export function TokenForm({ action, org, project }: { action: Action; org: string; project: string }) {
  const [state, formAction] = useActionState(action, {});
  return (
    <form action={formAction} className="stack">
      <input type="hidden" name="org" value={org} />
      <input type="hidden" name="project" value={project} />
      <div className="row">
        <input name="name" placeholder="Token name, e.g. GitHub Actions" aria-label="Token name" style={{ flex: 1, minWidth: 180 }} />
        <Submit label="Create token" pending="Creating…" />
      </div>
      {state.error && <p className="error" role="alert">{state.error}</p>}
      {state.token && (
        <div className="stack">
          <p className="small"><strong>Copy this token now.</strong> It won&apos;t be shown again.</p>
          <div className="secret">{state.token}</div>
        </div>
      )}
    </form>
  );
}
