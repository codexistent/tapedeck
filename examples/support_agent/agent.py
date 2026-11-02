"""A customer-support agent for a small online store: the agent Tapedeck tests.

It is an ordinary tool-calling loop. The only Tapedeck-specific parts are
``tapedeck.chat`` (instead of calling an SDK directly) and ``@tapedeck.tool``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import tapedeck

from . import store

MAX_STEPS = 10


@tapedeck.tool(effect="read")
def get_order(order_id: str) -> dict[str, Any]:
    """Look up an order by id."""
    order = store.get(str(order_id))
    return order if order is not None else {"error": f"order {order_id} not found"}


@tapedeck.tool(effect="read")
def search_policy(query: str) -> list[str]:
    """Return policy sections whose name or text mentions any word in the query."""
    words = {w.strip(".,?!").lower() for w in query.split() if len(w) > 2}
    hits = [
        f"{name}: {text}"
        for name, text in store.POLICY.items()
        if words & ({name} | {w.strip(".,").lower() for w in text.split()})
    ]
    return hits or ["No matching policy section."]


@tapedeck.tool(effect="write")
def issue_refund(order_id: str, amount: float, reason: str) -> dict[str, Any]:
    """Refund part or all of an order to the original payment method."""
    order = store.get(str(order_id))
    if order is None:
        return {"error": f"order {order_id} not found"}
    updated, result = store.apply_refund(order, float(amount))
    store.save(updated)
    return result


@tapedeck.tool(effect="write")
def create_ticket(subject: str, body: str) -> dict[str, Any]:
    """Open a ticket for a human support agent."""
    cursor = store.conn().execute(
        "INSERT INTO tickets (subject, body) VALUES (?, ?)", (subject, body)
    )
    return {"ticket_id": f"T-{cursor.lastrowid}"}


TOOLS: dict[str, Callable[..., Any]] = {
    "get_order": get_order,
    "search_policy": search_policy,
    "issue_refund": issue_refund,
    "create_ticket": create_ticket,
}


def _fn(name: str, description: str, params: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": params, "required": required},
        },
    }


TOOL_SCHEMAS = [
    _fn(
        "get_order",
        "Look up an order by id. Returns its customer_id, items, total, "
        "status and refunded_amount.",
        {"order_id": {"type": "string"}},
        ["order_id"],
    ),
    _fn("search_policy", "Search the store policy.", {"query": {"type": "string"}}, ["query"]),
    _fn(
        "issue_refund",
        "Refund an order to the original payment method.",
        {
            "order_id": {"type": "string"},
            "amount": {"type": "number"},
            "reason": {"type": "string"},
        },
        ["order_id", "amount", "reason"],
    ),
    _fn(
        "create_ticket",
        "Open a ticket for a human support agent.",
        {"subject": {"type": "string"}, "body": {"type": "string"}},
        ["subject", "body"],
    ),
]


def run(message: str, context: dict[str, Any], prompt: str) -> str:
    """Handle one customer message. ``context`` carries the logged-in customer id."""
    store.fresh()
    system = f"{prompt.strip()}\n\nCurrent customer id: {context['customer_id']}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": message},
    ]
    for _ in range(MAX_STEPS):
        response = tapedeck.chat(messages, TOOL_SCHEMAS, temperature=0)
        messages.append(tapedeck.assistant_message(response))
        if not response.tool_calls:
            return response.content or ""
        for call in response.tool_calls:
            fn = TOOLS.get(call.name)
            try:
                result = fn(**call.arguments) if fn else {"error": f"unknown tool {call.name}"}
            except (tapedeck.TapeMiss, tapedeck.ExternalToolBlocked):
                raise  # a replay problem, not a tool problem: let the run fail loudly
            except Exception as exc:
                result = {"error": f"{type(exc).__name__}: {exc}"}
            messages.append(tapedeck.tool_message(call.id, result))
    return "Sorry, I wasn't able to finish that. A human agent will follow up."
