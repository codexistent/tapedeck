"""Verifiers: turning a finished run into pass/fail with reasons.

A case's checks are a plain function registered with ``@tapedeck.case``. It
receives the :class:`Run` and states expectations through ``run.expect``.
Checks grade what the agent *did* (its trajectory) and what the world looks
like afterwards (simulator state), never the agent's own account of itself.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .matcher import MatchLogEntry
from .tape import LLMCallEvent, OutputEvent, Tape, ToolCallEvent, Usage

ArgPredicate = Callable[[dict[str, Any]], bool]


@dataclass
class CheckResult:
    name: str
    passed: bool
    reason: str


@dataclass
class Run:
    """One execution of one case."""

    case: str
    index: int
    trajectory: Tape
    state: dict[str, Any]
    usage: Usage
    cost_usd: float
    wall_ms: int
    match_log: list[MatchLogEntry] = field(default_factory=list)
    error: str | None = None
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def expect(self) -> Expect:
        return Expect(self)

    @property
    def passed(self) -> bool:
        return self.error is None and all(c.passed for c in self.checks)

    def tool_calls(self, name: str | None = None) -> list[ToolCallEvent]:
        return [
            e
            for e in self.trajectory.events
            if isinstance(e, ToolCallEvent) and (name is None or e.name == name)
        ]

    @property
    def llm_calls(self) -> list[LLMCallEvent]:
        return [e for e in self.trajectory.events if isinstance(e, LLMCallEvent)]

    @property
    def output(self) -> str | None:
        for event in reversed(self.trajectory.events):
            if isinstance(event, OutputEvent):
                return event.content
        return None

    @property
    def signature(self) -> tuple[str, ...]:
        """The sequence of tool names called: this run's behavior in one tuple."""
        return tuple(e.name for e in self.tool_calls())


def _describe(where: ArgPredicate | None) -> str:
    return "" if where is None else " matching the condition"


class Expect:
    """Assertions over a run. Each call appends one CheckResult to ``run.checks``."""

    def __init__(self, run: Run) -> None:
        self._run = run

    def _add(self, name: str, passed: bool, reason: str) -> bool:
        self._run.checks.append(CheckResult(name, passed, reason))
        return passed

    def _matching(self, tool: str, where: ArgPredicate | None) -> list[ToolCallEvent]:
        calls = self._run.tool_calls(tool)
        if where is None:
            return calls
        matched = []
        for call in calls:
            try:
                if where(call.args):
                    matched.append(call)
            except (KeyError, TypeError, ValueError):
                continue
        return matched

    def called(
        self, tool: str, *, where: ArgPredicate | None = None, times: int | None = None
    ) -> bool:
        count = len(self._matching(tool, where))
        name = f"called({tool})"
        if times is None:
            ok = count > 0
            reason = f"{tool} called {count} time(s){_describe(where)}"
        else:
            ok = count == times
            reason = f"{tool} called {count} time(s){_describe(where)}, expected {times}"
        return self._add(name, ok, reason)

    def never_called(self, tool: str, *, where: ArgPredicate | None = None) -> bool:
        hits = self._matching(tool, where)
        if hits:
            first = hits[0]
            reason = f"{tool} was called at step {first.step} with {first.args}"
        else:
            reason = f"{tool} never called{_describe(where)}"
        return self._add(f"never_called({tool})", not hits, reason)

    def called_before(self, first: str, then: str) -> bool:
        name = f"called_before({first}, {then})"
        later = self._run.tool_calls(then)
        if not later:
            return self._add(name, True, f"{then} never called, so nothing to order")
        earlier = [c for c in self._run.tool_calls(first) if c.step < later[0].step]
        if earlier:
            return self._add(name, True, f"{first} at step {earlier[0].step} preceded {then}")
        return self._add(name, False, f"{then} at step {later[0].step} without {first} before it")

    def max_steps(self, limit: int) -> bool:
        steps = len(self._run.llm_calls)
        return self._add(f"max_steps({limit})", steps <= limit, f"{steps} model calls")

    def cost_under(self, usd: float) -> bool:
        cost = self._run.cost_usd
        return self._add(f"cost_under({usd})", cost < usd, f"cost ${cost:.4f}")

    def state(self, predicate: Callable[[dict[str, Any]], bool], label: str = "state") -> bool:
        try:
            ok = bool(predicate(self._run.state))
            reason = "holds" if ok else "does not hold"
        except Exception as exc:  # a predicate that crashes is a failed check, not a crash
            ok, reason = False, f"raised {type(exc).__name__}: {exc}"
        return self._add(label, ok, f"{label} {reason}")

    def output_contains(self, text: str) -> bool:
        output = self._run.output or ""
        ok = text.casefold() in output.casefold()
        return self._add(f"output_contains({text!r})", ok, "found" if ok else "not in reply")


CheckFn = Callable[[Run], None]


class CaseRegistry:
    def __init__(self) -> None:
        self.checks: dict[str, CheckFn] = {}

    def case(self, case_id: str) -> Callable[[CheckFn], CheckFn]:
        def register(fn: CheckFn) -> CheckFn:
            if case_id in self.checks:
                raise ValueError(f"checks for case {case_id!r} registered twice")
            self.checks[case_id] = fn
            return fn

        return register

    def grade(self, run: Run) -> Run:
        fn = self.checks.get(run.case)
        if fn is None:
            raise KeyError(f"no @tapedeck.case({run.case!r}) checks registered")
        if run.error is None:
            fn(run)
        return run


registry = CaseRegistry()
case = registry.case
