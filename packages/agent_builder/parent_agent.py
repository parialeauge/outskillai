from __future__ import annotations

import json
import re

from shared.schemas import ROUTER_FORMAT

ACTIVATION_ORDER = ("financial", "pm", "capex", "general")
FIRST_SLICE_FALLBACK = ["financial", "pm"]
KNOWN_AGENTS = set(ACTIVATION_ORDER)


def decide(query: str, built: set[str], chat_sync=None) -> tuple[list[str], bool]:
    named, needs = _ask_router(query, built, chat_sync)
    chosen = [agent for agent in ACTIVATION_ORDER if agent in named and agent in built]
    if chosen:
        return chosen, needs
    if "general" in built:
        return ["general"], needs
    fallback = [agent for agent in FIRST_SLICE_FALLBACK if agent in built] or sorted(built)
    return fallback, needs


def route(query: str, built: set[str], chat_sync=None) -> list[str]:
    agents, _needs = decide(query, built, chat_sync=chat_sync)
    return agents


def _ask_router(query: str, built: set[str], chat_sync) -> tuple[set[str], bool]:
    llm = chat_sync
    if llm is None:
        from shared.llm import chat_sync as llm  # type: ignore[assignment]
    try:
        raw = llm(
            [
                {
                    "role": "system",
                    "content": (
                        "Pick agents as JSON {\"agents\": [\"financial\"|\"pm\"|\"capex\"|\"general\", ...], "
                        "\"needs_current_info\": true|false}. "
                        f"Only choose from: {sorted(built)}. "
                        "Set needs_current_info true when the question needs live or recent information."
                    ),
                },
                {"role": "user", "content": query},
            ],
            response_format=ROUTER_FORMAT,
        )
    except Exception:
        return set(), False
    return _parse_route(raw)


def _parse_route(raw: str) -> tuple[set[str], bool]:
    text = raw.strip()
    try:
        payload = json.loads(text)
        needs = bool(payload.get("needs_current_info")) if isinstance(payload, dict) else False
        names = payload.get("agents", payload) if isinstance(payload, dict) else payload
        if isinstance(names, str):
            names = [names]
        return {name for name in names if name in KNOWN_AGENTS}, needs
    except json.JSONDecodeError:
        found = set(re.findall(r"financial|pm|capex|general", text))
        return found, False
