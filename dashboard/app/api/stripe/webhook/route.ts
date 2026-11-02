import { NextResponse } from "next/server";
import type Stripe from "stripe";

import { applyEvent, stripe } from "@/lib/billing";

export const runtime = "nodejs";

/** Stripe calls this for subscription changes. The signature is verified on the raw body. */
export async function POST(request: Request) {
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  const signature = request.headers.get("stripe-signature");
  if (!secret) return NextResponse.json({ error: "webhook not configured" }, { status: 500 });
  if (!signature) return NextResponse.json({ error: "missing signature" }, { status: 400 });

  const payload = await request.text();
  let event: Stripe.Event;
  try {
    event = stripe().webhooks.constructEvent(payload, signature, secret);
  } catch {
    return NextResponse.json({ error: "invalid signature" }, { status: 400 });
  }

  const applied = await applyEvent(event);
  return NextResponse.json({ received: true, duplicate: !applied });
}
