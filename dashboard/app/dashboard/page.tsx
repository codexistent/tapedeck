import { redirect } from "next/navigation";

import { orgsForUser } from "@/lib/accounts";
import { requireUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

/** Send the user to their first organization. */
export default async function Dashboard() {
  const user = await requireUser();
  const orgs = await orgsForUser(user.id);
  redirect(orgs.length ? `/o/${orgs[0].slug}` : "/new-org");
}
