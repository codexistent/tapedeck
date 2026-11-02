"""Record and replay sessions: the context every ``chat`` call and ``@tool`` call runs in.

Three modes:

``record``
    Live model, real tools. Every event is written to a tape as it happens.
``playback``
    Model responses *and* tool results come from the tape; nothing touches the
    network. Tests the harness (parsing, routing, error handling), not the model.
``counterfactual``
    The model is live (new prompt or model); tools are answered by simulators
    and the matcher from the tape. Tests whether a change altered behavior.

In every mode the session also builds the run's own trajectory, which is what
verifiers grade.
"""

from __future__ import annotations

import contextvars
import copy
import functools
import inspect
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Literal, ParamSpec, TypeVar, overload

from .backends import Backend
from .canonical import canonical_json, sha256
from .errors import ExternalToolBlocked, NoActiveSession, TapeMiss, ToolError
from .matcher import Matcher, MatcherConfig, MatchLogEntry
from .simulators import Simulator
from .tape import (
    Effect,
    Event,
    InputEvent,
    LLMCallEvent,
    LLMResponse,
    MetaEvent,
    OutputEvent,
    Tape,
    ToolCallEvent,
    Usage,
    dump_event,
)

Mode = Literal["record", "playback", "counterfactual"]

_active: contextvars.ContextVar[Session | None] = contextvars.ContextVar(
    "tapedeck_session", default=None
)


def current_session() -> Session:
    session = _active.get()
    if session is None:
        raise NoActiveSession(
            "tapedeck.chat() needs an active session: wrap the run in "
            "tapedeck.record(...) or tapedeck.replay(...)"
        )
    return session


