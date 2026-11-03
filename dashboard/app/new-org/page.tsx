import { createOrgAction } from "@/app/actions";
import { Brand } from "@/components/Brand";
import { InlineForm } from "@/components/forms";
import { requireUser } from "@/lib/auth";

export const metadata = { title: "New organization" };

export default async function NewOrg() {
  await requireUser();
  return (
    <main className="wrap" style={{ maxWidth: 520, paddingTop: 80 }}>
      <div className="card stack" style={{ padding: 28 }}>
        <Brand href="/dashboard" />
        <h1>New organization</h1>
        <p className="muted">Organizations hold projects, members and billing. Each one has its own plan.</p>
        <InlineForm action={createOrgAction} hidden={{}} field="name" placeholder="Acme AI" label="Create" ariaLabel="Organization name" />
      </div>
    </main>
  );
}
