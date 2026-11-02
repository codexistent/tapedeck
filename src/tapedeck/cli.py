"""The ``tapedeck`` command line."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from dotenv import find_dotenv, load_dotenv

from .config import CaseSpec, Config
from .errors import BudgetExceeded
from .report import build_report, terminal_lines, write_reports
from .runner import (
    load_baseline,
    playback_case,
    record_case,
    run_suite,
    save_baseline,
    save_runs,
)
from .stats import false_alarm_rate, power
from .verify import Run

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Regression tests for AI agents: record, replay, and gate changes with statistics.",
)

ConfigOpt = Annotated[
    Path, typer.Option("--config", "-c", help="Path to tapedeck.yaml.", exists=True)
]
PromptOpt = Annotated[
    Path | None, typer.Option("--prompt", "-p", help="Prompt file (default: config's prompt).")
]
CaseOpt = Annotated[
    list[str] | None, typer.Option("--case", help="Only these case ids (repeatable).")
]


def _setup(config_path: Path) -> Config:
    load_dotenv(find_dotenv(usecwd=True))
    return Config.load(config_path)


def _prompt(config: Config, prompt: Path | None) -> tuple[str, str]:
    path = prompt if prompt is not None else config.path(config.prompt)
    if not path.exists() and not path.is_absolute():
        path = config.path(str(path))
    if not path.exists():
        raise typer.BadParameter(f"prompt file not found: {path}")
    return path.read_text(encoding="utf-8"), path.name


def _select(config: Config, ids: list[str] | None) -> list[CaseSpec]:
    cases = config.load_cases()
    if not ids:
        return cases
    known = {c.id for c in cases}
    unknown = sorted(set(ids) - known)
    if unknown:
        raise typer.BadParameter(f"unknown case id(s): {', '.join(unknown)}")
    return [c for c in cases if c.id in ids]


def _status(run: Run) -> str:
    if run.passed:
        return typer.style("pass", fg="green")
    detail = run.error or next((f"{c.name}: {c.reason}" for c in run.checks if not c.passed), "")
    return typer.style("FAIL", fg="red") + f"  {detail}"


@app.command()
def record(
    config: ConfigOpt = Path("tapedeck.yaml"),
    prompt: PromptOpt = None,
    case: CaseOpt = None,
) -> None:
    """Record live runs (real model, real tools) into tapes."""
    cfg = _setup(config)
    text, label = _prompt(cfg, prompt)
    typer.echo(f"recording with {label} on backend {cfg.backend!r}")
    for spec in _select(cfg, case):
        run = record_case(cfg, spec, text)
        typer.echo(f"  {spec.id:40} {_status(run)}  -> {cfg.tape_path(spec.id).name}")


@app.command()
def playback(
    config: ConfigOpt = Path("tapedeck.yaml"),
    prompt: PromptOpt = None,
    case: CaseOpt = None,
) -> None:
    """Replay tapes with no model and no network. Checks that the harness still works."""
    cfg = _setup(config)
    text, _ = _prompt(cfg, prompt)
    cfg.load_checks()
    failed = 0
    for spec in _select(cfg, case):
        run = playback_case(cfg, spec, text)
        failed += not run.passed
        typer.echo(f"  {spec.id:40} {_status(run)}")
    raise typer.Exit(code=1 if failed else 0)


@app.command()
def baseline(
    config: ConfigOpt = Path("tapedeck.yaml"),
    prompt: PromptOpt = None,
    runs: Annotated[int | None, typer.Option(help="Runs per case.")] = None,
) -> None:
    """Replay every case N times with the current prompt and save the baseline."""
    cfg = _setup(config)
    text, label = _prompt(cfg, prompt)
    typer.echo(f"computing baseline from {label}, {runs or cfg.runs} runs per case")
    result = run_suite(cfg, text, runs=runs)
    path = save_baseline(cfg, result)
    for case_id, counts in result.counts().items():
        typer.echo(f"  {case_id:40} {counts.passes}/{counts.n}")
    typer.echo(f"wrote {path}")


@app.command()
def test(
    config: ConfigOpt = Path("tapedeck.yaml"),
    prompt: PromptOpt = None,
    runs: Annotated[int | None, typer.Option(help="Runs per case.")] = None,
    budget: Annotated[float | None, typer.Option(help="Abort above this cost (USD).")] = None,
    html: Annotated[Path | None, typer.Option(help="Write an HTML report here.")] = None,
    md: Annotated[Path | None, typer.Option(help="Write a Markdown summary here.")] = None,
    save: Annotated[bool, typer.Option(help="Save every run's trajectory.")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Replay the candidate against the tapes and compare with the baseline.

    Exits 1 on a regression, 2 on a usage or budget error.
    """
    cfg = _setup(config)
    text, label = _prompt(cfg, prompt)
    base_path = cfg.path(cfg.baseline)
    if not base_path.exists():
        typer.echo(f"no baseline at {base_path}; run `tapedeck baseline` first", err=True)
        raise typer.Exit(code=2)
    base = load_baseline(base_path)
    try:
        result = run_suite(cfg, text, runs=runs, budget_usd=budget)
    except BudgetExceeded as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from None
    report = build_report(
        result, base, prompt_label=label, alpha=cfg.alpha, min_effect=cfg.min_effect
    )
    write_reports(report, html, md)
    if save:
        typer.echo(f"runs saved to {save_runs(result, cfg.path('.tapedeck/runs'))}")
    if not quiet:
        typer.echo(f"{label} vs baseline ({base.prompt_sha}):")
        for line in terminal_lines(report):
            typer.echo(line)
    colour = "green" if report.verdict.passed else "red"
    typer.echo(typer.style(report.headline, fg=colour, bold=True))
    raise typer.Exit(code=0 if report.verdict.passed else 1)


@app.command(name="power")
def power_table(
    cases: Annotated[int, typer.Option(help="Number of cases in the suite.")] = 8,
    base_rate: Annotated[float, typer.Option(help="True baseline pass rate.")] = 0.95,
    alpha: float = 0.05,
    min_effect: float = 0.2,
    trials: int = 2000,
) -> None:
    """Simulate the false-alarm rate and detection power for several N."""
    rates = [base_rate] * cases
    typer.echo(f"{cases} cases, true pass rate {base_rate}, alpha {alpha}, min effect {min_effect}")
    typer.echo(f"{'N':>4} {'false alarms':>13} {'catch to 0.5':>13} {'catch to 0.2':>13}")
    for n in (5, 10, 20):
        fa = false_alarm_rate(rates, n, trials=trials, alpha=alpha, min_effect=min_effect)
        p5 = power(rates, 0, 0.5, n, trials=trials, alpha=alpha, min_effect=min_effect)
        p2 = power(rates, 0, 0.2, n, trials=trials, alpha=alpha, min_effect=min_effect)
        typer.echo(f"{n:>4} {fa:>13.3f} {p5:>13.3f} {p2:>13.3f}")


if __name__ == "__main__":
    app()
