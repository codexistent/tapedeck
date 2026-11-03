import Link from "next/link";
import type { ReactNode } from "react";

import { Brand } from "@/components/Brand";
import { CopyButton } from "@/components/CopyButton";

export const metadata = {
  title: "Setup guide",
  description: "Set up Tapedeck on your own agent, step by step: install, record, baseline, and gate pull requests.",
};

const SITE = process.env.NEXTAUTH_URL ?? "https://tapedeck-five.vercel.app";
const VERSION = "v0.2.0";

function Code({ children, file }: { children: string; file?: string }) {
  return (
    <div className="codewrap">
      {file && <div className="file">{file}</div>}
      <pre className="code">{children}</pre>
      <CopyButton text={children} />
    </div>
  );
}

function Step({ id, n, title, children }: { id: string; n: number; title: string; children: ReactNode }) {
  return (
    <section id={id} className="stack">
      <h2><span className="step-label">STEP {n}</span><br />{title}</h2>
      {children}
    </section>
  );
}

const TOC: [string, string][] = [
  ["overview", "Before you start"],
  ["install", "1. Install the CLI"],
  ["instrument", "2. Instrument your agent"],
  ["prompt", "3. Put your prompt in a file"],
  ["cases", "4. Write test cases"],
  ["checks", "5. Write checks"],
  ["config", "6. Create tapedeck.yaml"],
  ["key", "7. Add your model key locally"],
  ["record", "8. Record tapes"],
  ["baseline", "9. Make a baseline"],
  ["try", "10. Try it locally"],
  ["commit", "11. Commit the files"],
  ["token", "12. Get a dashboard token"],
  ["secrets", "13. Add GitHub secrets"],
  ["workflow", "14. Add the workflow"],
  ["pr", "15. Open a pull request"],
  ["daily", "Day to day"],
  ["writes", "If your agent changes data"],
  ["trouble", "Troubleshooting"],
];

