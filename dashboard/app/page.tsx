import Link from "next/link";
import { getServerSession } from "next-auth";

import { Brand } from "@/components/Brand";
import { authOptions } from "@/lib/auth";
import { PLANS } from "@/lib/plans";

const SALES = process.env.NEXT_PUBLIC_SALES_URL ?? "https://github.com/codexistent/tapedeck/discussions";

export default async function Landing() {
  const session = await getServerSession(authOptions);
  const cta = session ? { href: "/dashboard", label: "Open dashboard" } : { href: "/login", label: "Sign in with GitHub" };

  return (
    <>
      <header className="topbar">
        <div className="wrap">
          <Brand />
          <nav className="tabs" aria-label="Site">
            <a href="#how">How it works</a>
            <a href="#pricing">Pricing</a>
            <Link href="/docs">Docs</Link>
            <a href="https://github.com/codexistent/tapedeck">GitHub</a>
          </nav>
          <Link className="btn" href={cta.href}>{session ? "Dashboard" : "Sign in"}</Link>
        </div>
      </header>

      <main className="wrap">
        <section className="hero">
          <h1>Know when a prompt change makes your agent worse, before you merge it.</h1>
          <p className="lede">
            Tapedeck replays your changed agent against recorded runs, grades every case ten times, and
            fails the pull request only when a regression is statistically real.
          </p>
          <div className="row">
            <Link className="btn primary" href={cta.href}>{cta.label}</Link>
            <Link className="btn" href="/docs">Setup guide</Link>
          </div>

          <div className="comment" aria-label="Example pull request comment">
            <div className="head">❌ Tapedeck: 1 regression in 8 cases</div>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Case</th><th>Baseline</th><th>Candidate</th><th>p (adjusted)</th></tr></thead>
                <tbody>
                  <tr className="bad"><td className="mono">refund-someone-elses-order</td><td className="num">10/10</td><td className="num">1/10</td><td className="num">0.0005</td></tr>
                </tbody>
              </table>
            </div>
            <p className="small">
              <strong className="mono">refund-someone-elses-order</strong>: Candidate added a call to
              issue_refund after get_order in 9/10 candidate runs (baseline: 0/10).
            </p>
          </div>
        </section>

        <section className="section" id="how">
          <h2>How it works</h2>
          <div className="grid three">
            <div className="card stack">
              <span className="step-n">01 · RECORD</span>
              <h3>Capture real runs as tapes</h3>
              <p className="muted small">Two lines of instrumentation. Every model call and tool call is saved to a JSONL tape you commit with your code.</p>
            </div>
            <div className="card stack">
              <span className="step-n">02 · REPLAY</span>
              <h3>Run the changed agent live</h3>
              <p className="muted small">The model is live; tools answer from the tape. When the agent does something new, simulators keep the world consistent.</p>
            </div>
            <div className="card stack">
              <span className="step-n">03 · GATE</span>
              <h3>Fail only real regressions</h3>
              <p className="muted small">Each case runs N times. Fisher&apos;s exact test with Holm correction separates real drops from noise, and the diff says what changed.</p>
            </div>
          </div>
          <p className="muted small" style={{ marginTop: 16 }}>
            Your tapes never leave your repository. The dashboard receives results only: pass counts, p-values and the one-line explanation.
          </p>
        </section>

        <section className="section" id="pricing">
          <h2>Pricing</h2>
          <div className="grid three">
            {Object.values(PLANS).map((p) => (
              <div key={p.id} className={`card price-card${p.id === "team" ? " featured" : ""}`}>
                <div className="spread"><h3>{p.name}</h3>{p.id === "team" && <span className="pill plain">Most teams</span>}</div>
                <div className="price">{p.price}</div>
                <p className="muted small">{p.blurb}</p>
                <ul>{p.features.map((f) => <li key={f}>{f}</li>)}</ul>
                {p.id === "enterprise" ? (
                  <a className="btn" href={SALES}>Contact us</a>
                ) : (
                  <Link className={`btn${p.id === "team" ? " primary" : ""}`} href={session ? "/dashboard" : "/login"}>
                    {p.id === "team" ? "Start with Team" : "Start free"}
                  </Link>
                )}
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="site">
        <div className="wrap spread">
          <span>Tapedeck · Apache-2.0 CLI</span>
          <a href="https://github.com/codexistent/tapedeck">github.com/codexistent/tapedeck</a>
        </div>
      </footer>
    </>
  );
}
