import Link from "next/link";

export default function NotFound() {
  return (
    <main className="wrap" style={{ maxWidth: 520, paddingTop: 96 }}>
      <div className="card stack empty">
        <h1>Not found</h1>
        <p className="muted">This page doesn&apos;t exist, or you don&apos;t have access to it.</p>
        <p><Link href="/dashboard">Go to your dashboard</Link></p>
      </div>
    </main>
  );
}
