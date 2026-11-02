import { checkoutAction, portalAction } from "@/app/actions";
import { requireMember } from "@/lib/auth";
import { billingConfigured } from "@/lib/billing";
import { PLANS, plan } from "@/lib/plans";

export const metadata = { title: "Billing" };

const SALES = process.env.NEXT_PUBLIC_SALES_URL ?? "https://github.com/codexistent/tapedeck/discussions";

export default async function Billing({
  params,
  searchParams,
}: {
  params: Promise<{ org: string }>;
  searchParams: Promise<{ upgraded?: string; error?: string }>;
}) {
  const { org: slug } = await params;
  const { upgraded, error } = await searchParams;
  const { org } = await requireMember(slug);
  const current = plan(org.plan);
  const owner = org.role === "owner";

  return (
    <div className="stack">
      <h1>Billing</h1>
      {upgraded && org.plan === "free" && (
        <div className="notice info">Payment received. Your plan updates as soon as Stripe confirms it, usually within a few seconds. Refresh this page.</div>
      )}
      {upgraded && org.plan !== "free" && <div className="notice good">You&apos;re on {current.name}. Thanks for supporting Tapedeck.</div>}
      {error === "not-configured" && <div className="notice bad">Payments aren&apos;t set up on this deployment yet.</div>}

      <section className="card stack">
        <div className="spread">
          <div>
            <p className="muted small">Current plan</p>
            <h2>{current.name} <span className="muted" style={{ fontWeight: 400 }}>· {current.price}</span></h2>
          </div>
          {org.subscription_status && <span className={`pill ${org.subscription_status === "active" ? "good" : "warn"}`}>{org.subscription_status.replace("_", " ")}</span>}
        </div>
        <ul style={{ margin: 0, paddingLeft: 18 }} className="muted small">
          {current.features.map((f) => <li key={f}>{f}</li>)}
        </ul>
        {org.current_period_end && org.plan === "team" && (
          <p className="muted small">Renews {new Date(org.current_period_end).toDateString()}.</p>
        )}
        {owner ? (
          <div className="row">
            {org.plan === "free" && (
              <form action={checkoutAction}>
                <input type="hidden" name="org" value={org.slug} />
                <button className="btn primary" type="submit" disabled={!billingConfigured()}>Upgrade to Team · {PLANS.team.price}</button>
              </form>
            )}
            {org.stripe_customer_id && org.plan !== "enterprise" && (
              <form action={portalAction}>
                <input type="hidden" name="org" value={org.slug} />
                <button className="btn" type="submit">Manage billing &amp; invoices</button>
              </form>
            )}
            <a className="btn" href={SALES}>Talk to us about Enterprise</a>
          </div>
        ) : (
          <p className="muted small">Only owners can change billing.</p>
        )}
      </section>
      <p className="faint small">Payments are processed by Stripe. Cancel anytime from &quot;Manage billing&quot;; you keep Team until the end of the paid period.</p>
    </div>
  );
}
