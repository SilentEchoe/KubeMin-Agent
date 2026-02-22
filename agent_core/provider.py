"""OpenAI-compatible provider with tool-call parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ToolCallRequest:
    """Tool call request emitted by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Normalized model response."""

    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class OpenAICompatibleProvider:
    """Provider for OpenAI-style `/chat/completions` endpoints."""

    def __init__(
        self,
        api_base: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 60.0,
    ):
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        endpoint = f"{self.api_base}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.post(endpoint, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
            return self._parse_response(data)
        except Exception as exc:  # pragma: no cover - exercised in integration
            return LLMResponse(
                content=f"Error calling model endpoint: {exc}",
                finish_reason="error",
            )

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        choices = data.get("choices", [])
        if not choices:
            return LLMResponse(content="Error: empty model response", finish_reason="error")

        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content")

        # Some providers can return segmented content payloads.
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(str(part.get("text", "")))
            content = "\n".join([part for part in text_parts if part])

        tool_calls: list[ToolCallRequest] = []
        for raw_call in message.get("tool_calls", []) or []:
            function = raw_call.get("function", {})
            raw_args = function.get("arguments", {})
            parsed_args: dict[str, Any]
            if isinstance(raw_args, str):
                try:
                    parsed_args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    parsed_args = {"raw": raw_args}
            elif isinstance(raw_args, dict):
                parsed_args = raw_args
            else:
                parsed_args = {}

            tool_calls.append(
                ToolCallRequest(
                    id=str(raw_call.get("id", "")),
                    name=str(function.get("name", "")),
                    arguments=parsed_args,
                )
            )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=str(choice.get("finish_reason", "stop")),
        )

