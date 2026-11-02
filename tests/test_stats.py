import math

import pytest

from tapedeck.stats import Counts, decide, false_alarm_rate, fisher_worse, holm, power, wilson


def test_wilson_known_values() -> None:
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4)
    assert hi == pytest.approx(0.7634, abs=1e-4)
    lo, hi = wilson(0, 5)
    assert lo == 0.0 and hi == pytest.approx(0.4345, abs=1e-4)
    lo, hi = wilson(5, 5)
    assert hi == 1.0 and lo == pytest.approx(0.5655, abs=1e-4)
    assert wilson(0, 0) == (0.0, 1.0)


def test_fisher_by_hand() -> None:
    # 5/5 -> 1/5: only one more-extreme-or-equal table, C(6,1)C(4,4)/C(10,5) = 6/252.
    assert fisher_worse(5, 5, 1, 5) == pytest.approx(6 / 252)
    # 10/10 -> 2/10: C(12,2)C(8,8)/C(20,10) = 66/184756.
    assert fisher_worse(10, 10, 2, 10) == pytest.approx(66 / math.comb(20, 10))
    # 10/10 -> 5/10: C(15,5)/C(20,10) = 3003/184756, about 0.0163.
    assert fisher_worse(10, 10, 5, 10) == pytest.approx(3003 / 184756)
    # No change, or an improvement, is never significant.
    assert fisher_worse(7, 10, 7, 10) > 0.5
    assert fisher_worse(3, 10, 9, 10) == pytest.approx(1.0, abs=1e-2)


def test_holm_hand_worked() -> None:
    # sorted 0.01, 0.02, 0.04 with m = 3 -> 0.03, 0.04, 0.04 (monotone)
    assert holm([0.04, 0.01, 0.02]) == pytest.approx([0.04, 0.03, 0.04])
    assert holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])
    assert holm([]) == []


def test_n5_with_eight_cases_only_catches_total_collapse() -> None:
    # Why the default is 10 runs: at N = 5 with 8 cases, only 5/5 -> 0/5 clears Holm's bar
    # (8 * 1/252 = 0.032); 5/5 -> 1/5 does not (8 * 6/252 = 0.19).
    base = {f"c{i}": Counts(5, 5) for i in range(8)}
    assert not decide(base, dict(base, c0=Counts(0, 5))).passed
    assert decide(base, dict(base, c0=Counts(1, 5))).passed


def test_decide_flags_big_real_drop_only() -> None:
    base = {f"c{i}": Counts(10, 10) for i in range(8)}
    big = dict(base, c3=Counts(2, 10))
    verdict = decide(base, big)
    assert [c.case for c in verdict.regressed] == ["c3"]
    medium = dict(base, c3=Counts(5, 10))
    assert decide(base, medium).passed  # p = 0.016 before correction: not enough


def test_min_effect_blocks_tiny_but_significant_drops() -> None:
    base = {"a": Counts(1000, 1000)}
    cand = {"a": Counts(950, 1000)}
    assert decide(base, cand, min_effect=0.2).passed
    assert not decide(base, cand, min_effect=0.05).passed


def test_false_alarm_rate_stays_under_alpha() -> None:
    rates = [0.95, 0.9, 0.8, 0.7, 0.95, 0.6, 0.85, 0.99]
    for n in (5, 10, 20):
        assert false_alarm_rate(rates, n, trials=2000, seed=1) <= 0.05


def test_power_grows_with_n() -> None:
    rates = [0.95] * 8
    low = power(rates, 0, 0.3, 5, trials=800, seed=2)
    mid = power(rates, 0, 0.3, 10, trials=800, seed=2)
    high = power(rates, 0, 0.3, 20, trials=800, seed=2)
    assert low < mid < high
    assert high > 0.9