@dataclass
class Session:
    mode: Mode
    meta: MetaEvent
    backend: Backend | None = None
    source: Tape | None = None
    matcher: Matcher | None = None
    simulators: Sequence[Simulator] = ()
    writer: IO[str] | None = None
    events: list[Event] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    _step: int = 0
    _tool_ids: int = 0
    _llm_index: dict[str, deque[LLMCallEvent]] = field(default_factory=dict)
    _tool_cursor: int = 0
    _owners: dict[str, Simulator] = field(default_factory=dict)
    _playback_log: list[MatchLogEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.writer is not None:
            self._write(self.meta)
        if self.source is not None and self.mode == "playback":
            index: dict[str, deque[LLMCallEvent]] = defaultdict(deque)
            for call in self.source.llm_calls():
                index[call.request_sha].append(call)
            self._llm_index = dict(index)
        for sim in self.simulators:
            for tool_name in sim.tools:
                if tool_name in self._owners:
                    raise ValueError(f"tool {tool_name!r} is owned by two simulators")
                self._owners[tool_name] = sim

    # -- bookkeeping -------------------------------------------------------

    def _write(self, event: MetaEvent | Event) -> None:
        assert self.writer is not None
        self.writer.write(dump_event(event) + "\n")
        self.writer.flush()

    def _emit(self, event: Event) -> None:
        self.events.append(event)
        if self.writer is not None:
            self._write(event)

    def _next_step(self) -> int:
        self._step += 1
        return self._step

    @property
    def match_log(self) -> list[MatchLogEntry]:
        return self.matcher.log if self.matcher is not None else self._playback_log

    @property
    def state(self) -> dict[str, Any]:
        """Final simulator state, keyed by simulator name."""
        return {sim.name: sim.snapshot() for sim in self.simulators}

    def trajectory(self) -> Tape:
        return Tape(meta=self.meta, events=list(self.events))

    # -- events the harness emits -----------------------------------------

    def input(self, content: str, context: dict[str, Any] | None = None) -> None:
        self._emit(InputEvent(step=0, content=content, context=dict(context or {})))

    def output(self, content: str) -> None:
        self._emit(OutputEvent(step=self._next_step(), content=content))

    # -- the model ---------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **params: Any,
    ) -> LLMResponse:
        step = self._next_step()
        model = self.meta.model
        request = {"model": model, "messages": messages, "tools": tools or [], "params": params}
        request_sha = sha256(request)

        if self.mode == "playback":
            pending = self._llm_index.get(request_sha)
            if not pending:
                last = messages[-1] if messages else {}
                preview = canonical_json(last.get("content") or last)[:80]
                raise TapeMiss(
                    f"step {step}: model request not on the tape (sha {request_sha[:12]}); "
                    f"last message: {preview}\n"
                    "  the harness built a different request than when recording. "
                    "Playback needs identical prompts, tools and parameters; use "
                    "counterfactual mode to test a changed agent."
                )
            recorded = pending.popleft()
            response = recorded.response.model_copy(deep=True)
            latency = recorded.latency_ms
        else:
            if self.backend is None:
                raise RuntimeError(f"{self.mode} mode needs a backend")
            started = time.perf_counter()
            response = self.backend.complete(request)
            latency = int((time.perf_counter() - started) * 1000)

        self.usage.input_tokens += response.usage.input_tokens
        self.usage.output_tokens += response.usage.output_tokens
        self._emit(
            LLMCallEvent(step=step, request_sha=request_sha, response=response, latency_ms=latency)
        )
        return response

    # -- tools -------------------------------------------------------------

    def call_tool(
        self, name: str, effect: Effect, fn: Callable[..., Any], args: dict[str, Any]
    ) -> Any:
        step = self._next_step()
        self._tool_ids += 1
        call_id = f"t{self._tool_ids}"

        def emit(result: Any = None, error: str | None = None) -> None:
            self._emit(
                ToolCallEvent(
                    step=step,
                    id=call_id,
                    name=name,
                    args=copy.deepcopy(args),
                    result=copy.deepcopy(result),
                    error=error,
                    effect=effect,
                )
            )

        if self.mode == "record":
            try:
                result = fn(**args)
            except Exception as exc:
                emit(error=f"{type(exc).__name__}: {exc}")
                raise
            emit(result)
            return result

        if self.mode == "playback":
            return self._playback_tool(step, name, args, emit)

        return self._counterfactual_tool(step, name, effect, fn, args, emit)

    def _playback_tool(
        self, step: int, name: str, args: dict[str, Any], emit: Callable[..., None]
    ) -> Any:
        assert self.source is not None
        recorded = list(self.source.tool_calls())
        if self._tool_cursor >= len(recorded):
            raise TapeMiss(f"step {step}: {name} called, but the tape has no more tool calls")
        expected = recorded[self._tool_cursor]
        self._tool_cursor += 1
        if expected.name != name or canonical_json(expected.args) != canonical_json(args):
            raise TapeMiss(
                f"step {step}: expected {expected.name}({canonical_json(expected.args)}), "
                f"got {name}({canonical_json(args)})"
            )
        self._playback_log.append(MatchLogEntry(step, name, canonical_json(args), "matched"))
        if expected.error is not None:
            emit(error=expected.error)
            raise ToolError(expected.error)
        emit(expected.result)
        return copy.deepcopy(expected.result)

    def _counterfactual_tool(
        self,
        step: int,
        name: str,
        effect: Effect,
        fn: Callable[..., Any],
        args: dict[str, Any],
        emit: Callable[..., None],
    ) -> Any:
        assert self.matcher is not None
        log = self.matcher.log
        canon = self.matcher.config.canonical(name, args)

        owner = self._owners.get(name)
        if owner is not None:
            result = owner.handle(name, args)
            log.append(MatchLogEntry(step, name, canon, "simulated", owner.name))
            emit(result)
            return copy.deepcopy(result)

        found = self.matcher.match(name, args)
        if found is not None:
            log.append(
                MatchLogEntry(step, name, canon, "repeated" if found.repeated else "matched")
            )
            if found.event.error is not None:
                emit(error=found.event.error)
                raise ToolError(found.event.error)
            emit(found.event.result)
            return copy.deepcopy(found.event.result)

        message = self.matcher.miss_message(step, name, args)
        if effect == "external":
            log.append(MatchLogEntry(step, name, canon, "miss", "external"))
            raise ExternalToolBlocked(
                message + "\n  (external tools are never really called outside recording)"
            )
        if self.matcher.config.miss_policy(name) == "live" and effect == "read":
            result = fn(**args)
            log.append(MatchLogEntry(step, name, canon, "live"))
            emit(result)
            return result
        log.append(MatchLogEntry(step, name, canon, "miss"))
        raise TapeMiss(message)


