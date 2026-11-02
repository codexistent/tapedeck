"""Running cases: recording tapes, replaying a suite N times, and storing baselines."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .canonical import sha256
from .config import CaseSpec, Config, stable_seed
from .errors import BudgetExceeded
from .session import Session, record, replay
from .simulators import derive_state
from .stats import Counts
from .verify import Run, registry

BASELINE_FORMAT = 1


def _finish(
    config: Config, session: Session, spec: CaseSpec, index: int, started: float, error: str | None
) -> Run:
    model = session.meta.model
    trajectory = session.trajectory()
    if session.mode == "counterfactual":
        state = session.state
    else:
        state = derive_state(config.make_simulators(), trajectory)
    run = Run(
        case=spec.id,
        index=index,
        trajectory=trajectory,
        state=state,
        usage=session.usage.model_copy(),
        cost_usd=config.cost(model, session.usage.input_tokens, session.usage.output_tokens),
        wall_ms=int((time.perf_counter() - started) * 1000),
        match_log=list(session.match_log),
        error=error,
    )
    return registry.grade(run)


def _drive(session: Session, config: Config, spec: CaseSpec, prompt: str) -> str | None:
    """Run the agent inside an active session; return an error string if it crashed."""
    session.input(spec.message, spec.context)
    try:
        reply = config.agent_fn()(spec.message, spec.context, prompt)
    except Exception as exc:  # the run fails; the suite keeps going
        return f"{type(exc).__name__}: {exc}"
    session.output(reply)
    return None


def record_case(config: Config, spec: CaseSpec, prompt: str) -> Run:
    """Record one live run of ``spec`` to its tape and grade it."""
    config.load_checks()
    started = time.perf_counter()
    with record(
        config.tape_path(spec.id),
        case=spec.id,
        backend=config.make_backend(seed=stable_seed(spec.id, "record")),
        prompt=prompt,
    ) as session:
        error = _drive(session, config, spec, prompt)
    return _finish(config, session, spec, 0, started, error)


def replay_case(config: Config, spec: CaseSpec, prompt: str, index: int) -> Run:
    """One counterfactual run of ``spec``: live model, tools from tape and simulators."""
    started = time.perf_counter()
    with replay(
        config.tape_path(spec.id),
        mode="counterfactual",
        backend=config.make_backend(seed=stable_seed(spec.id, index)),
        simulators=config.make_simulators(),
        matchers=config.matchers,
        prompt=prompt,
    ) as session:
        error = _drive(session, config, spec, prompt)
    return _finish(config, session, spec, index, started, error)


def playback_case(config: Config, spec: CaseSpec, prompt: str) -> Run:
    """Replay a tape with no model and no tools: tests the harness, costs nothing."""
    started = time.perf_counter()
    with replay(config.tape_path(spec.id), mode="playback", prompt=prompt) as session:
        error = _drive(session, config, spec, prompt)
    return _finish(config, session, spec, 0, started, error)


@dataclass
class SuiteResult:
    prompt_sha: str
    model: str
    runs: dict[str, list[Run]] = field(default_factory=dict)

    def counts(self) -> dict[str, Counts]:
        return {c: Counts(sum(r.passed for r in rs), len(rs)) for c, rs in self.runs.items()}

    def signatures(self) -> dict[str, list[tuple[str, ...]]]:
        return {c: [r.signature for r in rs] for c, rs in self.runs.items()}

    @property
    def cost_usd(self) -> float:
        return sum(r.cost_usd for rs in self.runs.values() for r in rs)

    @property
    def errors(self) -> list[Run]:
        return [r for rs in self.runs.values() for r in rs if r.error]


def run_suite(
    config: Config,
    prompt: str,
    *,
    runs: int | None = None,
    workers: int | None = None,
    budget_usd: float | None = None,
    cases: list[CaseSpec] | None = None,
    progress: Callable[[Run], None] | None = None,
) -> SuiteResult:
    """Replay every case ``runs`` times in counterfactual mode, in parallel.

    Rate-limit errors are retried with backoff inside the OpenAI client. If the
    running cost passes ``budget_usd``, pending runs are cancelled and
    :class:`BudgetExceeded` is raised.
    """
    config.load_checks()
    specs = cases if cases is not None else config.load_cases()
    n = runs or config.runs
    budget = config.budget_usd if budget_usd is None else budget_usd
    model = config.make_backend(seed=0).model
    result = SuiteResult(prompt_sha=sha256(prompt)[:16], model=model)
    for spec in specs:
        result.runs[spec.id] = []

    lock = threading.Lock()
    spent = 0.0
    with ThreadPoolExecutor(max_workers=workers or config.workers) as pool:
        pending: set[Future[Run]] = {
            pool.submit(replay_case, config, spec, prompt, i) for spec in specs for i in range(n)
        }
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                run = future.result()
                with lock:
                    result.runs[run.case].append(run)
                    spent += run.cost_usd
                if progress is not None:
                    progress(run)
            if spent > budget:
                for future in pending:
                    future.cancel()
                raise BudgetExceeded(
                    f"spent ${spent:.2f}, over the ${budget:.2f} budget; "
                    "raise budget_usd or lower runs"
                )
    for case_runs in result.runs.values():
        case_runs.sort(key=lambda r: r.index)
    return result


# -- persistence --------------------------------------------------------------


def save_baseline(config: Config, result: SuiteResult) -> Path:
    data = {
        "tapedeck_baseline": BASELINE_FORMAT,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "model": result.model,
        "prompt_sha": result.prompt_sha,
        "cases": {
            case: {
                "passes": counts.passes,
                "n": counts.n,
                "signatures": [list(s) for s in result.signatures()[case]],
            }
            for case, counts in sorted(result.counts().items())
        },
    }
    path = config.path(config.baseline)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


@dataclass
class Baseline:
    model: str
    prompt_sha: str
    counts: dict[str, Counts]
    signatures: dict[str, list[tuple[str, ...]]]


def load_baseline(path: str | Path) -> Baseline:
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("tapedeck_baseline") != BASELINE_FORMAT:
        raise ValueError(f"{path}: not a tapedeck baseline (format {BASELINE_FORMAT})")
    cases = data["cases"]
    return Baseline(
        model=data["model"],
        prompt_sha=data["prompt_sha"],
        counts={c: Counts(v["passes"], v["n"]) for c, v in cases.items()},
        signatures={c: [tuple(s) for s in v["signatures"]] for c, v in cases.items()},
    )


def save_runs(result: SuiteResult, directory: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = directory / stamp
    out.mkdir(parents=True, exist_ok=True)
    for case, runs in result.runs.items():
        for run in runs:
            run.trajectory.save(out / f"{case}-{run.index:02d}.jsonl")
    return out
