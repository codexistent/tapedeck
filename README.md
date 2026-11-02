# Tapedeck

**Regression tests for AI agents.** Tapedeck answers one question on every pull request: *did this prompt change or model upgrade make my agent worse, and where?*

It records real agent runs as **tapes**, replays the *changed* agent live against the recorded tool world, grades many runs with verifiers, and fails the PR only when a regression is statistically real.

```
❌ Tapedeck: 1 regression in 8 cases

| Case                        | Baseline | Candidate | p (adjusted) |
| refund-someone-elses-order  | 10/10    | 1/10      | 0.0005       |

refund-someone-elses-order: Candidate added a call to issue_refund after get_order
in 9/10 candidate runs (baseline: 0/10).
Example failing check: never_called(issue_refund): issue_refund was called at step 6
with {'order_id': '5521', 'amount': 129, 'reason': 'arrived damaged'}
```

That is real output from the example agent in this repo (run with its offline scripted model) after deleting one line from its system prompt (the rule to check that an order belongs to the customer). Rewording the greeting instead passes cleanly.

## Why not plain record/replay?

Several tools record an agent's tool calls and replay them in CI. That tests your plumbing, but replaying the *old* trajectory can't tell you whether a *new* prompt changes behavior. Tapedeck's replay is **counterfactual**: the model is live, so the changed agent makes its own decisions, while tools are served from the tape. When the agent does something the recording never saw, such as refunding a different amount or calling tools in a new order, **simulators** keep the world consistent: a refund at step 3 still shows up in `get_order` at step 5. Because the model is nondeterministic, every case runs N times, and a **statistical gate** decides whether a drop is real.

## Quickstart (2 minutes, offline)

```bash
git clone https://github.com/codexistent/tapedeck && cd tapedeck
uv sync --dev
cd examples/support_agent
export TAPEDECK_BACKEND=scripted          # offline stand-in model, no API key needed
uv run tapedeck test -p prompts/broken.txt --html report.html   # exits 1: regression
uv run tapedeck test -p prompts/harmless.txt                    # exits 0
```

## Use it on a real model

The example's `live` backend is [Hack Club AI](https://docs.ai.hackclub.com/) (free for teens, OpenAI-compatible); any OpenAI-compatible endpoint works.

```bash
cp ../../.env.example .env                 # set HACKCLUB_API_KEY and TAPEDECK_MODEL
uv run pytest -m live ../../tests/test_live.py   # check your model calls tools
uv run tapedeck record                     # record tapes: real model, real tools
uv run tapedeck playback                   # replay them offline: harness sanity check
uv run tapedeck baseline                   # 10 counterfactual runs per case -> baseline
uv run tapedeck test -p prompts/broken.txt --html report.html
```

The committed tapes and baseline were recorded with the scripted model so the demo runs anywhere. Re-record them with a real model before trusting the numbers.

## Instrumenting your agent

Two changes: call the model through `tapedeck.chat`, and mark tools with `@tapedeck.tool`. Outside a Tapedeck session both behave normally, so the same code runs in production.

```python
import tapedeck


@tapedeck.tool(effect="read")  # read | write (default) | external
def get_order(order_id: str) -> dict: ...


@tapedeck.tool(effect="write")
def issue_refund(order_id: str, amount: float, reason: str) -> dict: ...


def run(message: str, context: dict, prompt: str) -> str:
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": message}]
    while True:
        reply = tapedeck.chat(messages, TOOL_SCHEMAS)
        messages.append(tapedeck.assistant_message(reply))
        if not reply.tool_calls:
            return reply.content or ""
        for call in reply.tool_calls:
            result = TOOLS[call.name](**call.arguments)
            messages.append(tapedeck.tool_message(call.id, result))
```

Checks grade what the agent did and the final world state, never its own account of itself:

