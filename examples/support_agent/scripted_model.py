"""A scripted stand-in for a real LLM, so the demo and CI run offline and free.

It reads the system prompt to decide which rules it "follows", the way a real
model would follow (or miss) instructions, and uses a seeded RNG for a little
run-to-run variation. With the ownership rule removed from the prompt it will
usually refund an order that belongs to someone else, exactly the regression
Tapedeck should catch.

This is test scaffolding, not part of Tapedeck. Real tapes come from a real
model through the ``live`` backend in tapedeck.yaml.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any

from tapedeck import LLMResponse, ToolCallRequest, Usage

OWNERSHIP_RULE = "belongs to the current customer"
BALANCE_RULE = "never refund more than"
DAMAGE_WORDS = ("broken", "damaged", "shattered", "defective", "don't work", "doesn't work")


class ScriptedModel:
    model = "scripted/support-v1"

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)
        self._ids = 0

    # -- reading the conversation -------------------------------------------

    @staticmethod
    def _results(messages: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], Any]]:
        calls: dict[str, tuple[str, dict[str, Any]]] = {}
        out: list[tuple[str, dict[str, Any], Any]] = []
        for message in messages:
            for call in message.get("tool_calls") or []:
                fn = call["function"]
                calls[call["id"]] = (fn["name"], json.loads(fn["arguments"]))
            if message.get("role") == "tool":
                name, args = calls[message["tool_call_id"]]
                out.append((name, args, json.loads(message["content"])))
        return out

    # -- responding -----------------------------------------------------------

    def _call(self, name: str, **arguments: Any) -> LLMResponse:
        self._ids += 1
        return LLMResponse(
            tool_calls=[ToolCallRequest(id=f"call_{self._ids}", name=name, arguments=arguments)],
            finish_reason="tool_calls",
        )

    @staticmethod
    def _say(text: str) -> LLMResponse:
        return LLMResponse(content=text, finish_reason="stop")

    def complete(self, request: dict[str, Any]) -> LLMResponse:
        messages = request["messages"]
        response = self._decide(messages)
        size = sum(len(json.dumps(m)) for m in messages)
        response.usage = Usage(input_tokens=size // 4, output_tokens=40)
        return response

    def _decide(self, messages: list[dict[str, Any]]) -> LLMResponse:
        system = messages[0]["content"]
        user = next(m["content"] for m in messages if m["role"] == "user")
        text = user.lower()
        customer = re.search(r"Current customer id: (\S+)", system)
        customer_id = customer.group(1) if customer else ""
        checks_owner = OWNERSHIP_RULE in system
        caps_balance = BALANCE_RULE in system
        results = self._results(messages)
        orders = {a["order_id"]: r for n, a, r in results if n == "get_order"}
        refunded = {a["order_id"] for n, a, r in results if n == "issue_refund" and r.get("ok")}
        searched = any(n == "search_policy" for n, _, _ in results)
        ticketed = any(n == "create_ticket" for n, _, _ in results)
        ids = re.findall(r"\b\d{4}\b", user)
        wants_refund = "refund" in text or "money back" in text

        if wants_refund and ids:
            for oid in ids:
                if oid not in orders:
                    return self._call("get_order", order_id=oid)
            if not searched and self.rng.random() < 0.1:
                return self._call("search_policy", query="refund policy damaged")
            for oid in ids:
                order = orders[oid]
                if "error" in order:
                    return self._say(f"I couldn't find order {oid}. Could you double-check it?")
                foreign = order["customer_id"] != customer_id
                if foreign and (checks_owner or self.rng.random() < 0.15):
                    return self._say(
                        f"I'm sorry, order {oid} isn't on your account, so I can't refund it."
                    )
                remaining = round(order["total"] - order["refunded_amount"], 2)
                if remaining <= 0:
                    return self._say(f"Order {oid} has already been fully refunded.")
                if not any(w in text for w in DAMAGE_WORDS):
                    if not ticketed:
                        return self._call(
                            "create_ticket", subject=f"Refund request {oid}", body=user
                        )
                    return self._say("I've passed your request to our team.")
                asked = re.search(r"\$(\d+(?:\.\d+)?)", user)
                amount = float(asked.group(1)) if asked and len(ids) == 1 else remaining
                if caps_balance:
                    amount = min(amount, remaining)
                if oid not in refunded:
                    return self._call(
                        "issue_refund", order_id=oid, amount=amount, reason="arrived damaged"
                    )
            listed = " and ".join(ids)
            return self._say(f"Done: I've refunded order {listed}. Sorry about the damage!")

        if ids:
            oid = ids[0]
            if oid not in orders:
                return self._call("get_order", order_id=oid)
            order = orders[oid]
            if "error" in order:
                return self._say(f"I couldn't find order {oid}.")
            return self._say(f"Order {oid} is currently {order['status']}.")

        if any(w in text for w in ("policy", "window", "return")):
            if not searched:
                return self._call("search_policy", query=user)
            return self._say("Items can be returned within 30 days of delivery for a full refund.")

        if not ticketed and self.rng.random() < 0.95:
            return self._call("create_ticket", subject="Customer feedback", body=user)
        return self._say("I'm sorry to hear that. I've shared your feedback with the team.")


def make_backend(seed: int = 0) -> ScriptedModel:
    return ScriptedModel(seed)
