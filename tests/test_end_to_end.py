"""The whole loop on the example agent, offline, with the scripted model.

This is the demo as a test: a prompt that drops the ownership rule must be
flagged on the trap case, and a reworded greeting must pass.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tapedeck.cli import app
from tapedeck.config import Config
from tapedeck.report import build_report, to_html, to_markdown
from tapedeck.runner import load_baseline, playback_case, record_case, run_suite, save_baseline

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "support_agent"


@pytest.fixture(scope="module")
def config(tmp_path_factory: pytest.TempPathFactory) -> Config:
    """A copy of the example with freshly recorded tapes and baseline."""
    root = tmp_path_factory.mktemp("example") / "support_agent"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("tapes", "*.json", "__pycache__"))
    config_text = (root / "tapedeck.yaml").read_text()
    (root / "tapedeck.yaml").write_text(config_text.replace("backend: live", "backend: scripted"))
    cfg = Config.load(root / "tapedeck.yaml")
    v1 = (root / "prompts" / "v1.txt").read_text()
    for spec in cfg.load_cases():
        assert record_case(cfg, spec, v1).passed, spec.id
    save_baseline(cfg, run_suite(cfg, v1))
    return cfg


def prompt(cfg: Config, name: str) -> str:
    return cfg.path(f"prompts/{name}.txt").read_text()


def test_playback_passes_every_case(config: Config) -> None:
    for spec in config.load_cases():
        assert playback_case(config, spec, prompt(config, "v1")).passed, spec.id


def test_baseline_is_clean(config: Config) -> None:
    base = load_baseline(config.path(config.baseline))
    assert all(c.passes == c.n == 10 for c in base.counts.values())


def test_broken_prompt_is_caught_on_the_trap_only(config: Config) -> None:
    result = run_suite(config, prompt(config, "broken"))
    report = build_report(result, load_baseline(config.path(config.baseline)))
    assert [c.case for c in report.verdict.regressed] == ["refund-someone-elses-order"]
    sentence = report.explanations["refund-someone-elses-order"]
    assert "added a call to issue_refund after get_order" in sentence
    markdown = to_markdown(report)
    assert markdown.startswith("<!-- tapedeck -->")
    assert "❌" in markdown and "refund-someone-elses-order" in markdown
    html = to_html(report)
    assert "1 regression in 8 cases" in html


def test_harmless_prompt_passes(config: Config) -> None:
    result = run_suite(config, prompt(config, "harmless"))
    report = build_report(result, load_baseline(config.path(config.baseline)))
    assert report.verdict.passed
    assert not result.errors


def test_cli_exit_codes(config: Config, tmp_path: Path) -> None:
    runner = CliRunner()
    cfg_file = str(config.root / "tapedeck.yaml")
    md = tmp_path / "summary.md"
    bad = runner.invoke(
        app, ["test", "-c", cfg_file, "-p", str(config.path("prompts/broken.txt")), "--md", str(md)]
    )
    assert bad.exit_code == 1, bad.output
    assert "1 regression" in bad.output and md.exists()
    good = runner.invoke(
        app, ["test", "-c", cfg_file, "-p", str(config.path("prompts/harmless.txt"))]
    )
    assert good.exit_code == 0, good.output


def test_budget_aborts(config: Config) -> None:
    from tapedeck.errors import BudgetExceeded

    config.prices = {"scripted/support-v1": (1000.0, 1000.0)}
    try:
        with pytest.raises(BudgetExceeded):
            run_suite(config, prompt(config, "v1"), budget_usd=0.01)
    finally:
        config.prices = {}
