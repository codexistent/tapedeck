"""Deciding whether a change really made the agent worse.

Agents are nondeterministic, so each case is run N times and scored as a pass
rate. For each case we test "the candidate passes less often than the
baseline" with a one-sided Fisher exact test, then correct for testing many
cases at once with Holm-Bonferroni. Without that correction, 50 cases at
alpha = 0.05 would flag about 2.5 false regressions on every PR.

A case regresses only when its adjusted p-value is below alpha *and* its pass
rate dropped by at least ``min_effect``: statistically real and big enough to care.

Everything here is pure functions with no I/O, implemented from first
principles (``math.comb``), so each formula can be checked by hand.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def wilson(passes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for a pass rate. Behaves well at small n and near 0 or 1."""
    if n == 0:
        return (0.0, 1.0)
    if not 0 <= passes <= n:
        raise ValueError(f"passes must be in [0, {n}], got {passes}")
    p = passes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def fisher_worse(base_pass: int, base_n: int, cand_pass: int, cand_n: int) -> float:
    """One-sided Fisher exact p-value that the candidate's pass rate is lower.

    With the table's margins fixed, the candidate's pass count follows a
    hypergeometric distribution. The p-value is the probability of seeing the
    observed count or fewer.
    """
    total = base_n + cand_n
    successes = base_pass + cand_pass
    failures = total - successes
    lowest = max(0, cand_n - failures)
    denom = math.comb(total, cand_n)
    tail = sum(
        math.comb(successes, x) * math.comb(failures, cand_n - x)
        for x in range(lowest, cand_pass + 1)
    )
    return min(1.0, tail / denom)


def holm(pvalues: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, returned in the input order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[index]))
        adjusted[index] = running
    return adjusted


@dataclass(frozen=True)
class Counts:
    passes: int
    n: int

    @property
    def rate(self) -> float:
        return self.passes / self.n if self.n else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson(self.passes, self.n)


@dataclass(frozen=True)
class CaseVerdict:
    case: str
    baseline: Counts
    candidate: Counts
    p: float
    p_adjusted: float
    regressed: bool

    @property
    def drop(self) -> float:
        return self.baseline.rate - self.candidate.rate


@dataclass(frozen=True)
class SuiteVerdict:
    cases: list[CaseVerdict]
    alpha: float
    min_effect: float

    @property
    def regressed(self) -> list[CaseVerdict]:
        return [c for c in self.cases if c.regressed]

    @property
    def passed(self) -> bool:
        return not self.regressed


def decide(
    baseline: Mapping[str, Counts],
    candidate: Mapping[str, Counts],
    *,
    alpha: float = 0.05,
    min_effect: float = 0.2,
) -> SuiteVerdict:
    """Compare per-case pass counts. Only cases present on both sides are compared."""
    names = sorted(set(baseline) & set(candidate))
    raw = [
        fisher_worse(baseline[c].passes, baseline[c].n, candidate[c].passes, candidate[c].n)
        for c in names
    ]
    adjusted = holm(raw)
    verdicts = []
    for name, p, p_adj in zip(names, raw, adjusted, strict=True):
        base, cand = baseline[name], candidate[name]
        drop = base.rate - cand.rate
        verdicts.append(
            CaseVerdict(
                case=name,
                baseline=base,
                candidate=cand,
                p=p,
                p_adjusted=p_adj,
                regressed=p_adj < alpha and drop >= min_effect - 1e-12,
            )
        )
    return SuiteVerdict(cases=verdicts, alpha=alpha, min_effect=min_effect)


def _binomial(rng: random.Random, n: int, p: float) -> int:
    return sum(rng.random() < p for _ in range(n))


def false_alarm_rate(
    true_rates: Sequence[float],
    n: int,
    *,
    trials: int = 2000,
    alpha: float = 0.05,
    min_effect: float = 0.2,
    seed: int = 0,
) -> float:
    """Fraction of simulated suites flagged as regressed when nothing changed."""
    rng = random.Random(seed)
    flagged = 0
    for _ in range(trials):
        base = {f"c{i}": Counts(_binomial(rng, n, r), n) for i, r in enumerate(true_rates)}
        cand = {f"c{i}": Counts(_binomial(rng, n, r), n) for i, r in enumerate(true_rates)}
        if not decide(base, cand, alpha=alpha, min_effect=min_effect).passed:
            flagged += 1
    return flagged / trials


def power(
    true_rates: Sequence[float],
    drop_case: int,
    drop_to: float,
    n: int,
    *,
    trials: int = 2000,
    alpha: float = 0.05,
    min_effect: float = 0.2,
    seed: int = 0,
) -> float:
    """Probability of flagging case ``drop_case`` when its true rate falls to ``drop_to``."""
    rng = random.Random(seed)
    caught = 0
    target = f"c{drop_case}"
    for _ in range(trials):
        base = {f"c{i}": Counts(_binomial(rng, n, r), n) for i, r in enumerate(true_rates)}
        cand = {
            f"c{i}": Counts(_binomial(rng, n, drop_to if i == drop_case else r), n)
            for i, r in enumerate(true_rates)
        }
        verdict = decide(base, cand, alpha=alpha, min_effect=min_effect)
        if any(c.case == target for c in verdict.regressed):
            caught += 1
    return caught / trials
