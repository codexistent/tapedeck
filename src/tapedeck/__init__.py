"""Tapedeck: regression tests for AI agents.

Record real agent runs as tapes, replay a changed agent live against the
recorded tool world, grade many runs with verifiers, and fail a pull request
only when a regression is statistically real.
"""

from .backends import Backend, OpenAIBackend, assistant_message, tool_message
from .errors import (
    BudgetExceeded,
    ExternalToolBlocked,
    NoActiveSession,
    TapedeckError,
    TapeMiss,
    ToolError,
)
from .matcher import Matcher, MatcherConfig, ToolMatchConfig
from .session import Session, chat, current_session, record, replay, tool
from .simulators import AppendLogSimulator, KeyValueSimulator, Simulator
from .tape import LLMResponse, Tape, ToolCallRequest, Usage
from .verify import CheckResult, Run, case, registry

__version__ = "0.2.0"

__all__ = [
    "AppendLogSimulator",
    "Backend",
    "BudgetExceeded",
    "CheckResult",
    "ExternalToolBlocked",
    "KeyValueSimulator",
    "LLMResponse",
    "Matcher",
    "MatcherConfig",
    "NoActiveSession",
    "OpenAIBackend",
    "Run",
    "Session",
    "Simulator",
    "Tape",
    "TapeMiss",
    "TapedeckError",
    "ToolCallRequest",
    "ToolError",
    "ToolMatchConfig",
    "Usage",
    "assistant_message",
    "case",
    "chat",
    "current_session",
    "record",
    "registry",
    "replay",
    "tool",
    "tool_message",
]
