"""Explaining a regression: where did the candidate's behavior change?

Each run is reduced to its signature, the sequence of tool names it called.
Across N runs per side we take the most common signature (the side's
behavior "mode"), align the baseline mode with the candidate mode using
Needleman-Wunsch, and describe the first difference in one sentence.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

Op = Literal["same", "sub", "del", "ins"]
Signature = tuple[str, ...]


@dataclass(frozen=True)
class Step:
    op: Op
    base: str | None
    cand: str | None


def align(base: Sequence[str], cand: Sequence[str]) -> list[Step]:
    """Global alignment, cost 0 for a match and 1 for a substitution or gap.

    ``del`` means the baseline step is missing from the candidate; ``ins``
    means the candidate added a step. Ties prefer match/substitution, then
    deletion, so output is deterministic.
    """
    n, m = len(base), len(cand)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i
    for j in range(1, m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = cost[i - 1][j - 1] + (0 if base[i - 1] == cand[j - 1] else 1)
            cost[i][j] = min(diag, cost[i - 1][j] + 1, cost[i][j - 1] + 1)

    steps: list[Step] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            same = base[i - 1] == cand[j - 1]
            if cost[i][j] == cost[i - 1][j - 1] + (0 if same else 1):
                steps.append(Step("same" if same else "sub", base[i - 1], cand[j - 1]))
                i, j = i - 1, j - 1
                continue
        if i > 0 and cost[i][j] == cost[i - 1][j] + 1:
            steps.append(Step("del", base[i - 1], None))
            i -= 1
        else:
            steps.append(Step("ins", None, cand[j - 1]))
            j -= 1
    steps.reverse()
    return steps


def mode(signatures: Sequence[Signature]) -> Signature | None:
    """Most common signature; ties broken by first appearance."""
    if not signatures:
        return None
    counts = Counter(signatures)
    best = max(counts.values())
    return next(s for s in signatures if counts[s] == best)


def _first_difference(steps: list[Step]) -> tuple[int, Step] | None:
    for index, step in enumerate(steps):
        if step.op != "same":
            return index, step
    return None


def _share(
    baseline: Sequence[Signature],
    candidate: Sequence[Signature],
    shows_change: Callable[[Signature], bool],
) -> str:
    return (
        f"{sum(map(shows_change, candidate))}/{len(candidate)} candidate runs "
        f"(baseline: {sum(map(shows_change, baseline))}/{len(baseline)})"
    )


def explain(baseline: Sequence[Signature], candidate: Sequence[Signature]) -> str:
    """One sentence a human can act on, describing how behavior changed.

    The change is found by aligning the two sides' most common signatures; the
    counts then say how many runs on each side show that change (more or fewer
    calls to the tool involved than the baseline's usual behavior), so runs
    with small unrelated variations still count.
    """
    base_mode, cand_mode = mode(baseline), mode(candidate)
    if base_mode is None or cand_mode is None:
        return "Not enough runs to compare behavior."
    steps = align(base_mode, cand_mode)
    found = _first_difference(steps)
    if found is None:
        return (
            "The tool sequence is unchanged; the regression is in tool arguments or the "
            "reply. See the failing checks."
        )
    index, step = found
    if step.op == "del":
        assert step.base is not None
        tool, usual = step.base, base_mode.count(step.base)
        later = next((s.base for s in steps[index + 1 :] if s.base is not None), None)
        where = f"before {later}" if later else "at the end"
        share = _share(baseline, candidate, lambda s: s.count(tool) < usual)
        return f"Candidate skipped {tool} {where} in {share}."
    if step.op == "ins":
        assert step.cand is not None
        tool, usual = step.cand, base_mode.count(step.cand)
        earlier = next((s.cand for s in reversed(steps[:index]) if s.cand is not None), None)
        where = f"after {earlier}" if earlier else "first"
        share = _share(baseline, candidate, lambda s: s.count(tool) > usual)
        return f"Candidate added a call to {tool} {where} in {share}."
    assert step.cand is not None and step.base is not None
    new, usual = step.cand, base_mode.count(step.cand)
    share = _share(baseline, candidate, lambda s: s.count(new) > usual)
    return f"Candidate called {new} where baseline called {step.base} in {share}."


def first_divergence(base: Signature, cand: Signature) -> int | None:
    """Index in the alignment of the first differing step, or None if identical."""
    found = _first_difference(align(base, cand))
    return None if found is None else found[0]
