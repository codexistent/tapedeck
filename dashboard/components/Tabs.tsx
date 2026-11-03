"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function Tabs({ org }: { org: string }) {
  const path = usePathname();
  const base = `/o/${org}`;
  const tabs = [
    { href: base, label: "Projects", on: path === base || path.startsWith(`${base}/p/`) },
    { href: `${base}/members`, label: "Members", on: path.startsWith(`${base}/members`) },
    { href: `${base}/billing`, label: "Billing", on: path.startsWith(`${base}/billing`) },
  ];
  return (
    <nav className="tabs" aria-label="Organization">
      {tabs.map((t) => (
        <Link key={t.href} href={t.href} className={t.on ? "on" : undefined} aria-current={t.on ? "page" : undefined}>
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
