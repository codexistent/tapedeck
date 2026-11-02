import Link from "next/link";

export function Brand({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="brand" aria-label="Tapedeck home">
      <svg className="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="2" y="5" width="20" height="14" rx="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <circle cx="8" cy="12" r="2.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <circle cx="16" cy="12" r="2.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <path d="M8 14.6h8" stroke="currentColor" strokeWidth="1.8" />
      </svg>
      Tapedeck
    </Link>
  );
}
