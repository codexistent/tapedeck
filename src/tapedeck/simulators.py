"""Simulators keep the replayed world consistent when the agent diverges from the tape.

Read-only tools can be answered straight from the tape. Writes cannot: if the
changed agent issues a refund the recording never saw, a later ``get_order``
must reflect it, or the world contradicts itself and the agent fails for
reasons that are not its fault. A simulator owns a set of tools, holds small
in-memory state seeded from the tape, and answers every call to its tools.
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .tape import Tape

State = dict[str, Any]
WriteHandler = Callable[[State, Mapping[str, Any]], Any]


class Simulator(ABC):
    """Base class. ``name`` is the key its state appears under in ``Run.state``."""

    name: str
    tools: frozenset[str]

    def seed(self, tape: Tape) -> None:  # noqa: B027 - optional hook
        """Initialize state from the recorded tape. Called once per replay."""

    @abstractmethod
    def handle(self, tool: str, args: Mapping[str, Any]) -> Any:
        """Answer a call to one of ``self.tools`` and update state."""

    @abstractmethod
    def snapshot(self) -> Any:
        """A deep copy of current state, for verifiers."""


class KeyValueSimulator(Simulator):
    """Records keyed by one argument, e.g. orders keyed by ``order_id``.

    Seeded from every successful recorded call to ``read_tool``: the recorded
    result becomes ``state[args[key_arg]]``. Reads then come from state, and
    each tool in ``writes`` mutates state through its handler, which returns
    the tool's result.
    """

    def __init__(
        self,
        name: str,
        *,
        read_tool: str,
        key_arg: str,
        writes: Mapping[str, WriteHandler] | None = None,
        not_found: Callable[[str], Any] | None = None,
        initial: Mapping[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.read_tool = read_tool
        self.key_arg = key_arg
        self.writes = dict(writes or {})
        self.not_found = not_found or (lambda key: {"error": f"{key_arg} {key} not found"})
        self.tools = frozenset({read_tool, *self.writes})
        self.state: State = copy.deepcopy(dict(initial or {}))

    def seed(self, tape: Tape) -> None:
        for call in tape.tool_calls():
            if call.name != self.read_tool or call.error is not None:
                continue
            if isinstance(call.result, dict) and "error" in call.result:
                continue
            key = str(call.args.get(self.key_arg))
            self.state.setdefault(key, copy.deepcopy(call.result))

    def handle(self, tool: str, args: Mapping[str, Any]) -> Any:
        if tool == self.read_tool:
            key = str(args.get(self.key_arg))
            if key not in self.state:
                return self.not_found(key)
            return copy.deepcopy(self.state[key])
        return self.writes[tool](self.state, args)

    def snapshot(self) -> Any:
        return copy.deepcopy(self.state)


def derive_state(simulators: Iterable[Simulator], tape: Tape) -> dict[str, Any]:
    """World state at the end of a recorded run, rebuilt by passing its calls through simulators.

    Recording and playback use real (or recorded) tools, so there is no live
    simulator state to grade. Seeding fresh simulators from the trajectory and
    re-applying its successful calls in order gives the state checks the same
    view they get in counterfactual mode.
    """
    sims = list(simulators)
    for sim in sims:
        sim.seed(tape)
    for call in tape.tool_calls():
        if call.error is not None:
            continue
        for sim in sims:
            if call.name in sim.tools:
                sim.handle(call.name, call.args)
    return {sim.name: sim.snapshot() for sim in sims}


class AppendLogSimulator(Simulator):
    """Append-only records, e.g. support tickets or sent emails.

    Each call appends its arguments and returns ``respond(record_id, args)``.
    """

    def __init__(
        self,
        name: str,
        *,
        tools: Iterable[str],
        id_prefix: str = "SIM-",
        respond: Callable[[str, Mapping[str, Any]], Any] | None = None,
    ) -> None:
        self.name = name
        self.tools = frozenset(tools)
        self.id_prefix = id_prefix
        self.respond = respond or (lambda record_id, _args: {"id": record_id})
        self.records: list[dict[str, Any]] = []

    def handle(self, tool: str, args: Mapping[str, Any]) -> Any:
        record_id = f"{self.id_prefix}{len(self.records) + 1}"
        self.records.append({"id": record_id, "tool": tool, "args": copy.deepcopy(dict(args))})
        return self.respond(record_id, args)

    def snapshot(self) -> Any:
        return copy.deepcopy(self.records)
