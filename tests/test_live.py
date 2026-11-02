"""Calls a real model. Excluded by default; run with: uv run pytest -m live"""

from __future__ import annotations

import os

import pytest
from dotenv import find_dotenv, load_dotenv

from tapedeck import OpenAIBackend

load_dotenv(find_dotenv(usecwd=True))

pytestmark = pytest.mark.live


@pytest.mark.skipif(not os.environ.get("HACKCLUB_API_KEY"), reason="HACKCLUB_API_KEY not set")
def test_model_calls_a_tool() -> None:
    backend = OpenAIBackend(
        os.environ.get("TAPEDECK_MODEL", "openai/gpt-5-mini"),
        base_url="https://ai.hackclub.com/proxy/v1",
        api_key_env="HACKCLUB_API_KEY",
    )
    tool = {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Look up an order by id.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    }
    response = backend.complete(
        {
            "model": backend.model,
            "messages": [{"role": "user", "content": "What is the status of order 4420?"}],
            "tools": [tool],
            "params": {},
        }
    )
    assert response.tool_calls, f"model answered without a tool call: {response.content!r}"
    assert response.tool_calls[0].name == "get_order"
    assert response.tool_calls[0].arguments.get("order_id") == "4420"