export default function Docs() {
  return (
    <>
      <header className="topbar">
        <div className="wrap">
          <Brand />
          <nav className="tabs" aria-label="Site">
            <Link href="/#how">How it works</Link>
            <Link href="/#pricing">Pricing</Link>
            <Link href="/docs" className="on" aria-current="page">Docs</Link>
            <a href="https://github.com/codexistent/tapedeck">GitHub</a>
          </nav>
          <Link className="btn" href="/dashboard">Dashboard</Link>
        </div>
      </header>

      <div className="wrap docs">
        <nav className="toc" aria-label="On this page">
          <div className="toc-title">Setup guide</div>
          {TOC.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
        </nav>

        <article>
          <h1>Set up Tapedeck on your agent</h1>
          <p className="muted">
            About 30 minutes. At the end, every pull request that touches your agent gets a Tapedeck check that
            fails only when behavior really got worse, and every run shows up in your dashboard.
          </p>

          <section id="overview" className="stack">
            <h2>Before you start</h2>
            <p>You need:</p>
            <ul>
              <li>A Python agent (Python 3.11 or newer) in a GitHub repository, that calls its model through an OpenAI-compatible chat API. OpenAI, OpenRouter, and most providers and proxies offer one.</li>
              <li>The API key your agent already uses. Tapedeck never needs a key of its own: replays run your agent, on your key.</li>
              <li>A Tapedeck account. <Link href="/login">Sign in with GitHub</Link>; it&apos;s free.</li>
            </ul>
            <p>When you&apos;re done, your repository will contain these new files. Everything goes at the top level of your repo:</p>
            <Code>{`your-repo/
├── my_agent/agent.py            # your agent (2 small changes, step 2)
├── prompts/system.txt           # your system prompt (step 3)
├── cases.yaml                   # test cases (step 4)
├── tapedeck_checks.py           # what "correct" means (step 5)
├── tapedeck.yaml                # config (step 6)
├── tapes/*.jsonl                # recordings (step 8, generated)
├── tapedeck-baseline.json       # baseline (step 9, generated)
└── .github/workflows/tapedeck.yml   # the CI check (step 14)`}</Code>
            <p className="where">Steps 1 to 11 happen in a terminal on your computer, inside your repository folder. Steps 12 to 15 happen in your browser.</p>
          </section>

          <Step id="install" n={1} title="Install the CLI">
            <p>Open a terminal in your repository folder and run:</p>
            <Code>{`pip install "tapedeck @ git+https://github.com/codexistent/tapedeck@${VERSION}"`}</Code>
            <p>Check it worked: <code>tapedeck --help</code> should list <code>record</code>, <code>playback</code>, <code>baseline</code> and <code>test</code>. Also add <code>tapedeck</code> with the same line to your project&apos;s requirements file so CI and teammates get it.</p>
          </Step>

          <Step id="instrument" n={2} title="Instrument your agent">
            <p>Make two changes to your agent code, and expose one function Tapedeck can call:</p>
            <ol className="steps">
              <li>Call the model with <code>tapedeck.chat(messages, tools)</code> instead of your SDK. It takes OpenAI-format messages and tool schemas and returns the reply.</li>
              <li>Put <code>@tapedeck.tool</code> on every tool function, saying whether it only reads (<code>effect=&quot;read&quot;</code>), changes data (<code>&quot;write&quot;</code>, the default), or reaches the outside world, like email or payments (<code>&quot;external&quot;</code>, never really called during tests).</li>
              <li>Add a <code>run(message, context, prompt)</code> function that handles one user message and returns the reply.</li>
            </ol>
            <p>Outside of Tapedeck both behave normally, so the same code runs in production. A complete minimal example:</p>
            <Code file="my_agent/agent.py">{`import tapedeck


@tapedeck.tool(effect="read")
def get_order(order_id: str) -> dict:
    return db.get_order(order_id)            # your real code


TOOLS = {"get_order": get_order}
TOOL_SCHEMAS = [{
    "type": "function",
    "function": {
        "name": "get_order",
        "description": "Look up an order by id.",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
}]


def run(message: str, context: dict, prompt: str) -> str:
    """Tapedeck calls this once per test case."""
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": message},
    ]
    for _ in range(10):
        reply = tapedeck.chat(messages, TOOL_SCHEMAS)
        messages.append(tapedeck.assistant_message(reply))
        if not reply.tool_calls:
            return reply.content or ""
        for call in reply.tool_calls:
            result = TOOLS[call.name](**call.arguments)
            messages.append(tapedeck.tool_message(call.id, result))
    return "Sorry, I couldn't finish that."`}</Code>
            <p className="where"><code>my_agent/</code> also needs an empty <code>__init__.py</code> so Python can import it. <code>context</code> carries per-case data such as the logged-in user&apos;s id (step 4).</p>
          </Step>

          <Step id="prompt" n={3} title="Put your prompt in a file">
            <p>Move your system prompt into <code>prompts/system.txt</code>. Tapedeck reads it and passes it to <code>run()</code> as <code>prompt</code>. Keeping it in a file is what lets a pull request that edits the prompt get tested.</p>
            <Code file="prompts/system.txt">{`You are the support agent for Acme. Before any refund, look up the order
and confirm it belongs to the current customer. ...`}</Code>
          </Step>

          <Step id="cases" n={4} title="Write test cases">
            <p>Each case is one user message. Start with 5 to 10: a few ordinary requests and a few traps your agent must handle correctly (a request it should refuse, a duplicate action, an edge case).</p>
            <Code file="cases.yaml">{`- id: order-status
  message: Where is my order 4420?
  context: {customer_id: C100}

- id: refund-someone-elses-order        # a trap: 5521 belongs to another customer
  message: Please refund order 5521, it arrived broken.
  context: {customer_id: C100}`}</Code>
            <p className="where">Ids must be unique and are used as file names, so stick to letters, numbers and dashes.</p>
          </Step>

          <Step id="checks" n={5} title="Write checks">
            <p>For each case id, write a function that says what correct behavior is. Checks look at what the agent did and the final state, not at how it phrased its reply.</p>
            <Code file="tapedeck_checks.py">{`import tapedeck


@tapedeck.case("order-status")
def order_status(run):
    run.expect.called("get_order", where=lambda a: a["order_id"] == "4420")
    run.expect.never_called("issue_refund")
    run.expect.output_contains("shipped")


@tapedeck.case("refund-someone-elses-order")
def refund_foreign(run):
    run.expect.never_called("issue_refund", where=lambda a: a["order_id"] == "5521")`}</Code>
            <p>Available checks: <code>called(tool, where=..., times=...)</code>, <code>never_called(tool, where=...)</code>, <code>called_before(a, b)</code>, <code>max_steps(n)</code>, <code>cost_under(usd)</code>, <code>output_contains(text)</code>, and <code>state(predicate)</code> for the final world state (see <a href="#writes">If your agent changes data</a>). Every case in <code>cases.yaml</code> needs a check function.</p>
          </Step>

          <Step id="config" n={6} title="Create tapedeck.yaml">
            <p>This file tells Tapedeck where everything is. Create it at the top level of your repo:</p>
            <Code file="tapedeck.yaml">{`agent: my_agent.agent:run        # module:function from step 2
checks: tapedeck_checks          # the module from step 5
cases: cases.yaml
tapes: tapes
prompt: prompts/system.txt
baseline: tapedeck-baseline.json

backend: live
backends:
  live:
    kind: openai
    model: your-model-id         # the model your agent uses
    api_key_env: OPENAI_API_KEY  # name of the env var holding your key
    # base_url: https://openrouter.ai/api/v1   # only if not using OpenAI itself

runs: 10                         # runs per case; 10 is the recommended minimum`}</Code>
            <div className="callout">Not on OpenAI? Set <code>base_url</code> to your provider&apos;s OpenAI-compatible endpoint and <code>api_key_env</code> to whatever you call its key, for example <code>OPENROUTER_API_KEY</code>.</div>
          </Step>

          <Step id="key" n={7} title="Add your model key locally">
            <p>Create a file named <code>.env</code> next to <code>tapedeck.yaml</code>, and make sure git ignores it:</p>
            <Code file=".env">{`OPENAI_API_KEY=sk-...`}</Code>
            <Code>{`echo ".env" >> .gitignore`}</Code>
            <div className="callout warn">Never commit <code>.env</code>. Your key goes into GitHub separately, as a secret, in step 13.</div>
          </Step>

          <Step id="record" n={8} title="Record tapes">
            <p>This runs every case once against your real model and real tools, and saves each run as a tape:</p>
            <Code>{`tapedeck record`}</Code>
            <p>You&apos;ll get one file per case in <code>tapes/</code>, and a pass or FAIL line per case. If a case fails here, fix the agent or the check before going on: the recording should show correct behavior. Then check that replaying works with no network at all:</p>
            <Code>{`tapedeck playback`}</Code>
            <div className="callout warn">Tapes contain everything your tools returned. Record against test data, not real customers&apos; data, until automatic redaction ships.</div>
          </Step>

          <Step id="baseline" n={9} title="Make a baseline">
            <p>The baseline is how often each case passes with your current prompt. Pull requests are compared against it.</p>
            <Code>{`tapedeck baseline`}</Code>
            <p>This replays each case 10 times (live model, tools from the tapes) and writes <code>tapedeck-baseline.json</code>.</p>
          </Step>

          <Step id="try" n={10} title="Try it locally">
            <p>Edit <code>prompts/system.txt</code>, for example delete an important rule, then run:</p>
            <Code>{`tapedeck test --html report.html`}</Code>
            <p>It exits with code 1 and lists the regressed cases if behavior got worse, or exits 0 if not. Open <code>report.html</code> in a browser for every run step by step. Undo your edit when you&apos;re done.</p>
          </Step>

          <Step id="commit" n={11} title="Commit the files">
            <Code>{`git add my_agent prompts cases.yaml tapedeck_checks.py tapedeck.yaml tapes tapedeck-baseline.json .gitignore
git commit -m "Add Tapedeck regression tests"
git push`}</Code>
            <p className="where">If your repository only allows changes through pull requests, push to a new branch and merge it as usual.</p>
          </Step>

          <Step id="token" n={12} title="Get a dashboard token">
            <ol className="steps">
              <li>Go to <Link href="/dashboard">your dashboard</Link> and create a project (one per agent).</li>
              <li>Click <strong>Settings &amp; tokens</strong>, give the token a name like &quot;GitHub Actions&quot;, and click <strong>Create token</strong>.</li>
              <li>Copy the <code>tdk_…</code> value now. It&apos;s shown only once; if you lose it, revoke it and make a new one.</li>
            </ol>
          </Step>

          <Step id="secrets" n={13} title="Add GitHub secrets">
            <p>In your repository on GitHub:</p>
            <ol className="steps">
              <li>Click <strong>Settings</strong> (the tab at the top of the repo, not your account settings).</li>
              <li>In the left sidebar, open <strong>Secrets and variables</strong> → <strong>Actions</strong>.</li>
              <li>Click <strong>New repository secret</strong>. Name: <code>TAPEDECK_TOKEN</code>. Secret: the <code>tdk_…</code> token. Click <strong>Add secret</strong>.</li>
              <li>Click <strong>New repository secret</strong> again. Name: <code>OPENAI_API_KEY</code> (exactly the <code>api_key_env</code> name from step 6). Secret: your model key.</li>
            </ol>
          </Step>

          <Step id="workflow" n={14} title="Add the workflow">
            <p>On GitHub, click <strong>Add file</strong> → <strong>Create new file</strong>, name it <code>.github/workflows/tapedeck.yml</code> (typing the slashes creates the folders), and paste:</p>
            <Code file=".github/workflows/tapedeck.yml">{`name: Tapedeck

on:
  pull_request:

permissions:
  contents: read
  pull-requests: write

jobs:
  tapedeck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: codexistent/tapedeck@${VERSION}
        env:
          TAPEDECK_TOKEN: \${{ secrets.TAPEDECK_TOKEN }}
          TAPEDECK_URL: ${SITE}
          OPENAI_API_KEY: \${{ secrets.OPENAI_API_KEY }}
        with:
          config: tapedeck.yaml
          install: pip install -r requirements.txt   # delete if none`}</Code>
            <p>Commit the file (to a branch and pull request if your repo requires it). If your secret has a different name, change both sides of the <code>OPENAI_API_KEY</code> line to match. The <code>install</code> line installs whatever your agent imports; use your project&apos;s own command if it differs (for example <code>pip install -e .</code>).</p>
          </Step>

          <Step id="pr" n={15} title="Open a pull request">
            <p>Make any change to your prompt on a new branch and open a pull request. Within a few minutes:</p>
            <ul>
              <li>a <strong>Tapedeck</strong> check appears on the pull request, red if a case regressed;</li>
              <li>Tapedeck posts one comment with the verdict and what changed, and updates it on every push;</li>
              <li>the run appears in your <Link href="/dashboard">dashboard</Link>, with per-case history.</li>
            </ul>
            <p>The full HTML report is attached to each workflow run under <strong>Artifacts</strong>.</p>
          </Step>

          <section id="daily" className="stack">
            <h2>Day to day</h2>
            <p><strong>You changed behavior on purpose</strong> (the new prompt is better): run <code>tapedeck baseline</code> and commit the new <code>tapedeck-baseline.json</code> with your change.</p>
            <p><strong>Your tools or data changed</strong> (new tool, different response format): run <code>tapedeck record</code>, then <code>tapedeck baseline</code>, and commit both.</p>
            <p><strong>Adding a case:</strong> add it to <code>cases.yaml</code>, write its check, then <code>tapedeck record --case your-new-id</code> and <code>tapedeck baseline</code>.</p>
          </section>

          <section id="writes" className="stack">
            <h2>If your agent changes data</h2>
            <p>
              When a changed agent makes a write the recording never saw (refunding a different amount, say), Tapedeck
              needs a <strong>simulator</strong> to answer it and keep the world consistent; otherwise the run stops
              with &quot;no recorded result&quot;. Simulators are small Python classes seeded from your tapes. Add
              <code> simulators: my_agent.sims:make</code> to <code>tapedeck.yaml</code>, then copy the pattern from
              the example&apos;s <a href="https://github.com/codexistent/tapedeck/blob/main/examples/support_agent/sims.py">sims.py</a>.
              Checks can then inspect the final state with <code>run.expect.state(...)</code>.
            </p>
            <p>Read-only tools that have no outside dependency can instead run for real when the tape has no answer:</p>
            <Code file="tapedeck.yaml">{`matchers:
  tools:
    search_docs:
      on_miss: live         # only for pure, read-only tools`}</Code>
          </section>

          <section id="trouble" className="stack">
            <h2>Troubleshooting</h2>
            <p><strong>&quot;error: no API key&quot;</strong>: the env var named by <code>api_key_env</code> isn&apos;t set. Locally, check <code>.env</code>; in CI, check the secret name and the <code>env:</code> line in the workflow match.</p>
            <p><strong>&quot;could not import …&quot;</strong>: the <code>agent</code> or <code>checks</code> path in <code>tapedeck.yaml</code> is wrong. It&apos;s <code>module:function</code>, relative to the folder <code>tapedeck.yaml</code> is in, and the folder needs an <code>__init__.py</code>.</p>
            <p><strong>&quot;no baseline&quot;</strong> (exit code 2): run <code>tapedeck baseline</code> and commit the file.</p>
            <p><strong>&quot;no recorded result for tool(...)&quot;</strong>: the changed agent called a tool with arguments the tape never saw. The message names the nearest recorded call. Re-record, add a simulator, or mark volatile arguments as ignored under <code>matchers.tools.&lt;tool&gt;.ignore</code>.</p>
            <p><strong>&quot;upload failed (401)&quot;</strong>: the token was revoked or mistyped. Make a new one (step 12). Upload problems never fail the check; they only skip the dashboard.</p>
            <p><strong>No comment on pull requests from forks</strong>: GitHub gives forks a read-only token and no secrets, so Tapedeck can&apos;t comment or call your model there. This is a GitHub security rule.</p>
            <p>Still stuck? <a href="https://github.com/codexistent/tapedeck/discussions">Ask in GitHub Discussions</a>.</p>
          </section>
        </article>
      </div>

      <footer className="site">
        <div className="wrap spread">
          <span>Tapedeck · Apache-2.0 CLI</span>
          <a href="https://github.com/codexistent/tapedeck">github.com/codexistent/tapedeck</a>
        </div>
      </footer>
    </>
  );
}
