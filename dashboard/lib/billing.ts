import Stripe from "stripe";

import type { Org } from "./accounts";
import { query, tx } from "./db";
import { isPaidStatus } from "./plans";

let client: Stripe | null = null;

export function stripe(): Stripe {
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) throw new Error("STRIPE_SECRET_KEY is not set");
  client ??= new Stripe(key);
  return client;
}

export function billingConfigured(): boolean {
  return Boolean(process.env.STRIPE_SECRET_KEY && process.env.STRIPE_PRICE_TEAM);
}

async function ensureCustomer(org: Org, email: string | null): Promise<string> {
  if (org.stripe_customer_id) return org.stripe_customer_id;
  const customer = await stripe().customers.create({
    name: org.name,
    email: email ?? undefined,
    metadata: { org_id: org.id, org_slug: org.slug },
  });
  await query(`update orgs set stripe_customer_id = $1 where id = $2`, [customer.id, org.id]);
  return customer.id;
}

/** A Stripe Checkout URL for upgrading ``org`` to Team. */
export async function checkoutUrl(org: Org, email: string | null, baseUrl: string): Promise<string> {
  const price = process.env.STRIPE_PRICE_TEAM;
  if (!price) throw new Error("STRIPE_PRICE_TEAM is not set");
  const customer = await ensureCustomer(org, email);
  const session = await stripe().checkout.sessions.create({
    mode: "subscription",
    customer,
    client_reference_id: org.id,
    line_items: [{ price, quantity: 1 }],
    subscription_data: { metadata: { org_id: org.id } },
    allow_promotion_codes: true,
    success_url: `${baseUrl}/o/${org.slug}/billing?upgraded=1`,
    cancel_url: `${baseUrl}/o/${org.slug}/billing`,
  });
  if (!session.url) throw new Error("Stripe returned no checkout URL");
  return session.url;
}

/** A Stripe Customer Portal URL for changing card, cancelling, or downloading invoices. */
export async function portalUrl(org: Org, baseUrl: string): Promise<string> {
  if (!org.stripe_customer_id) throw new Error("this organization has no billing account yet");
  const session = await stripe().billingPortal.sessions.create({
    customer: org.stripe_customer_id,
    return_url: `${baseUrl}/o/${org.slug}/billing`,
  });
  return session.url;
}

function periodEnd(sub: Stripe.Subscription): Date | null {
  const raw = sub as unknown as {
    current_period_end?: number;
    items?: { data?: { current_period_end?: number }[] };
  };
  const seconds = raw.current_period_end ?? raw.items?.data?.[0]?.current_period_end;
  return seconds ? new Date(seconds * 1000) : null;
}

/**
 * Apply one webhook event. Each event id is recorded in the same transaction as
 * its effect, so a retried event is a no-op and a failed one can be retried.
 * Returns false if the event was already processed.
 */
export async function applyEvent(event: Stripe.Event): Promise<boolean> {
  return tx(async (db) => {
    const fresh = await db.query(
      `insert into stripe_events (id, type) values ($1, $2) on conflict do nothing`,
      [event.id, event.type],
    );
    if (fresh.rowCount === 0) return false;

    switch (event.type) {
      case "checkout.session.completed": {
        const session = event.data.object as Stripe.Checkout.Session;
        const subscription =
          typeof session.subscription === "string" ? session.subscription : session.subscription?.id;
        const customer =
          typeof session.customer === "string" ? session.customer : session.customer?.id;
        if (session.client_reference_id && customer) {
          await db.query(
            `update orgs set stripe_customer_id = $1,
                             stripe_subscription_id = coalesce($2, stripe_subscription_id)
              where id = $3`,
            [customer, subscription ?? null, session.client_reference_id],
          );
        }
        break;
      }
      case "customer.subscription.created":
      case "customer.subscription.updated":
      case "customer.subscription.deleted": {
        const sub = event.data.object as Stripe.Subscription;
        const customer = typeof sub.customer === "string" ? sub.customer : sub.customer.id;
        const status = event.type === "customer.subscription.deleted" ? "canceled" : sub.status;
        const paid = isPaidStatus(status);
        // Enterprise is set by hand and never changed by a self-serve subscription.
        await db.query(
          `update orgs
              set subscription_status = $1,
                  stripe_subscription_id = $2,
                  current_period_end = $3,
                  plan = case when plan = 'enterprise' then plan
                              when $4 then 'team' else 'free' end
            where stripe_customer_id = $5`,
          [status, sub.id, periodEnd(sub), paid, customer],
        );
        break;
      }
      default:
        break;
    }
    return true;
  });
}
