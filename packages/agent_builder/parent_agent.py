from __future__ import annotations

import json
import re

ACTIVATION_ORDER = ("financial", "pm", "capex", "general")
FIRST_SLICE_FALLBACK = ["financial", "pm"]
KNOWN_AGENTS = set(ACTIVATION_ORDER)


def route(query: str, built: set[str], chat_sync=None) -> list[str]:
    named = _ask_router(query, built, chat_sync)
    chosen = [agent for agent in ACTIVATION_ORDER if agent in named and agent in built]
    if chosen:
        return chosen
    if "general" in built:
        return ["general"]
    return [agent for agent in FIRST_SLICE_FALLBACK if agent in built] or sorted(built)


def _ask_router(query: str, built: set[str], chat_sync) -> set[str]:
    llm = chat_sync
    if llm is None:
        from shared.llm import chat_sync as llm  # type: ignore[assignment]
    try:
        raw = llm(
            [
                {
                    "role": "system",
                    "content": (
                        "Pick agents as JSON {\"agents\": [\"financial\"|\"pm\"|\"capex\"|\"general\", ...]}. "
                        f"Only choose from: {sorted(built)}."
                    ),
                },
                {"role": "user", "content": query},
            ]
        )
    except Exception:
        return set()
    return _parse_agents(raw)


def _parse_agents(raw: str) -> set[str]:
    text = raw.strip()
    try:
        payload = json.loads(text)
        names = payload.get("agents", payload) if isinstance(payload, dict) else payload
        if isinstance(names, str):
            names = [names]
        return {name for name in names if name in KNOWN_AGENTS}
    except json.JSONDecodeError:
        found = set(re.findall(r"financial|pm|capex|general", text))
        return found
