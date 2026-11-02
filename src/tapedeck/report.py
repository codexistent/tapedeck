"""Turning a verdict into something a reviewer reads in ten seconds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from .diff import explain
from .runner import Baseline, SuiteResult
from .stats import CaseVerdict, SuiteVerdict, decide

MARKER = "<!-- tapedeck -->"


@dataclass
class Report:
    verdict: SuiteVerdict
    result: SuiteResult
    baseline: Baseline
    explanations: dict[str, str]
    prompt_label: str

    @property
    def headline(self) -> str:
        total = len(self.verdict.cases)
        bad = len(self.verdict.regressed)
        if bad == 0:
            return f"No regressions across {total} cases"
        return f"{bad} regression{'s' if bad != 1 else ''} in {total} cases"


def build_report(
    result: SuiteResult,
    baseline: Baseline,
    *,
    prompt_label: str = "",
    alpha: float = 0.05,
    min_effect: float = 0.2,
) -> Report:
    verdict = decide(baseline.counts, result.counts(), alpha=alpha, min_effect=min_effect)
    return Report(
        verdict=verdict,
        result=result,
        baseline=baseline,
        explanations={
            c.case: explain(baseline.signatures.get(c.case, []), result.signatures()[c.case])
            for c in verdict.regressed
        },
        prompt_label=prompt_label,
    )


def _fmt_p(p: float) -> str:
    return "<0.0001" if p < 0.0001 else f"{p:.4f}"


def _rate(c: CaseVerdict, side: str) -> str:
    counts = c.baseline if side == "base" else c.candidate
    return f"{counts.passes}/{counts.n}"


def to_markdown(report: Report) -> str:
    v = report.verdict
    icon = "✅" if v.passed else "❌"
    lines = [MARKER, f"### {icon} Tapedeck: {report.headline}", ""]
    if v.regressed:
        lines += ["| Case | Baseline | Candidate | p (adjusted) |", "|---|---|---|---|"]
        for c in v.regressed:
            lines.append(
                f"| `{c.case}` | {_rate(c, 'base')} | {_rate(c, 'cand')} | {_fmt_p(c.p_adjusted)} |"
            )
        lines.append("")
        for c in v.regressed:
            lines.append(f"**`{c.case}`**: {report.explanations[c.case]}")
            failing = _first_failing_check(report, c.case)
            if failing:
                lines.append(f"<br><sub>Example failing check: {failing}</sub>")
            lines.append("")
    errors = report.result.errors
    if errors:
        lines.append(
            f"> ⚠️ {len(errors)} run(s) crashed (counted as failures). First: "
            f"`{errors[0].case}`: {errors[0].error}"
        )
        lines.append("")
    runs = max((c.candidate.n for c in v.cases), default=0)
    lines.append(
        f"<sub>{runs} runs per case · model `{report.result.model}` · "
        f"alpha {v.alpha}, min effect {v.min_effect} · est. cost "
        f"${report.result.cost_usd:.4f}</sub>"
    )
    return "\n".join(lines) + "\n"


def _first_failing_check(report: Report, case: str) -> str | None:
    for run in report.result.runs.get(case, []):
        for check in run.checks:
            if not check.passed:
                return f"{check.name}: {check.reason}"
        if run.error:
            return f"crashed: {run.error}"
    return None


def to_html(report: Report) -> str:
    env = Environment(
        loader=PackageLoader("tapedeck", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
    )
    env.filters["p"] = _fmt_p
    template = env.get_template("report.html.j2")
    return template.render(
        report=report,
        verdict=report.verdict,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )


def write_reports(report: Report, html: Path | None, markdown: Path | None) -> None:
    if html is not None:
        html.write_text(to_html(report), encoding="utf-8")
    if markdown is not None:
        markdown.write_text(to_markdown(report), encoding="utf-8")


def terminal_lines(report: Report) -> list[str]:
    out = []
    for c in report.verdict.cases:
        status = "REGRESSED" if c.regressed else "ok"
        out.append(
            f"  {status:9} {c.case:40} {_rate(c, 'base'):>6} -> {_rate(c, 'cand'):<6} "
            f"p_adj={_fmt_p(c.p_adjusted)}"
        )
        if c.regressed:
            out.append(f"            {report.explanations[c.case]}")
    return out
