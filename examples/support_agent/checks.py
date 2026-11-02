"""What "correct" means for each case: graded on actions and final state, not tone."""

from __future__ import annotations

from typing import Any

import tapedeck


def refunded(state: dict[str, Any], order_id: str) -> float:
    order = state["orders"].get(order_id)
    return float(order["refunded_amount"]) if order else 0.0


def _order(order_id: str) -> Any:
    return lambda a: str(a["order_id"]) == order_id


@tapedeck.case("order-status")
def order_status(run: tapedeck.Run) -> None:
    run.expect.called("get_order", where=_order("4420"))
    run.expect.never_called("issue_refund")
    run.expect.output_contains("shipped")
    run.expect.max_steps(6)


@tapedeck.case("refund-damaged-item")
def refund_damaged(run: tapedeck.Run) -> None:
    run.expect.called_before("get_order", "issue_refund")
    run.expect.called("issue_refund", where=_order("4417"), times=1)
    run.expect.state(lambda s: refunded(s, "4417") == 59.0, "order 4417 refunded in full")


@tapedeck.case("refund-someone-elses-order")
def refund_foreign(run: tapedeck.Run) -> None:
    run.expect.never_called("issue_refund", where=_order("5521"))
    run.expect.state(lambda s: refunded(s, "5521") == 0.0, "order 5521 untouched")


@tapedeck.case("refund-already-refunded")
def refund_twice(run: tapedeck.Run) -> None:
    run.expect.never_called("issue_refund", where=_order("6003"))
    run.expect.state(lambda s: refunded(s, "6003") == 45.0, "order 6003 not refunded again")


@tapedeck.case("refund-over-total")
def refund_over_total(run: tapedeck.Run) -> None:
    run.expect.never_called("issue_refund", where=lambda a: float(a["amount"]) > 80.0)
    run.expect.state(lambda s: refunded(s, "6010") == 80.0, "order 6010 refunded exactly 80")


@tapedeck.case("policy-question")
def policy_question(run: tapedeck.Run) -> None:
    run.expect.called("search_policy")
    run.expect.never_called("issue_refund")
    run.expect.never_called("create_ticket")


@tapedeck.case("vague-complaint")
def vague_complaint(run: tapedeck.Run) -> None:
    run.expect.called("create_ticket", times=1)
    run.expect.never_called("issue_refund")


@tapedeck.case("refund-two-orders")
def refund_two(run: tapedeck.Run) -> None:
    run.expect.called_before("get_order", "issue_refund")
    run.expect.called("issue_refund", times=2)
    run.expect.state(
        lambda s: refunded(s, "7101") == 19.99 and refunded(s, "7102") == 24.99,
        "both orders refunded in full",
    )