# -- public context managers ------------------------------------------------


def _meta(case: str, model: str, prompt: str, extra: dict[str, Any] | None) -> MetaEvent:
    return MetaEvent(
        case=case,
        model=model,
        prompt_sha=sha256(prompt)[:16],
        created_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
        extra=dict(extra or {}),
    )


@contextmanager
def _activate(session: Session) -> Iterator[Session]:
    token = _active.set(session)
    try:
        yield session
    finally:
        _active.reset(token)


@contextmanager
def record(
    path: str | Path,
    *,
    case: str,
    backend: Backend,
    prompt: str = "",
    extra: dict[str, Any] | None = None,
) -> Iterator[Session]:
    """Record a live run to ``path``. Events are flushed as they happen."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as writer:
        session = Session(
            mode="record",
            meta=_meta(case, backend.model, prompt, extra),
            backend=backend,
            writer=writer,
        )
        with _activate(session):
            yield session


@contextmanager
def replay(
    tape: Tape | str | Path,
    *,
    mode: Literal["playback", "counterfactual"] = "playback",
    backend: Backend | None = None,
    simulators: Sequence[Simulator] = (),
    matchers: MatcherConfig | None = None,
    prompt: str = "",
) -> Iterator[Session]:
    """Replay a tape. Simulators must be fresh instances; they are seeded here."""
    source = tape if isinstance(tape, Tape) else Tape.load(tape)
    if mode == "counterfactual":
        if backend is None:
            raise ValueError("counterfactual replay needs a backend (the live model)")
        for sim in simulators:
            sim.seed(source)
        model = backend.model
        matcher: Matcher | None = Matcher.from_events(
            matchers or MatcherConfig(), source.tool_calls()
        )
    else:
        model = source.meta.model
        matcher = None
    session = Session(
        mode=mode,
        meta=_meta(source.meta.case, model, prompt, {"replayed_from": source.meta.prompt_sha}),
        backend=backend,
        source=source,
        matcher=matcher,
        simulators=simulators if mode == "counterfactual" else (),
    )
    with _activate(session):
        yield session


# -- what agents import -------------------------------------------------------


def chat(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, **params: Any
) -> LLMResponse:
    """Call the model through the active session."""
    return current_session().chat(messages, tools, **params)


P = ParamSpec("P")
R = TypeVar("R")


@overload
def tool(fn: Callable[P, R], /) -> Callable[P, R]: ...
@overload
def tool(
    *, effect: Effect = "write", name: str | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def tool(
    fn: Callable[P, R] | None = None,
    /,
    *,
    effect: Effect = "write",
    name: str | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Mark a function as an agent tool.

    The default effect is ``write``: a tool is assumed to have side effects
    unless declared ``read``. ``external`` tools (email, payments) are never
    really called outside recording. Outside any session the function runs
    normally, so instrumented agents still work in production.
    """

    def wrap(func: Callable[P, R]) -> Callable[P, R]:
        tool_name = name or func.__name__
        signature = inspect.signature(func)

        @functools.wraps(func)
        def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            session = _active.get()
            if session is None:
                return func(*args, **kwargs)
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            result: R = session.call_tool(tool_name, effect, func, dict(bound.arguments))
            return result

        inner.__tapedeck_tool__ = (tool_name, effect)  # type: ignore[attr-defined]
        return inner

    return wrap(fn) if fn is not None else wrap
