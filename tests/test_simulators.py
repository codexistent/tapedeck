"""Property tests: simulator state never contradicts itself."""

from __future__ import annotations

from typing import Any

from hypothesis import given
from hypothesis import strategies as st
from support_agent.sims import make
from support_agent.store import ORDERS

from tapedeck import KeyValueSimulator, Matcher, MatcherConfig, Tape, ToolMatchConfig
from tapedeck.simulators import derive_state
from tapedeck.tape import MetaEvent, ToolCallEvent


def seeded_orders() -> KeyValueSimulator:
    sim = make()[0]
    assert isinstance(sim, KeyValueSimulator)
    for order in ORDERS:
        sim.state[order["order_id"]] = dict(order)
    return sim


ids = st.sampled_from([o["order_id"] for o in ORDERS] + ["9999"])
actions = st.lists(
    st.one_of(
        st.tuples(st.just("get_order"), ids, st.just(0.0)),
        st.tuples(st.just("issue_refund"), ids, st.floats(-10, 200, allow_nan=False)),
    ),
    max_size=30,
)


@given(actions)
def test_refunds_never_exceed_total_and_reads_reflect_writes(steps: list[Any]) -> None:
    sim = seeded_orders()
    expected = {o["order_id"]: 0.0 + o["refunded_amount"] for o in ORDERS}
    for tool, oid, amount in steps:
        if tool == "issue_refund":
            result = sim.handle("issue_refund", {"order_id": oid, "amount": amount})
            if result.get("ok"):
                expected[oid] = result["refunded_amount"]
        else:
            result = sim.handle("get_order", {"order_id": oid})
            if oid in expected:
                assert result["refunded_amount"] == expected[oid]
            else:
                assert "error" in result
    for oid, order in sim.snapshot().items():
        assert order["refunded_amount"] <= order["total"] + 1e-9
        assert order["refunded_amount"] == expected[oid]


def _tape(*calls: ToolCallEvent) -> Tape:
    meta = MetaEvent(case="x", model="m", prompt_sha="p", created_at="t")
    return Tape(meta=meta, events=list(calls))


def test_derive_state_replays_successful_writes_only() -> None:
    order = dict(ORDERS[0])
    tape = _tape(
        ToolCallEvent(
            step=1,
            id="t1",
            name="get_order",
            args={"order_id": "4417"},
            result=order,
            effect="read",
        ),
        ToolCallEvent(
            step=2,
            id="t2",
            name="issue_refund",
            args={"order_id": "4417", "amount": 20, "reason": "r"},
            result={"ok": True},
        ),
        ToolCallEvent(
            step=3,
            id="t3",
            name="issue_refund",
            args={"order_id": "4417", "amount": 5, "reason": "r"},
            error="Boom",
        ),
        ToolCallEvent(
            step=4,
            id="t4",
            name="create_ticket",
            args={"subject": "s", "body": "b"},
            result={"ticket_id": "T-1"},
        ),
    )
    state = derive_state(make(), tape)
    assert state["orders"]["4417"]["refunded_amount"] == 20
    assert len(state["tickets"]) == 1


def test_positional_matching_ignores_arguments() -> None:
    tape = _tape(
        ToolCallEvent(
            step=1, id="a", name="page", args={"cursor": "x1"}, result=[1], effect="read"
        ),
        ToolCallEvent(
            step=2, id="b", name="page", args={"cursor": "x2"}, result=[2], effect="read"
        ),
    )
    matcher = Matcher.from_events(
        MatcherConfig(tools={"page": ToolMatchConfig(order="positional")}), tape.tool_calls()
    )
    first, second = matcher.match("page", {"cursor": "zz"}), matcher.match("page", {"cursor": "?"})
    assert first is not None and second is not None
    assert (first.event.result, second.event.result) == ([1], [2])
    assert matcher.match("page", {}) is None


def test_keyed_reads_repeat_but_writes_do_not() -> None:
    tape = _tape(
        ToolCallEvent(step=1, id="a", name="get", args={"k": 1}, result="v", effect="read"),
        ToolCallEvent(step=2, id="b", name="put", args={"k": 1}, result="ok", effect="write"),
    )
    matcher = Matcher.from_events(MatcherConfig(), tape.tool_calls())
    assert matcher.match("get", {"k": 1}) is not None
    again = matcher.match("get", {"k": 1})
    assert again is not None and again.repeated
    assert matcher.match("put", {"k": 1}) is not None
    assert matcher.match("put", {"k": 1}) is None
