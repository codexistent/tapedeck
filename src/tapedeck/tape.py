"""The tape: an append-only JSONL log of one agent run.

Line one is a ``meta`` event; every later line is one event in the order it
happened. Tapes are immutable once written: any change produces a new tape.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .canonical import canonical_json

TAPE_VERSION = 1

Effect = Literal["read", "write", "external"]


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_tokens: int = 0
    output_tokens: int = 0


class ToolCallRequest(BaseModel):
    """A tool call the model asked for."""

    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    """A provider-neutral model response. Agents read this, never raw SDK objects."""

    model_config = ConfigDict(extra="forbid")
    content: str | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    finish_reason: str | None = None


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MetaEvent(_Event):
    type: Literal["meta"] = "meta"
    tape_version: int = TAPE_VERSION
    case: str
    model: str
    prompt_sha: str
    created_at: str
    extra: dict[str, Any] = Field(default_factory=dict)


class InputEvent(_Event):
    type: Literal["input"] = "input"
    step: int
    content: str
    context: dict[str, Any] = Field(default_factory=dict)


class LLMCallEvent(_Event):
    type: Literal["llm_call"] = "llm_call"
    step: int
    request_sha: str
    response: LLMResponse
    latency_ms: int = 0


class ToolCallEvent(_Event):
    type: Literal["tool_call"] = "tool_call"
    step: int
    id: str
    name: str
    args: dict[str, Any]
    result: Any = None
    error: str | None = None
    effect: Effect = "write"


class OutputEvent(_Event):
    type: Literal["output"] = "output"
    step: int
    content: str


Event = Annotated[
    MetaEvent | InputEvent | LLMCallEvent | ToolCallEvent | OutputEvent,
    Field(discriminator="type"),
]
_event_adapter: TypeAdapter[Event] = TypeAdapter(Event)


def parse_event(line: str) -> Event:
    return _event_adapter.validate_json(line)


def dump_event(event: _Event) -> str:
    return canonical_json(event.model_dump(mode="json"))


class Tape(BaseModel):
    """A fully loaded tape."""

    meta: MetaEvent
    events: list[Event]

    @classmethod
    def load(cls, path: str | Path) -> Tape:
        lines = [ln for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            raise ValueError(f"{path}: empty tape")
        parsed = [parse_event(ln) for ln in lines]
        meta, rest = parsed[0], parsed[1:]
        if not isinstance(meta, MetaEvent):
            raise ValueError(f"{path}: first line must be a meta event")
        if meta.tape_version > TAPE_VERSION:
            raise ValueError(
                f"{path}: tape_version {meta.tape_version} is newer than this Tapedeck "
                f"supports ({TAPE_VERSION}); upgrade tapedeck"
            )
        return cls(meta=meta, events=rest)

    def dumps(self) -> str:
        return "".join(dump_event(e) + "\n" for e in [self.meta, *self.events])

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.dumps(), encoding="utf-8")

    def tool_calls(self) -> Iterator[ToolCallEvent]:
        for event in self.events:
            if isinstance(event, ToolCallEvent):
                yield event

    def llm_calls(self) -> Iterator[LLMCallEvent]:
        for event in self.events:
            if isinstance(event, LLMCallEvent):
                yield event

    @property
    def input(self) -> InputEvent:
        for event in self.events:
            if isinstance(event, InputEvent):
                return event
        raise ValueError(f"tape for case {self.meta.case!r} has no input event")
