"""OpenRouter chat wrapper with bounded retry behavior."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from shared.config import LLM_TIMEOUT

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _openrouter_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "")


def _openrouter_model() -> str:
    return os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")


def _base_headers() -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {_openrouter_key()}",
        "Content-Type": "application/json",
    }

    # LangSmith-related env should never interfere with chat calls.
    try:
        if os.getenv("LANGCHAIN_TRACING_V2") or os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY"):
            return headers
    except Exception:
        return headers

    return headers


def _response_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""

    first_choice = choices[0] or {}
    message = first_choice.get("message") or {}
    if isinstance(message, dict) and message.get("content") is not None:
        return str(message["content"])

    if first_choice.get("text") is not None:
        return str(first_choice["text"])

    return ""


async def chat(
    messages: list[dict],
    *,
    timeout: float = LLM_TIMEOUT,
    response_format: dict | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": _openrouter_model(),
        "messages": messages,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    last_error: Exception | None = None
    async with httpx.AsyncClient(headers=_base_headers()) as client:
        for attempt in range(2):
            try:
                response = await client.post(
                    OPENROUTER_URL,
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
                return _response_content(response.json())
            except httpx.ConnectError as error:
                last_error = error
                if attempt == 0:
                    continue
                raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("OpenRouter chat failed without an error")


def chat_sync(
    messages: list[dict],
    *,
    timeout: float = LLM_TIMEOUT,
    response_format: dict | None = None,
) -> str:
    return asyncio.run(chat(messages, timeout=timeout, response_format=response_format))

