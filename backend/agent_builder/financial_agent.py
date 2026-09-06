from __future__ import annotations

from backend.agent_builder.specialist import run_specialist


def run_financial(state: dict, **kwargs) -> dict:
    return run_specialist("financial", "financial", state, live_web_if_empty=True, **kwargs)