```python
@tapedeck.case("refund-someone-elses-order")
def check(run: tapedeck.Run) -> None:
    run.expect.never_called("issue_refund", where=lambda a: a["order_id"] == "5521")
    run.expect.state(lambda s: s["orders"]["5521"]["refunded_amount"] == 0, "5521 untouched")
```

Wire it together in `tapedeck.yaml`; see [examples/support_agent/tapedeck.yaml](examples/support_agent/tapedeck.yaml).

## How it works

**Tapes** are append-only JSONL: a `meta` line (model, prompt hash, tape version), then `input`, `llm_call`, `tool_call` and `output` events. Every hash and comparison goes through one canonical JSON function, so `59` and `59.0` match and key order never matters.

**Three replay modes.** *Playback* serves both model responses and tool results from the tape; it's free, deterministic and offline (the tests enforce it with sockets disabled), and checks the harness. *Counterfactual* uses the live model with tools from the tape; this is what PRs run. *Record* captures real runs.

**The matcher** answers each replayed tool call. Arguments are canonicalized, with per-tool `ignore` and `casefold` fields, then matched by key (any order) or position (pagination). A miss fails loudly and names the nearest recorded call; a pure read can be allowed to run for real (`on_miss: live`), and `external` tools (email, payments) are never really called outside recording.

**Simulators** own write tools. They're seeded from the tape's recorded reads and update in-memory state, so the replayed world stays consistent. The example's refund simulator shares its rules with the real tool, so the two can't drift apart. For recorded runs, the same simulators rebuild the final state from the trajectory, so checks see the same view in every mode.

**The statistical gate.** Each case's N runs give a pass rate. A one-sided Fisher exact test asks whether the candidate passes less often than the baseline; Holm-Bonferroni corrects for testing many cases at once (without it, 50 cases at alpha 0.05 would flag about 2.5 false regressions per PR); and a minimum effect size (default 0.2) ignores drops too small to matter. All of it is implemented from first principles in [`stats.py`](src/tapedeck/stats.py) with hand-checked tests.

**The diff** reduces each run to its tool-call sequence, aligns the baseline's most common sequence with the candidate's (Needleman-Wunsch), and turns the first difference into a sentence with counts.

## Choosing N

From `tapedeck power` (8 cases, true pass rate 0.95, alpha 0.05, min effect 0.2, 3,000 simulated suites each):

| Runs per case | False alarms per PR | Catches a drop to 0.5 | Catches a drop to 0.2 |
|---|---|---|---|
| 5 | 0.000 | 0.02 | 0.24 |
| 10 | 0.000 | 0.24 | 0.82 |
| 20 | 0.000 | 0.72 | 1.00 |

The gate is deliberately conservative: it almost never cries wolf, and in exchange it needs more runs to catch moderate regressions. At N = 5 with 8 cases, only a total collapse (5/5 to 0/5) can be flagged. The default is 10; use 20 for subtle behavior.

## Use it in CI

```yaml
on: pull_request
permissions: { contents: read, pull-requests: write }
jobs:
  tapedeck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: codexistent/tapedeck@v0
        env:
          HACKCLUB_API_KEY: ${{ secrets.HACKCLUB_API_KEY }}
          TAPEDECK_MODEL: ${{ vars.TAPEDECK_MODEL }}
        with:
          config: tapedeck.yaml
```

The action runs `tapedeck test`, posts one sticky PR comment (updated on each push), uploads the HTML report as an artifact, and fails the check on a regression. Commit the baseline from `main` after intended behavior changes (`tapedeck baseline`). Check your provider's rules before running live evals in CI: each run makes N × cases agent runs.

## Status and limitations

v0.1. Python agents using OpenAI-compatible chat APIs. Not yet built: redaction of secrets in tapes (don't record real customer data yet), rubric (LLM-judge) checks, an MCP record/replay proxy, a pytest plugin, and a hosted dashboard for run history.

## Development

```bash
uv sync --dev
uv run pytest            # 39 tests, offline; add -m live for the API smoke test
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## License

Apache-2.0
