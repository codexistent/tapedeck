"""The upload payload and HTTP behavior, against a local stub server."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from tapedeck.report import build_report
from tapedeck.runner import Baseline, SuiteResult
from tapedeck.stats import Counts
from tapedeck.upload import payload, upload


def report():  # type: ignore[no-untyped-def]
    result = SuiteResult(prompt_sha="cand", model="m/x")
    base = Baseline(
        model="m/x",
        prompt_sha="base",
        counts={"trap": Counts(10, 10), "ok": Counts(10, 10)},
        signatures={"trap": [("get_order",)] * 10, "ok": [("get_order",)] * 10},
    )
    from tapedeck.tape import MetaEvent, Tape, ToolCallEvent, Usage
    from tapedeck.verify import CheckResult, Run

    def run(case: str, i: int, passed: bool, sig: list[str]) -> Run:
        events = [
            ToolCallEvent(step=n + 1, id=f"t{n}", name=name, args={}, result=None)
            for n, name in enumerate(sig)
        ]
        r = Run(
            case=case,
            index=i,
            trajectory=Tape(
                meta=MetaEvent(case=case, model="m/x", prompt_sha="p", created_at="t"),
                events=events,
            ),
            state={},
            usage=Usage(),
            cost_usd=0.001,
            wall_ms=1,
        )
        r.checks.append(CheckResult("never_called(x)", passed, "x was called"))
        return r

    result.runs["trap"] = [run("trap", i, i == 0, ["get_order", "issue_refund"]) for i in range(10)]
    result.runs["ok"] = [run("ok", i, True, ["get_order"]) for i in range(10)]
    return build_report(result, base, prompt_label="broken.txt")


def test_payload_shape_matches_dashboard_schema() -> None:
    body = payload(report())
    assert body["tapedeck_upload"] == 1 and body["passed"] is False
    assert body["runs_per_case"] == 10 and body["model"] == "m/x"
    trap = next(c for c in body["cases"] if c["case"] == "trap")
    assert trap["regressed"] is True
    assert trap["candidate"] == {"passes": 1, "n": 10}
    assert "added a call to issue_refund" in trap["explanation"]
    assert trap["failing_check"].startswith("never_called(x)")
    ok = next(c for c in body["cases"] if c["case"] == "ok")
    assert ok["failing_check"] is None
    json.dumps(body)  # serializable


class _Handler(BaseHTTPRequestHandler):
    received: list[dict[str, Any]] = []
    status = 201

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers["Content-Length"])
        _Handler.received.append(
            {"auth": self.headers["Authorization"], "body": json.loads(self.rfile.read(length))}
        )
        self.send_response(_Handler.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        reply = (
            {"url": "http://dash/o/a/p/b/runs/1"}
            if _Handler.status == 201
            else {"error": "unknown or revoked token"}
        )
        self.wfile.write(json.dumps(reply).encode())

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def server():  # type: ignore[no-untyped-def]
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    _Handler.received.clear()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.mark.enable_socket
def test_upload_sends_bearer_token(server: str) -> None:
    _Handler.status = 201
    sent = upload(report(), token="tdk_abc", url=server)
    assert sent.ok and sent.url == "http://dash/o/a/p/b/runs/1"
    assert _Handler.received[0]["auth"] == "Bearer tdk_abc"


@pytest.mark.enable_socket
def test_upload_reports_server_errors_without_raising(server: str) -> None:
    _Handler.status = 401
    sent = upload(report(), token="tdk_bad", url=server)
    assert not sent.ok and "401" in sent.message and "revoked" in sent.message


def test_upload_without_token_is_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAPEDECK_TOKEN", raising=False)
    assert not upload(report(), token=None, url="http://nowhere").ok
