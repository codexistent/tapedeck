"""LLM backends: where a live ``tapedeck.chat`` call actually goes.

Messages and tools use the OpenAI chat-completions shapes, which nearly every
provider and proxy (OpenRouter, Hack Club AI, vLLM, ...) accepts. Responses are
normalized to :class:`~tapedeck.tape.LLMResponse` so agents never touch SDK objects.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol, runtime_checkable

from .canonical import canonical_json
from .tape import LLMResponse, ToolCallRequest, Usage


@runtime_checkable
class Backend(Protocol):
    model: str

    def complete(self, request: dict[str, Any]) -> LLMResponse:
        """``request`` has keys model, messages, tools, params."""
        ...


class OpenAIBackend:
    """Any OpenAI-compatible endpoint."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        timeout: float = 120.0,
        max_retries: int = 4,
    ) -> None:
        from openai import OpenAI  # imported lazily so playback never needs it

        self.model = model
        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"no API key: set {api_key_env} (e.g. in .env)")
        self._client = OpenAI(
            base_url=base_url, api_key=key, timeout=timeout, max_retries=max_retries
        )

    def complete(self, request: dict[str, Any]) -> LLMResponse:
        kwargs: dict[str, Any] = dict(request.get("params") or {})
        if request.get("tools"):
            kwargs["tools"] = request["tools"]
        raw = self._client.chat.completions.create(
            model=request["model"], messages=request["messages"], **kwargs
        )
        choice = raw.choices[0]
        calls: list[ToolCallRequest] = []
        for call in choice.message.tool_calls or []:
            fn = getattr(call, "function", None)
            if fn is None:
                continue
            try:
                arguments = json.loads(fn.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {"_unparseable_arguments": fn.arguments}
            if not isinstance(arguments, dict):
                arguments = {"_value": arguments}
            calls.append(ToolCallRequest(id=call.id, name=fn.name, arguments=arguments))
        usage = raw.usage
        return LLMResponse(
            content=choice.message.content,
            tool_calls=calls,
            usage=Usage(
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            ),
            finish_reason=choice.finish_reason,
        )


def assistant_message(response: LLMResponse) -> dict[str, Any]:
    """The assistant turn to append to the conversation after ``response``."""
    message: dict[str, Any] = {"role": "assistant", "content": response.content}
    if response.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": canonical_json(call.arguments)},
            }
            for call in response.tool_calls
        ]
    return message


def tool_message(call_id: str, result: Any) -> dict[str, Any]:
    """The tool turn carrying ``result`` back to the model."""
    content = result if isinstance(result, str) else canonical_json(result)
    return {"role": "tool", "tool_call_id": call_id, "content": content}
