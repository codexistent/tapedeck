"""Sending a run's results to a Tapedeck dashboard.

Only results leave the machine: per-case pass counts, p-values and the one-line
explanation. Tapes, prompts and trajectories stay in the repository.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .report import Report, _first_failing_check

DEFAULT_URL = "https://tapedeck.vercel.app"


@dataclass
class UploadResult:
    ok: bool
    message: str
    url: str | None = None


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=5, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


def ci_context() -> dict[str, Any]:
    """Commit, branch and PR number from GitHub Actions, falling back to local git."""
    pr: int | None = None
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        try:
            with open(event_path, encoding="utf-8") as fh:
                event = json.load(fh)
            number = (event.get("pull_request") or {}).get("number")
            pr = int(number) if number else None
            sha = (event.get("pull_request") or {}).get("head", {}).get("sha")
        except (OSError, ValueError):
            sha = None
    else:
        sha = None
    return {
        "commit_sha": sha or os.environ.get("GITHUB_SHA") or _git("rev-parse", "HEAD"),
        "branch": os.environ.get("GITHUB_HEAD_REF")
        or os.environ.get("GITHUB_REF_NAME")
        or _git("rev-parse", "--abbrev-ref", "HEAD"),
        "pr_number": pr,
    }


def payload(report: Report) -> dict[str, Any]:
    v = report.verdict
    return {
        "tapedeck_upload": 1,
        "passed": v.passed,
        "model": report.result.model,
        "prompt_label": report.prompt_label or None,
        "prompt_sha": report.result.prompt_sha,
        "baseline_prompt_sha": report.baseline.prompt_sha,
        "runs_per_case": max((c.candidate.n for c in v.cases), default=1) or 1,
        "alpha": v.alpha,
        "min_effect": v.min_effect,
        "cost_usd": round(report.result.cost_usd, 6),
        "error_count": len(report.result.errors),
        **ci_context(),
        "cases": [
            {
                "case": c.case,
                "baseline": {"passes": c.baseline.passes, "n": c.baseline.n},
                "candidate": {"passes": c.candidate.passes, "n": c.candidate.n},
                "p_adjusted": c.p_adjusted,
                "regressed": c.regressed,
                "explanation": report.explanations.get(c.case),
                "failing_check": _first_failing_check(report, c.case) if c.regressed else None,
            }
            for c in v.cases
        ],
    }


def upload(report: Report, *, token: str | None = None, url: str | None = None) -> UploadResult:
    """POST the report to ``{url}/api/v1/runs``. Never raises: CI shouldn't fail on upload."""
    token = token or os.environ.get("TAPEDECK_TOKEN")
    base = (url or os.environ.get("TAPEDECK_URL") or DEFAULT_URL).rstrip("/")
    if not token:
        return UploadResult(False, "no TAPEDECK_TOKEN set; create one in the dashboard")
    body = json.dumps(payload(report)).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/api/v1/runs",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "tapedeck-cli",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        return UploadResult(True, "uploaded", data.get("url"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", "")
        except (ValueError, OSError):
            detail = ""
        return UploadResult(False, f"upload failed ({exc.code}): {detail or exc.reason}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return UploadResult(False, f"upload failed: {exc}")
