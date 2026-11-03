import Stripe from "stripe";
import { beforeEach, describe, expect, it } from "vitest";

import "./setup";
import { resetDb } from "./setup";

process.env.STRIPE_SECRET_KEY ??= "sk_test_dummy";
process.env.STRIPE_WEBHOOK_SECRET = "whsec_test_secret";

import { POST } from "@/app/api/stripe/webhook/route";
import { onSignIn, orgsForUser } from "@/lib/accounts";
import { applyEvent } from "@/lib/billing";
import { one, query } from "@/lib/db";

async function orgWithCustomer(): Promise<string> {
  const user = await onSignIn({ githubId: 3, login: "acme" });
  const [org] = await orgsForUser(user.id);
  await query(`update orgs set stripe_customer_id = 'cus_123' where id = $1`, [org.id]);
  return org.id;
}

function subEvent(id: string, type: string, status: string): Stripe.Event {
  return {
    id,
    type,
    object: "event",
    data: { object: { id: "sub_1", object: "subscription", customer: "cus_123", status, current_period_end: 1_900_000_000 } },
  } as unknown as Stripe.Event;
}

async function orgPlan(orgId: string) {
  return one<{ plan: string; subscription_status: string; stripe_subscription_id: string }>(
    `select plan, subscription_status, stripe_subscription_id from orgs where id = $1`, [orgId]);
}

beforeEach(resetDb);

describe("Stripe webhook handling", () => {
  it("upgrades on an active subscription and downgrades when it ends", async () => {
    const orgId = await orgWithCustomer();
    await applyEvent(subEvent("evt_1", "customer.subscription.created", "active"));
    expect(await orgPlan(orgId)).toMatchObject({ plan: "team", subscription_status: "active", stripe_subscription_id: "sub_1" });
    await applyEvent(subEvent("evt_2", "customer.subscription.updated", "past_due"));
    expect((await orgPlan(orgId))?.plan).toBe("team"); // grace period while Stripe retries the card
    await applyEvent(subEvent("evt_3", "customer.subscription.deleted", "canceled"));
    expect(await orgPlan(orgId)).toMatchObject({ plan: "free", subscription_status: "canceled" });
  });

  it("applies each event once", async () => {
    const orgId = await orgWithCustomer();
    expect(await applyEvent(subEvent("evt_1", "customer.subscription.created", "active"))).toBe(true);
    await query(`update orgs set plan = 'free' where id = $1`, [orgId]);
    expect(await applyEvent(subEvent("evt_1", "customer.subscription.created", "active"))).toBe(false);
    expect((await orgPlan(orgId))?.plan).toBe("free");
  });

  it("never touches a hand-set Enterprise plan", async () => {
    const orgId = await orgWithCustomer();
    await query(`update orgs set plan = 'enterprise' where id = $1`, [orgId]);
    await applyEvent(subEvent("evt_9", "customer.subscription.deleted", "canceled"));
    expect((await orgPlan(orgId))?.plan).toBe("enterprise");
  });

  it("links the subscription from checkout.session.completed", async () => {
    const orgId = await orgWithCustomer();
    await applyEvent({
      id: "evt_c", type: "checkout.session.completed", object: "event",
      data: { object: { object: "checkout.session", client_reference_id: orgId, customer: "cus_123", subscription: "sub_9" } },
    } as unknown as Stripe.Event);
    expect((await orgPlan(orgId))?.stripe_subscription_id).toBe("sub_9");
  });

  it("verifies signatures on the route", async () => {
    const orgId = await orgWithCustomer();
    const payload = JSON.stringify(subEvent("evt_sig", "customer.subscription.created", "active"));
    const header = new Stripe("sk_test_dummy").webhooks.generateTestHeaderString({
      payload, secret: "whsec_test_secret",
    });
    const forged = await POST(new Request("http://x/api/stripe/webhook", {
      method: "POST", headers: { "stripe-signature": "t=1,v1=bad" }, body: payload,
    }));
    expect(forged.status).toBe(400);
    const ok = await POST(new Request("http://x/api/stripe/webhook", {
      method: "POST", headers: { "stripe-signature": header }, body: payload,
    }));
    expect(ok.status).toBe(200);
    expect((await orgPlan(orgId))?.plan).toBe("team");
  });
});
