export type PlanId = "free" | "team" | "enterprise";

export interface Plan {
  id: PlanId;
  name: string;
  price: string;
  blurb: string;
  maxProjects: number;
  maxMembers: number;
  historyDays: number;
  features: string[];
}

export const PLANS: Record<PlanId, Plan> = {
  free: {
    id: "free",
    name: "Free",
    price: "$0",
    blurb: "For trying Tapedeck on one agent.",
    maxProjects: 1,
    maxMembers: 1,
    historyDays: 14,
    features: [
      "Open-source CLI and GitHub Action",
      "1 project, 1 member",
      "14 days of run history",
      "Case pass-rate trends",
    ],
  },
  team: {
    id: "team",
    name: "Team",
    price: "$99/mo",
    blurb: "Flat per organization. Expense it without a procurement process.",
    maxProjects: Number.POSITIVE_INFINITY,
    maxMembers: Number.POSITIVE_INFINITY,
    historyDays: 365,
    features: [
      "Everything in Free",
      "Unlimited projects and members",
      "1 year of run history",
      "Flaky-case detection across runs",
    ],
  },
  enterprise: {
    id: "enterprise",
    name: "Enterprise",
    price: "Contact us",
    blurb: "For companies with security and compliance requirements.",
    maxProjects: Number.POSITIVE_INFINITY,
    maxMembers: Number.POSITIVE_INFINITY,
    historyDays: 730,
    features: [
      "Everything in Team",
      "Custom history retention",
      "Help with your security review",
      "Annual contract and invoicing",
    ],
  },
};

export function plan(id: string): Plan {
  return PLANS[(id in PLANS ? id : "free") as PlanId];
}

/** Stripe subscription statuses that keep a paid plan active. */
export function isPaidStatus(status: string | null | undefined): boolean {
  return status === "active" || status === "trialing" || status === "past_due";
}

export function canAddProject(planId: string, current: number): boolean {
  return current < plan(planId).maxProjects;
}

export function canAddMember(planId: string, currentMembersAndInvites: number): boolean {
  return currentMembersAndInvites < plan(planId).maxMembers;
}
