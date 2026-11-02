"""Answering a replayed tool call from the tape.

The matcher decides whether a call made by the *changed* agent is "the same" as
one recorded on the tape. Matching is configured per tool:

``keyed`` (default)
    Any order. A call matches a recorded call with the same tool name and the
    same canonical arguments; repeated identical calls consume recorded results
    in order. Once exhausted, a ``read`` tool keeps returning its last result
    (reads are idempotent); other tools miss.
``positional``
    The Nth call to the tool gets the Nth recorded result, whatever its
    arguments. Right for pagination-style tools whose arguments are opaque.
"""

from __future__ import annotations

import difflib
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .canonical import canonicalize_args
from .tape import ToolCallEvent

Order = Literal["keyed", "positional"]
MissPolicy = Literal["fail", "live"]


class ToolMatchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ignore: list[str] = Field(default_factory=list)
    casefold: list[str] = Field(default_factory=list)
    order: Order = "keyed"
    on_miss: MissPolicy | None = None


class MatcherConfig(BaseModel):
    """Contents of the ``matchers`` section of tapedeck.yaml."""

    model_config = ConfigDict(extra="forbid")
    on_miss: MissPolicy = "fail"
    tools: dict[str, ToolMatchConfig] = Field(default_factory=dict)

    def for_tool(self, name: str) -> ToolMatchConfig:
        return self.tools.get(name, ToolMatchConfig())

    def miss_policy(self, name: str) -> MissPolicy:
        """``live`` lets a *read* tool with no outside dependency run for real on a miss."""
        return self.for_tool(name).on_miss or self.on_miss

    def canonical(self, name: str, args: Mapping[str, Any]) -> str:
        cfg = self.for_tool(name)
        return canonicalize_args(args, ignore=cfg.ignore, casefold=cfg.casefold)

    @classmethod
    def from_yaml(cls, path: str | Path) -> MatcherConfig:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.model_validate(data.get("matchers", data))


@dataclass
class MatchLogEntry:
    step: int
    tool: str
    args: str
    outcome: Literal["matched", "repeated", "simulated", "live", "miss"]
    detail: str = ""


@dataclass
class MatchResult:
    event: ToolCallEvent
    repeated: bool = False


@dataclass
class Matcher:
    """Serves recorded tool results for one replay."""

    config: MatcherConfig
    recorded: list[ToolCallEvent]
    log: list[MatchLogEntry] = field(default_factory=list)
    _keyed: dict[tuple[str, str], deque[ToolCallEvent]] = field(init=False)
    _last: dict[tuple[str, str], ToolCallEvent] = field(init=False)
    _positional: dict[str, list[ToolCallEvent]] = field(init=False)
    _cursor: dict[str, int] = field(init=False)

    def __post_init__(self) -> None:
        self._keyed = defaultdict(deque)
        self._last = {}
        self._positional = defaultdict(list)
        self._cursor = defaultdict(int)
        for event in self.recorded:
            if self.config.for_tool(event.name).order == "positional":
                self._positional[event.name].append(event)
            else:
                self._keyed[(event.name, self.config.canonical(event.name, event.args))].append(
                    event
                )

    @classmethod
    def from_events(cls, config: MatcherConfig, events: Iterable[ToolCallEvent]) -> Matcher:
        return cls(config=config, recorded=list(events))

    def match(self, name: str, args: Mapping[str, Any]) -> MatchResult | None:
        """Return the recorded call answering ``name(args)``, or None on a miss."""
        if self.config.for_tool(name).order == "positional":
            queue = self._positional.get(name, [])
            index = self._cursor[name]
            if index < len(queue):
                self._cursor[name] += 1
                return MatchResult(queue[index])
            return None

        key = (name, self.config.canonical(name, args))
        pending = self._keyed.get(key)
        if pending:
            event = pending.popleft()
            self._last[key] = event
            return MatchResult(event)
        last = self._last.get(key)
        if last is not None and last.effect == "read":
            return MatchResult(last, repeated=True)
        return None

    def nearest(self, name: str, args: Mapping[str, Any]) -> str | None:
        """The recorded call to ``name`` whose canonical arguments look most like ``args``."""
        target = self.config.canonical(name, args)
        candidates = sorted(
            {self.config.canonical(e.name, e.args) for e in self.recorded if e.name == name}
        )
        if not candidates:
            return None
        best = max(candidates, key=lambda c: difflib.SequenceMatcher(None, target, c).ratio())
        return f"{name}({best})"

    def miss_message(self, step: int, name: str, args: Mapping[str, Any]) -> str:
        canon = self.config.canonical(name, args)
        lines = [f"step {step}: no recorded result for {name}({canon})"]
        near = self.nearest(name, args)
        if near is None:
            lines.append(f"  the tape never calls {name!r}")
        else:
            lines.append(f"  nearest recorded call: {near}")
        lines.append(
            "  fix: re-record this case; add argument names to "
            f"matchers.tools.{name}.ignore or .casefold in tapedeck.yaml; set "
            f"matchers.tools.{name}.on_miss: live if it is a pure read; "
            "or give the tool a simulator"
        )
        return "\n".join(lines)
