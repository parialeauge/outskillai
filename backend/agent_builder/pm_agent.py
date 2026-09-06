from __future__ import annotations

from backend.agent_builder.specialist import run_specialist


def run_pm(state: dict, **kwargs) -> dict:
    return run_specialist("pm", "pm", state, live_web_if_empty=True, **kwargs)
