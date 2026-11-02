"""Simulators for the support agent's write tools.

The orders simulator is seeded from the ``get_order`` results on the tape and
applies refunds with the same rules as the real tool (``store.apply_refund``),
so a refund the recording never saw still shows up in a later ``get_order``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tapedeck import AppendLogSimulator, KeyValueSimulator, Simulator

from .store import apply_refund


def _refund(state: dict[str, Any], args: Mapping[str, Any]) -> dict[str, Any]:
    order_id = str(args.get("order_id"))
    order = state.get(order_id)
    if order is None:
        return {"error": f"order {order_id} not found"}
    updated, result = apply_refund(order, float(args.get("amount", 0)))
    state[order_id] = updated
    return result


def make() -> list[Simulator]:
    return [
        KeyValueSimulator(
            "orders",
            read_tool="get_order",
            key_arg="order_id",
            writes={"issue_refund": _refund},
            not_found=lambda oid: {"error": f"order {oid} not found"},
        ),
        AppendLogSimulator(
            "tickets",
            tools=["create_ticket"],
            id_prefix="T-",
            respond=lambda ticket_id, _args: {"ticket_id": ticket_id},
        ),
    ]
