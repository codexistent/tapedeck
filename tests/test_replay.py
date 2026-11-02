"""Record, playback and counterfactual replay with a tiny self-contained agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import tapedeck
from tapedeck import (
    ExternalToolBlocked,
    KeyValueSimulator,
    LLMResponse,
    MatcherConfig,
    Tape,
    TapeMiss,
    ToolCallRequest,
    ToolError,
    ToolMatchConfig,
)

WORLD: dict[str, int] = {}


@tapedeck.tool(effect="read")
def get_balance(account: str) -> dict[str, Any]:
    return {"account": account, "balance": WORLD.get(account, 0)}


@tapedeck.tool
def withdraw(account: str, amount: int) -> dict[str, Any]:
    if WORLD.get(account, 0) < amount:
        raise ValueError("insufficient funds")
    WORLD[account] -= amount
    return {"ok": True}


@tapedeck.tool(effect="external")
def send_email(to: str, body: str) -> dict[str, Any]:
    raise AssertionError("an external tool must never run in a test")


class Script:
    """A backend that returns a fixed list of responses."""

    model = "test/script"

    def __init__(self, *steps: LLMResponse) -> None:
        self.steps = list(steps)

    def complete(self, request: dict[str, Any]) -> LLMResponse:
        return self.steps.pop(0)


def call(name: str, **args: Any) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCallRequest(id="c", name=name, arguments=args)])


def say(text: str) -> LLMResponse:
    return LLMResponse(content=text)


def agent() -> str:
    """Ask the model, run whatever tools it calls, until it answers."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": "go"}]
    for _ in range(6):
        reply = tapedeck.chat(messages)
        messages.append(tapedeck.assistant_message(reply))
        if not reply.tool_calls:
            return reply.content or ""
        for c in reply.tool_calls:
            fn = {"get_balance": get_balance, "withdraw": withdraw, "send_email": send_email}
            try:
                result = fn[c.name](**c.arguments)
            except (TapeMiss, ExternalToolBlocked):
                raise
            except Exception as exc:
                result = {"error": str(exc)}
            messages.append(tapedeck.tool_message(c.id, result))
    return "gave up"


@pytest.fixture
def tape_path(tmp_path: Path) -> Path:
    WORLD.clear()
    WORLD["acct"] = 100
    path = tmp_path / "t.jsonl"
    backend = Script(
        call("get_balance", account="acct"),
        call("withdraw", account="acct", amount=30),
        call("get_balance", account="acct"),
        say("done"),
    )
    with tapedeck.record(path, case="c1", backend=backend, prompt="p") as session:
        session.input("go")
        session.output(agent())
    return path


def account_sim() -> KeyValueSimulator:
    def withdraw_handler(state: dict[str, Any], args: Any) -> dict[str, Any]:
        acct = state[args["account"]]
        if acct["balance"] < args["amount"]:
            return {"error": "insufficient funds"}
        acct["balance"] -= args["amount"]
        return {"ok": True}

    return KeyValueSimulator(
        "accounts",
        read_tool="get_balance",
        key_arg="account",
        writes={"withdraw": withdraw_handler},
    )


def test_tape_round_trip_is_byte_identical(tape_path: Path) -> None:
    text = tape_path.read_text()
    assert Tape.load(tape_path).dumps() == text
    tape = Tape.load(tape_path)
    assert tape.meta.case == "c1" and tape.meta.model == "test/script"
    assert [c.name for c in tape.tool_calls()] == ["get_balance", "withdraw", "get_balance"]
    assert [c.effect for c in tape.tool_calls()] == ["read", "write", "read"]


@pytest.mark.disable_socket
def test_playback_is_deterministic_and_offline(tape_path: Path) -> None:
    outputs = set()
    for _ in range(100):
        with tapedeck.replay(tape_path) as session:
            outputs.add(agent())
        assert [c.name for c in session.trajectory().tool_calls()] == [
            "get_balance",
            "withdraw",
            "get_balance",
        ]
    assert outputs == {"done"}


def test_playback_rejects_a_different_harness(tape_path: Path) -> None:
    with tapedeck.replay(tape_path) as session, pytest.raises(TapeMiss, match="not on the tape"):
        session.chat([{"role": "user", "content": "something else"}])


def test_recorded_tool_errors_replay_as_errors(tmp_path: Path) -> None:
    WORLD.clear()
    WORLD["acct"] = 5
    path = tmp_path / "e.jsonl"
    with tapedeck.record(path, case="e", backend=Script(), prompt="") as session:
        with pytest.raises(ValueError):
            withdraw("acct", 50)
        assert session.events[-1].error == "ValueError: insufficient funds"  # type: ignore[union-attr]
    with tapedeck.replay(path), pytest.raises(ToolError, match="insufficient"):
        withdraw("acct", 50)


def test_counterfactual_keeps_the_world_consistent(tape_path: Path) -> None:
    WORLD.clear()  # real tools must not be touched in counterfactual mode
    changed = Script(
        call("withdraw", account="acct", amount=80),  # never recorded
        call("get_balance", account="acct"),
        say("withdrew more"),
    )
    with tapedeck.replay(
        tape_path, mode="counterfactual", backend=changed, simulators=[account_sim()]
    ) as session:
        assert agent() == "withdrew more"
    balances = [c.result for c in session.trajectory().tool_calls() if c.name == "get_balance"]
    assert balances == [{"account": "acct", "balance": 20}]  # 100 seeded from tape, minus 80
    assert session.state == {"accounts": {"acct": {"account": "acct", "balance": 20}}}
    assert {e.outcome for e in session.match_log} == {"simulated"}
    assert WORLD == {}


def test_counterfactual_miss_names_nearest_call(tape_path: Path) -> None:
    changed = Script(call("get_balance", account="ACCT"))
    with tapedeck.replay(tape_path, mode="counterfactual", backend=changed) as _:  # noqa: SIM117
        with pytest.raises(TapeMiss) as info:
            agent()
    assert 'nearest recorded call: get_balance({"account":"acct"})' in str(info.value)


def test_casefold_matcher_resolves_that_miss(tape_path: Path) -> None:
    config = MatcherConfig(tools={"get_balance": ToolMatchConfig(casefold=["account"])})
    changed = Script(call("get_balance", account="ACCT"), say("ok"))
    with tapedeck.replay(tape_path, mode="counterfactual", backend=changed, matchers=config):
        assert agent() == "ok"


def test_external_tools_are_never_called(tape_path: Path) -> None:
    changed = Script(call("send_email", to="a@b.c", body="hi"))
    with tapedeck.replay(tape_path, mode="counterfactual", backend=changed) as _:  # noqa: SIM117
        with pytest.raises(ExternalToolBlocked):
            agent()


def test_tools_run_normally_outside_a_session() -> None:
    WORLD.clear()
    WORLD["x"] = 3
    assert get_balance("x") == {"account": "x", "balance": 3}
    with pytest.raises(tapedeck.NoActiveSession):
        tapedeck.chat([{"role": "user", "content": "hi"}])
