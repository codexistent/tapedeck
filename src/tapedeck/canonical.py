"""Canonical JSON: the one place where "are these two values the same?" is decided.

Every hash, tape comparison, and argument match goes through ``canonical_json``.
If this function changed its output for an existing value, every committed tape
would silently stop matching, so its rules are deliberately small and fixed:

* object keys are sorted, separators are compact, non-ASCII is kept as UTF-8;
* a float with an integral value is written as an integer (``59.0`` -> ``59``),
  so the same amount produced by different code paths hashes the same;
* other floats use Python's shortest round-trip repr; NaN and infinity are rejected;
* tuples are treated as lists.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from typing import Any


def normalize(value: Any) -> Any:
    """Return a JSON-compatible copy of ``value`` with canonical number forms."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("NaN and infinity cannot be canonicalized")
        if value.is_integer() and abs(value) < 2**53:
            return int(value)
        return value
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"object keys must be strings, got {type(key).__name__}")
            out[key] = normalize(item)
        return out
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    raise TypeError(f"{type(value).__name__} is not JSON-serializable")


def canonical_json(value: Any) -> str:
    """Serialize ``value`` to its canonical JSON string."""
    return json.dumps(normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(value: Any) -> str:
    """SHA-256 hex digest of the canonical JSON of ``value``."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonicalize_args(
    args: Mapping[str, Any],
    *,
    ignore: Iterable[str] = (),
    casefold: Iterable[str] = (),
) -> str:
    """Canonical string for a tool call's arguments under a matcher config.

    ``ignore`` lists argument names dropped before comparison (request ids,
    timestamps). ``casefold`` lists string arguments compared case-insensitively
    with surrounding whitespace removed.
    """
    ignored = set(ignore)
    folded = set(casefold)
    kept: dict[str, Any] = {}
    for key, item in args.items():
        if key in ignored:
            continue
        if key in folded and isinstance(item, str):
            item = " ".join(item.split()).casefold()
        kept[key] = item
    return canonical_json(kept)
