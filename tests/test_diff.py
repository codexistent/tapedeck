from tapedeck.diff import align, explain, first_divergence, mode


def ops(base: list[str], cand: list[str]) -> list[str]:
    return [s.op for s in align(base, cand)]


def test_align_edge_cases() -> None:
    assert align([], []) == []
    assert ops(["a"], []) == ["del"]
    assert ops([], ["a"]) == ["ins"]
    assert ops(["a", "b"], ["a", "b"]) == ["same", "same"]


def test_align_finds_skip_and_insert() -> None:
    assert ops(["get", "check", "refund"], ["get", "refund"]) == ["same", "del", "same"]
    assert ops(["get", "reply"], ["get", "refund", "reply"]) == ["same", "ins", "same"]
    assert ops(["a", "b"], ["a", "c"]) == ["same", "sub"]


def test_mode_ties_go_to_first_seen() -> None:
    assert mode([("a",), ("b",), ("b",), ("a",)]) == ("a",)
    assert mode([]) is None


def test_explain_skipped_step() -> None:
    base = [("get_order", "verify", "issue_refund")] * 5
    cand = [("get_order", "issue_refund")] * 4 + [("get_order", "verify", "issue_refund")]
    text = explain(base, cand)
    assert (
        text
        == "Candidate skipped verify before issue_refund in 4/5 candidate runs (baseline: 0/5)."
    )


def test_explain_added_step_counts_variants() -> None:
    base = [("get_order",)] * 10
    cand = (
        [("get_order", "issue_refund")] * 6
        + [("get_order", "search", "issue_refund")] * 3
        + [("get_order",)]
    )
    text = explain(base, cand)
    assert "added a call to issue_refund after get_order" in text
    assert "9/10 candidate runs (baseline: 0/10)" in text


def test_explain_unchanged_sequence() -> None:
    assert "unchanged" in explain([("a",)] * 3, [("a",)] * 3)


def test_first_divergence() -> None:
    assert first_divergence(("a", "b", "c"), ("a", "x", "c")) == 1
    assert first_divergence(("a",), ("a",)) is None
