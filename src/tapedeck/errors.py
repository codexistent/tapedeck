"""Exceptions Tapedeck raises. Messages are written to be fixable from the text alone."""

from __future__ import annotations


class TapedeckError(Exception):
    """Base class for Tapedeck errors."""


class TapeMiss(TapedeckError):
    """A replayed agent made a call the tape cannot answer."""


class ExternalToolBlocked(TapedeckError):
    """An ``external`` tool (email, payment, ...) would have run for real outside recording."""


class ToolError(TapedeckError):
    """A tool failed. In replay this re-raises the error recorded on the tape."""


class BudgetExceeded(TapedeckError):
    """A suite's estimated cost passed its budget."""


class NoActiveSession(TapedeckError):
    """``tapedeck.chat`` or a ``@tapedeck.tool`` was used outside record() or replay()."""
